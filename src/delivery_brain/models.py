"""
Data models for Delivery Brain Data Ingestion
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Dict, Optional, Any
from enum import Enum
import hashlib
import uuid


class FileType(Enum):
    """Supported file types"""
    TEXT = "text"
    MARKDOWN = "markdown"
    XML = "xml"
    JSON = "json"
    CSV = "csv"
    PDF = "pdf"
    DOCX = "docx"
    PPTX = "pptx"
    XLSX = "xlsx"
    AUDIO = "audio"
    VIDEO = "video"
    UNKNOWN = "unknown"


class ProcessingStatus(Enum):
    """Processing status"""
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass
class Speaker:
    """Speaker information from diarization"""
    speaker_id: str
    label: str  # e.g., "SPEAKER_00"
    segments: List[Dict[str, float]] = field(default_factory=list)  # start, end times
    total_duration: float = 0.0

    def add_segment(self, start: float, end: float):
        """Add a speaking segment"""
        self.segments.append({"start": start, "end": end})
        self.total_duration += (end - start)


@dataclass
class TranscriptionSegment:
    """A segment of transcribed text"""
    text: str
    start_time: float
    end_time: float
    speaker: Optional[str] = None
    confidence: float = 1.0


@dataclass
class DocumentMetadata:
    """Metadata for an ingested document"""
    file_path: str
    file_name: str
    file_type: FileType
    file_size_bytes: int
    file_hash: str
    created_at: datetime
    modified_at: datetime
    ingested_at: datetime = field(default_factory=datetime.now)

    # Content metadata
    language: Optional[str] = None
    encoding: Optional[str] = None
    page_count: Optional[int] = None
    word_count: Optional[int] = None
    char_count: Optional[int] = None

    # Media metadata
    duration_seconds: Optional[float] = None
    speakers: Optional[List[Speaker]] = None
    audio_channels: Optional[int] = None
    sample_rate: Optional[int] = None

    # Document-specific metadata
    title: Optional[str] = None
    author: Optional[str] = None
    subject: Optional[str] = None
    keywords: Optional[List[str]] = None

    # Custom metadata
    custom: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            "file_path": self.file_path,
            "file_name": self.file_name,
            "file_type": self.file_type.value,
            "file_size_bytes": self.file_size_bytes,
            "file_hash": self.file_hash,
            "created_at": self.created_at.isoformat(),
            "modified_at": self.modified_at.isoformat(),
            "ingested_at": self.ingested_at.isoformat(),
            "language": self.language,
            "encoding": self.encoding,
            "page_count": self.page_count,
            "word_count": self.word_count,
            "char_count": self.char_count,
            "duration_seconds": self.duration_seconds,
            "speakers": [
                {"id": s.speaker_id, "label": s.label, "duration": s.total_duration}
                for s in (self.speakers or [])
            ],
            "title": self.title,
            "author": self.author,
            "subject": self.subject,
            "keywords": self.keywords,
            "custom": self.custom,
        }


@dataclass
class DocumentChunk:
    """A chunk of document content"""
    chunk_id: str
    document_id: str
    content: str
    chunk_index: int
    total_chunks: int

    # Position information
    start_char: Optional[int] = None
    end_char: Optional[int] = None
    start_time: Optional[float] = None  # For media files
    end_time: Optional[float] = None

    # Speaker information (for transcribed content)
    speaker: Optional[str] = None

    # Metadata
    metadata: Dict[str, Any] = field(default_factory=dict)

    # Embedding (populated after vectorization)
    embedding: Optional[List[float]] = None

    def __post_init__(self):
        if not self.chunk_id:
            self.chunk_id = str(uuid.uuid4())

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for storage"""
        return {
            "chunk_id": self.chunk_id,
            "document_id": self.document_id,
            "content": self.content,
            "chunk_index": self.chunk_index,
            "total_chunks": self.total_chunks,
            "start_char": self.start_char,
            "end_char": self.end_char,
            "start_time": self.start_time,
            "end_time": self.end_time,
            "speaker": self.speaker,
            "metadata": self.metadata,
        }


@dataclass
class IngestedDocument:
    """A fully processed document"""
    document_id: str
    metadata: DocumentMetadata
    raw_content: str
    cleaned_content: str
    chunks: List[DocumentChunk]
    status: ProcessingStatus = ProcessingStatus.COMPLETED

    # Transcription data (for media files)
    transcription_segments: Optional[List[TranscriptionSegment]] = None

    # Processing info
    processing_time_seconds: float = 0.0
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    def __post_init__(self):
        if not self.document_id:
            self.document_id = str(uuid.uuid4())

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for storage"""
        return {
            "document_id": self.document_id,
            "metadata": self.metadata.to_dict(),
            "raw_content": self.raw_content[:10000] if self.raw_content else None,  # Truncate for storage
            "cleaned_content": self.cleaned_content[:10000] if self.cleaned_content else None,
            "chunk_count": len(self.chunks),
            "status": self.status.value,
            "processing_time_seconds": self.processing_time_seconds,
            "errors": self.errors,
            "warnings": self.warnings,
        }


@dataclass
class IngestionResult:
    """Result of an ingestion operation"""
    success: bool
    total_files: int
    processed_files: int
    failed_files: int
    skipped_files: int

    documents: List[IngestedDocument] = field(default_factory=list)
    total_chunks: int = 0

    start_time: datetime = field(default_factory=datetime.now)
    end_time: Optional[datetime] = None
    duration_seconds: float = 0.0

    errors: List[Dict[str, str]] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    def add_document(self, doc: IngestedDocument):
        """Add a processed document"""
        self.documents.append(doc)
        self.total_chunks += len(doc.chunks)
        if doc.status == ProcessingStatus.COMPLETED:
            self.processed_files += 1
        elif doc.status == ProcessingStatus.FAILED:
            self.failed_files += 1
        elif doc.status == ProcessingStatus.SKIPPED:
            self.skipped_files += 1

    def add_error(self, file_path: str, error: str):
        """Add an error"""
        self.errors.append({"file": file_path, "error": error})

    def finalize(self):
        """Finalize the result"""
        self.end_time = datetime.now()
        self.duration_seconds = (self.end_time - self.start_time).total_seconds()
        self.success = self.failed_files == 0

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            "success": self.success,
            "total_files": self.total_files,
            "processed_files": self.processed_files,
            "failed_files": self.failed_files,
            "skipped_files": self.skipped_files,
            "total_chunks": self.total_chunks,
            "start_time": self.start_time.isoformat(),
            "end_time": self.end_time.isoformat() if self.end_time else None,
            "duration_seconds": self.duration_seconds,
            "errors": self.errors,
            "warnings": self.warnings,
            "documents": [d.document_id for d in self.documents],
        }


def compute_file_hash(filepath: str) -> str:
    """Compute SHA-256 hash of a file"""
    sha256 = hashlib.sha256()
    with open(filepath, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            sha256.update(chunk)
    return sha256.hexdigest()
