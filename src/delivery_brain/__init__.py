"""
Delivery Brain Data Ingestion Module

A multimodal data ingestion pipeline supporting:
- Text files (TXT, MD, XML)
- Documents (PDF, DOCX, PPTX)
- Media files (MP3, AVI, WMV, MP4)

Features:
- Automatic file type detection
- Text cleaning and normalization
- Audio/video transcription with diarization
- Intelligent chunking
- Dual storage (NoSQL + Vector DB)

All dependencies use permissive licenses (MIT, Apache-2.0, BSD).
"""

from .pipeline import DeliveryBrainPipeline
from .models import IngestedDocument, DocumentChunk, IngestionResult
from .config import IngestionConfig

__all__ = [
    "DeliveryBrainPipeline",
    "IngestedDocument",
    "DocumentChunk",
    "IngestionResult",
    "IngestionConfig",
]
