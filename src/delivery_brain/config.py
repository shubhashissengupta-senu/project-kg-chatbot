"""
Configuration for Delivery Brain Data Ingestion
"""

from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any
from pathlib import Path
import os


@dataclass
class ChunkingConfig:
    """Configuration for text chunking"""
    chunk_size: int = 1000  # characters
    chunk_overlap: int = 200  # characters
    min_chunk_size: int = 100  # minimum chunk size
    split_by: str = "sentence"  # sentence, paragraph, or fixed


@dataclass
class CleaningConfig:
    """Configuration for text cleaning"""
    remove_extra_whitespace: bool = True
    fix_encoding: bool = True
    remove_special_chars: bool = False
    lowercase: bool = False
    remove_urls: bool = False
    remove_emails: bool = False
    remove_phone_numbers: bool = False
    language_detection: bool = True


@dataclass
class TranscriptionConfig:
    """Configuration for audio/video transcription"""
    model_size: str = "base"  # tiny, base, small, medium, large
    language: Optional[str] = None  # Auto-detect if None
    enable_diarization: bool = True
    min_speakers: int = 1
    max_speakers: int = 10
    device: str = "cpu"  # cpu or cuda


@dataclass
class StorageConfig:
    """Configuration for storage backends"""
    # NoSQL Configuration
    nosql_type: str = "tinydb"  # tinydb or mongodb
    mongodb_uri: str = "mongodb://localhost:27017"
    mongodb_database: str = "delivery_brain"
    tinydb_path: str = "./data/delivery_brain_db.json"

    # ChromaDB Configuration
    chromadb_path: str = "./data/chroma_delivery_brain"
    chromadb_collection: str = "delivery_brain_docs"

    # Embedding configuration
    embedding_model: str = "default"  # default uses ONNX embeddings


@dataclass
class IngestionConfig:
    """Main configuration for ingestion pipeline"""
    # Supported file extensions
    supported_extensions: List[str] = field(default_factory=lambda: [
        # Text files
        ".txt", ".md", ".markdown", ".xml", ".json", ".csv",
        # Documents
        ".pdf", ".docx", ".doc", ".pptx", ".ppt", ".xlsx", ".xls",
        # Media files
        ".mp3", ".wav", ".m4a", ".flac", ".ogg",  # Audio
        ".mp4", ".avi", ".wmv", ".mov", ".mkv",   # Video
    ])

    # Processing configurations
    chunking: ChunkingConfig = field(default_factory=ChunkingConfig)
    cleaning: CleaningConfig = field(default_factory=CleaningConfig)
    transcription: TranscriptionConfig = field(default_factory=TranscriptionConfig)
    storage: StorageConfig = field(default_factory=StorageConfig)

    # General settings
    recursive: bool = True  # Scan subdirectories
    max_file_size_mb: int = 500  # Maximum file size in MB
    batch_size: int = 10  # Files to process in batch
    parallel_processing: bool = True
    max_workers: int = 4

    # Metadata extraction
    extract_metadata: bool = True
    include_file_stats: bool = True

    # Error handling
    skip_on_error: bool = True  # Continue processing on errors
    log_errors: bool = True

    def get_supported_text_extensions(self) -> List[str]:
        """Get text file extensions"""
        return [".txt", ".md", ".markdown", ".xml", ".json", ".csv"]

    def get_supported_document_extensions(self) -> List[str]:
        """Get document file extensions"""
        return [".pdf", ".docx", ".doc", ".pptx", ".ppt", ".xlsx", ".xls"]

    def get_supported_audio_extensions(self) -> List[str]:
        """Get audio file extensions"""
        return [".mp3", ".wav", ".m4a", ".flac", ".ogg"]

    def get_supported_video_extensions(self) -> List[str]:
        """Get video file extensions"""
        return [".mp4", ".avi", ".wmv", ".mov", ".mkv"]

    def is_text_file(self, filepath: str) -> bool:
        """Check if file is a text file"""
        return Path(filepath).suffix.lower() in self.get_supported_text_extensions()

    def is_document_file(self, filepath: str) -> bool:
        """Check if file is a document file"""
        return Path(filepath).suffix.lower() in self.get_supported_document_extensions()

    def is_audio_file(self, filepath: str) -> bool:
        """Check if file is an audio file"""
        return Path(filepath).suffix.lower() in self.get_supported_audio_extensions()

    def is_video_file(self, filepath: str) -> bool:
        """Check if file is a video file"""
        return Path(filepath).suffix.lower() in self.get_supported_video_extensions()

    def is_media_file(self, filepath: str) -> bool:
        """Check if file is audio or video"""
        return self.is_audio_file(filepath) or self.is_video_file(filepath)

    @classmethod
    def from_env(cls) -> "IngestionConfig":
        """Create configuration from environment variables"""
        config = cls()

        # Override from environment
        if os.getenv("MONGODB_URI"):
            config.storage.mongodb_uri = os.getenv("MONGODB_URI")
        if os.getenv("MONGODB_DATABASE"):
            config.storage.mongodb_database = os.getenv("MONGODB_DATABASE")
        if os.getenv("NOSQL_TYPE"):
            config.storage.nosql_type = os.getenv("NOSQL_TYPE")
        if os.getenv("WHISPER_MODEL"):
            config.transcription.model_size = os.getenv("WHISPER_MODEL")
        if os.getenv("WHISPER_DEVICE"):
            config.transcription.device = os.getenv("WHISPER_DEVICE")

        return config
