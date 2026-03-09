"""
Media File Handler for Delivery Brain

Handles: Audio (MP3, WAV, M4A, FLAC, OGG) and Video (MP4, AVI, WMV, MOV, MKV)
License-compliant dependencies:
- faster-whisper (MIT) or openai-whisper (MIT) for transcription
- pyannote.audio (MIT) for speaker diarization
- pydub (MIT) for audio processing
- moviepy (MIT) for video processing
"""

import os
import logging
import tempfile
from pathlib import Path
from typing import Optional, Dict, Any, Tuple, List
from datetime import datetime

from ..models import Speaker, TranscriptionSegment

logger = logging.getLogger(__name__)


class MediaHandler:
    """Handler for audio and video files with transcription and diarization"""

    AUDIO_EXTENSIONS = [".mp3", ".wav", ".m4a", ".flac", ".ogg"]
    VIDEO_EXTENSIONS = [".mp4", ".avi", ".wmv", ".mov", ".mkv"]
    SUPPORTED_EXTENSIONS = AUDIO_EXTENSIONS + VIDEO_EXTENSIONS

    def __init__(self,
                 whisper_model: str = "base",
                 device: str = "cpu",
                 enable_diarization: bool = True,
                 min_speakers: int = 1,
                 max_speakers: int = 10):
        """
        Initialize media handler.

        Args:
            whisper_model: Whisper model size (tiny, base, small, medium, large)
            device: Device to use (cpu or cuda)
            enable_diarization: Enable speaker diarization
            min_speakers: Minimum number of speakers for diarization
            max_speakers: Maximum number of speakers for diarization
        """
        self.whisper_model_size = whisper_model
        self.device = device
        self.enable_diarization = enable_diarization
        self.min_speakers = min_speakers
        self.max_speakers = max_speakers

        self._whisper_available = False
        self._faster_whisper = False  # True if using faster-whisper
        self._whisper_model = None
        self._pydub_available = False
        self._av_available = False
        self._moviepy_available = False
        self._pyannote_available = False
        self._diarization_pipeline = None

        self._check_dependencies()

    def _check_dependencies(self):
        """Check for required dependencies"""
        # Try faster-whisper first (preferred - more efficient)
        try:
            from faster_whisper import WhisperModel
            self._whisper_available = True
            self._faster_whisper = True
            logger.info("faster-whisper available for transcription")
        except ImportError:
            # Fall back to openai-whisper
            try:
                import whisper
                self._whisper_available = True
                self._faster_whisper = False
                logger.info("openai-whisper available for transcription")
            except ImportError:
                logger.warning("No whisper library available - transcription disabled")

        try:
            import pydub
            self._pydub_available = True
        except ImportError:
            logger.warning("pydub not available - audio conversion limited")

        # Check for av (pyav) - for audio conversion without ffmpeg
        try:
            import av
            self._av_available = True
        except ImportError:
            self._av_available = False
            logger.warning("av not available - audio conversion limited")

        try:
            import moviepy.editor
            self._moviepy_available = True
        except ImportError:
            logger.warning("moviepy not available - video extraction limited")

        try:
            from pyannote.audio import Pipeline
            self._pyannote_available = True
            logger.info("pyannote.audio available for diarization")
        except ImportError:
            logger.warning("pyannote.audio not available - diarization disabled")

    def _load_whisper_model(self):
        """Load Whisper model lazily"""
        if self._whisper_model is None and self._whisper_available:
            logger.info(f"Loading Whisper model: {self.whisper_model_size}")
            if self._faster_whisper:
                from faster_whisper import WhisperModel
                # faster-whisper uses compute_type instead of device
                compute_type = "float16" if self.device == "cuda" else "int8"
                self._whisper_model = WhisperModel(
                    self.whisper_model_size,
                    device=self.device,
                    compute_type=compute_type
                )
            else:
                import whisper
                self._whisper_model = whisper.load_model(
                    self.whisper_model_size,
                    device=self.device
                )
        return self._whisper_model

    def _load_diarization_pipeline(self):
        """Load diarization pipeline lazily"""
        if self._diarization_pipeline is None and self._pyannote_available:
            try:
                from pyannote.audio import Pipeline
                import torch

                # Note: pyannote.audio requires HuggingFace token for pretrained models
                # Using local fallback if token not available
                hf_token = os.getenv("HF_TOKEN") or os.getenv("HUGGINGFACE_TOKEN")

                if hf_token:
                    self._diarization_pipeline = Pipeline.from_pretrained(
                        "pyannote/speaker-diarization-3.1",
                        use_auth_token=hf_token
                    )
                    if self.device == "cuda" and torch.cuda.is_available():
                        self._diarization_pipeline.to(torch.device("cuda"))
                    logger.info("Diarization pipeline loaded")
                else:
                    logger.warning("No HuggingFace token - diarization requires HF_TOKEN env var")
                    self._pyannote_available = False

            except Exception as e:
                logger.warning(f"Could not load diarization pipeline: {e}")
                self._pyannote_available = False

        return self._diarization_pipeline

    def _convert_audio_to_16khz_mono(self, input_path: str) -> str:
        """
        Convert audio to 16kHz mono WAV for efficient Whisper processing.
        Uses av library for conversion without requiring ffmpeg.
        """
        if not self._av_available:
            return input_path  # Return original if av not available

        import av
        import numpy as np

        logger.info(f"Converting audio to 16kHz mono: {input_path}")

        # Create temp file for converted audio
        temp_wav = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
        temp_wav_path = temp_wav.name
        temp_wav.close()

        try:
            # Open input
            input_container = av.open(input_path)
            input_stream = input_container.streams.audio[0]

            # Set up resampler to 16kHz mono
            resampler = av.AudioResampler(
                format='s16',
                layout='mono',
                rate=16000
            )

            # Open output
            output_container = av.open(temp_wav_path, 'w')
            output_stream = output_container.add_stream('pcm_s16le', rate=16000)
            output_stream.layout = 'mono'

            # Process audio
            for frame in input_container.decode(audio=0):
                # Resample
                resampled_frames = resampler.resample(frame)
                for resampled_frame in resampled_frames:
                    # Encode and write
                    for packet in output_stream.encode(resampled_frame):
                        output_container.mux(packet)

            # Flush
            for packet in output_stream.encode(None):
                output_container.mux(packet)

            input_container.close()
            output_container.close()

            logger.info(f"Audio converted successfully: {temp_wav_path}")
            return temp_wav_path

        except Exception as e:
            logger.error(f"Audio conversion failed: {e}")
            # Clean up temp file on failure
            try:
                os.remove(temp_wav_path)
            except:
                pass
            return input_path  # Fall back to original

    def can_handle(self, filepath: str) -> bool:
        """Check if this handler can process the file"""
        ext = Path(filepath).suffix.lower()
        return ext in self.SUPPORTED_EXTENSIONS and self._whisper_available

    def is_audio(self, filepath: str) -> bool:
        """Check if file is audio"""
        return Path(filepath).suffix.lower() in self.AUDIO_EXTENSIONS

    def is_video(self, filepath: str) -> bool:
        """Check if file is video"""
        return Path(filepath).suffix.lower() in self.VIDEO_EXTENSIONS

    def extract_content(self, filepath: str) -> Tuple[str, Dict[str, Any], List[TranscriptionSegment]]:
        """
        Extract content from a media file.

        Returns:
            Tuple of (transcribed_text, metadata, transcription_segments)
        """
        path = Path(filepath)
        extension = path.suffix.lower()
        metadata = {
            "file_type": extension[1:],
            "file_name": path.name,
            "media_type": "audio" if self.is_audio(filepath) else "video",
        }

        converted_audio_path = None
        try:
            # Extract audio from video if needed
            if self.is_video(filepath):
                audio_path = self._extract_audio_from_video(filepath)
                metadata["video_audio_extracted"] = True
            else:
                audio_path = filepath

            # Get audio metadata
            audio_metadata = self._get_audio_metadata(audio_path)
            metadata.update(audio_metadata)

            # Convert to 16kHz mono for efficient processing
            if self._av_available:
                converted_audio_path = self._convert_audio_to_16khz_mono(audio_path)
                transcribe_path = converted_audio_path
            else:
                transcribe_path = audio_path

            # Transcribe audio
            transcription_result = self._transcribe_audio(transcribe_path)
            segments = transcription_result["segments"]
            full_text = transcription_result["text"]

            metadata["language"] = transcription_result.get("language", "unknown")
            metadata["transcription_duration"] = transcription_result.get("duration", 0)

            # Convert to TranscriptionSegment objects
            transcription_segments = [
                TranscriptionSegment(
                    text=seg["text"].strip(),
                    start_time=seg["start"],
                    end_time=seg["end"],
                    confidence=seg.get("confidence", 1.0)
                )
                for seg in segments
            ]

            # Perform diarization if enabled
            if self.enable_diarization and self._pyannote_available:
                speakers, diarized_segments = self._perform_diarization(
                    audio_path, transcription_segments
                )
                metadata["speakers"] = speakers
                metadata["speaker_count"] = len(speakers)
                transcription_segments = diarized_segments

                # Rebuild full text with speaker labels
                full_text = self._build_diarized_text(diarized_segments)

            # Clean up temp audio files
            if self.is_video(filepath) and audio_path != filepath:
                try:
                    os.remove(audio_path)
                except:
                    pass
            if converted_audio_path and converted_audio_path != audio_path:
                try:
                    os.remove(converted_audio_path)
                except:
                    pass

            # Calculate stats
            metadata["word_count"] = len(full_text.split())
            metadata["segment_count"] = len(transcription_segments)

            return full_text, metadata, transcription_segments

        except Exception as e:
            logger.error(f"Error extracting content from {filepath}: {e}")
            raise

    def _extract_audio_from_video(self, video_path: str) -> str:
        """Extract audio track from video file"""
        if not self._moviepy_available:
            raise RuntimeError("moviepy not available for video audio extraction")

        from moviepy.editor import VideoFileClip

        # Create temp file for audio
        temp_audio = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
        temp_audio_path = temp_audio.name
        temp_audio.close()

        try:
            video = VideoFileClip(video_path)
            video.audio.write_audiofile(
                temp_audio_path,
                codec="pcm_s16le",
                verbose=False,
                logger=None
            )
            video.close()
            return temp_audio_path
        except Exception as e:
            logger.error(f"Error extracting audio from video: {e}")
            raise

    def _get_audio_metadata(self, audio_path: str) -> Dict[str, Any]:
        """Get audio file metadata"""
        metadata = {}

        if self._pydub_available:
            try:
                from pydub import AudioSegment
                audio = AudioSegment.from_file(audio_path)
                metadata["duration_seconds"] = len(audio) / 1000.0
                metadata["channels"] = audio.channels
                metadata["sample_rate"] = audio.frame_rate
                metadata["sample_width"] = audio.sample_width
            except Exception as e:
                logger.warning(f"Could not get audio metadata: {e}")

        return metadata

    def _transcribe_audio(self, audio_path: str) -> Dict[str, Any]:
        """Transcribe audio using Whisper"""
        model = self._load_whisper_model()
        if model is None:
            raise RuntimeError("Whisper model not available")

        logger.info(f"Transcribing audio: {audio_path}")

        if self._faster_whisper:
            # For long audio, process in chunks to avoid memory issues
            # First check audio duration
            import av
            try:
                container = av.open(audio_path)
                duration_sec = container.duration / 1000000 if container.duration else 0
                container.close()
            except:
                duration_sec = 0

            # If audio is longer than 5 minutes, process in chunks
            if duration_sec > 300 and self._av_available:
                return self._transcribe_audio_chunked(audio_path, model, duration_sec)

            # faster-whisper API for shorter audio
            segments_gen, info = model.transcribe(
                audio_path,
                word_timestamps=True,
                vad_filter=True
            )
            # Convert generator to list and build segments
            segments = []
            full_text_parts = []
            for segment in segments_gen:
                segments.append({
                    "start": segment.start,
                    "end": segment.end,
                    "text": segment.text,
                    "confidence": segment.avg_logprob if hasattr(segment, 'avg_logprob') else 1.0
                })
                full_text_parts.append(segment.text)

            return {
                "text": " ".join(full_text_parts),
                "segments": segments,
                "language": info.language if hasattr(info, 'language') else "unknown",
                "duration": segments[-1]["end"] if segments else 0
            }
        else:
            # openai-whisper API
            result = model.transcribe(
                audio_path,
                word_timestamps=True,
                verbose=False
            )
            return {
                "text": result["text"],
                "segments": result["segments"],
                "language": result.get("language"),
                "duration": result["segments"][-1]["end"] if result["segments"] else 0
            }

    def _transcribe_audio_chunked(self, audio_path: str, model, total_duration: float) -> Dict[str, Any]:
        """
        Transcribe long audio by splitting into smaller chunks.
        This avoids memory issues with very long audio files.
        """
        import av
        import numpy as np

        logger.info(f"Processing long audio ({total_duration:.0f}s) in chunks...")

        CHUNK_DURATION = 240  # 4 minutes per chunk
        all_segments = []
        all_text_parts = []
        detected_language = None

        # Process audio in chunks
        chunk_start = 0
        chunk_idx = 0
        while chunk_start < total_duration:
            chunk_end = min(chunk_start + CHUNK_DURATION, total_duration)
            logger.info(f"Processing chunk {chunk_idx + 1}: {chunk_start:.0f}s - {chunk_end:.0f}s")

            # Extract chunk to temp file
            chunk_path = self._extract_audio_chunk(audio_path, chunk_start, chunk_end)

            try:
                # Transcribe chunk
                segments_gen, info = model.transcribe(
                    chunk_path,
                    word_timestamps=True,
                    vad_filter=True
                )

                if detected_language is None and hasattr(info, 'language'):
                    detected_language = info.language

                # Process segments and adjust timestamps
                for segment in segments_gen:
                    adjusted_start = segment.start + chunk_start
                    adjusted_end = segment.end + chunk_start
                    all_segments.append({
                        "start": adjusted_start,
                        "end": adjusted_end,
                        "text": segment.text,
                        "confidence": segment.avg_logprob if hasattr(segment, 'avg_logprob') else 1.0
                    })
                    all_text_parts.append(segment.text)

            finally:
                # Clean up chunk temp file
                try:
                    os.remove(chunk_path)
                except:
                    pass

            chunk_start = chunk_end
            chunk_idx += 1

        return {
            "text": " ".join(all_text_parts),
            "segments": all_segments,
            "language": detected_language or "unknown",
            "duration": total_duration
        }

    def _extract_audio_chunk(self, audio_path: str, start_sec: float, end_sec: float) -> str:
        """Extract a chunk of audio to a temporary file using numpy arrays."""
        import av
        import numpy as np
        import wave

        temp_wav = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
        temp_wav_path = temp_wav.name
        temp_wav.close()

        # Open input and collect samples in the time range
        input_container = av.open(audio_path)
        input_stream = input_container.streams.audio[0]
        sample_rate = input_stream.sample_rate

        # Set up resampler to 16kHz mono
        resampler = av.AudioResampler(
            format='s16',
            layout='mono',
            rate=16000
        )

        # Collect audio samples
        all_samples = []
        current_time = 0.0

        for frame in input_container.decode(audio=0):
            # Calculate frame time based on samples
            frame_duration = frame.samples / sample_rate
            frame_end_time = current_time + frame_duration

            # Skip frames before start
            if frame_end_time < start_sec:
                current_time = frame_end_time
                continue

            # Stop if past end
            if current_time >= end_sec:
                break

            # Resample frame
            resampled_frames = resampler.resample(frame)
            for resampled_frame in resampled_frames:
                # Convert to numpy array
                arr = resampled_frame.to_ndarray()
                if arr.ndim > 1:
                    arr = arr.flatten()
                all_samples.append(arr)

            current_time = frame_end_time

        input_container.close()

        # Combine all samples
        if all_samples:
            audio_data = np.concatenate(all_samples)
            # Ensure int16 format
            if audio_data.dtype != np.int16:
                audio_data = (audio_data * 32767).astype(np.int16)
        else:
            audio_data = np.array([], dtype=np.int16)

        # Write WAV file
        with wave.open(temp_wav_path, 'wb') as wav_file:
            wav_file.setnchannels(1)
            wav_file.setsampwidth(2)  # 16-bit
            wav_file.setframerate(16000)
            wav_file.writeframes(audio_data.tobytes())

        return temp_wav_path

    def _perform_diarization(self,
                             audio_path: str,
                             segments: List[TranscriptionSegment]
                             ) -> Tuple[List[Speaker], List[TranscriptionSegment]]:
        """Perform speaker diarization and assign speakers to segments"""
        pipeline = self._load_diarization_pipeline()
        if pipeline is None:
            logger.warning("Diarization pipeline not available")
            return [], segments

        logger.info("Performing speaker diarization...")

        try:
            # Run diarization
            diarization = pipeline(
                audio_path,
                min_speakers=self.min_speakers,
                max_speakers=self.max_speakers
            )

            # Build speaker list
            speakers_dict = {}
            for turn, _, speaker in diarization.itertracks(yield_label=True):
                if speaker not in speakers_dict:
                    speakers_dict[speaker] = Speaker(
                        speaker_id=speaker,
                        label=speaker
                    )
                speakers_dict[speaker].add_segment(turn.start, turn.end)

            speakers = list(speakers_dict.values())

            # Assign speakers to transcription segments
            diarized_segments = []
            for segment in segments:
                # Find speaker for this segment's time range
                segment_mid = (segment.start_time + segment.end_time) / 2
                assigned_speaker = None

                for turn, _, speaker in diarization.itertracks(yield_label=True):
                    if turn.start <= segment_mid <= turn.end:
                        assigned_speaker = speaker
                        break

                diarized_segments.append(TranscriptionSegment(
                    text=segment.text,
                    start_time=segment.start_time,
                    end_time=segment.end_time,
                    speaker=assigned_speaker,
                    confidence=segment.confidence
                ))

            return speakers, diarized_segments

        except Exception as e:
            logger.error(f"Diarization failed: {e}")
            return [], segments

    def _build_diarized_text(self, segments: List[TranscriptionSegment]) -> str:
        """Build full text with speaker labels"""
        text_parts = []
        current_speaker = None

        for segment in segments:
            if segment.speaker and segment.speaker != current_speaker:
                text_parts.append(f"\n[{segment.speaker}]: ")
                current_speaker = segment.speaker
            text_parts.append(segment.text + " ")

        return "".join(text_parts).strip()


# Convenience function
def extract_media_content(filepath: str,
                          whisper_model: str = "base",
                          enable_diarization: bool = True
                          ) -> Tuple[str, Dict[str, Any], List[TranscriptionSegment]]:
    """Extract content from a media file"""
    handler = MediaHandler(
        whisper_model=whisper_model,
        enable_diarization=enable_diarization
    )
    return handler.extract_content(filepath)
