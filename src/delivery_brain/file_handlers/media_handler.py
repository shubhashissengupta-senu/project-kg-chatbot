"""
Media File Handler for Delivery Brain

Handles: Audio (MP3, WAV, M4A, FLAC, OGG) and Video (MP4, AVI, WMV, MOV, MKV)
License-compliant dependencies:
- openai-whisper (MIT) for transcription
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
        self._whisper_model = None
        self._pydub_available = False
        self._moviepy_available = False
        self._pyannote_available = False
        self._diarization_pipeline = None

        self._check_dependencies()

    def _check_dependencies(self):
        """Check for required dependencies"""
        try:
            import whisper
            self._whisper_available = True
            logger.info("Whisper available for transcription")
        except ImportError:
            logger.warning("openai-whisper not available - transcription disabled")

        try:
            import pydub
            self._pydub_available = True
        except ImportError:
            logger.warning("pydub not available - audio conversion limited")

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
            import whisper
            logger.info(f"Loading Whisper model: {self.whisper_model_size}")
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

            # Transcribe audio
            transcription_result = self._transcribe_audio(audio_path)
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

            # Clean up temp audio file if extracted from video
            if self.is_video(filepath) and audio_path != filepath:
                try:
                    os.remove(audio_path)
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
