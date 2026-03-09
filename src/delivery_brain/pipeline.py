"""
Delivery Brain Data Ingestion Pipeline

Main orchestrator for multimodal data ingestion.
"""

import os
import logging
import hashlib
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Any, Optional, Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
import uuid

from .config import IngestionConfig
from .models import (
    IngestedDocument, DocumentChunk, DocumentMetadata,
    IngestionResult, FileType, ProcessingStatus,
    TranscriptionSegment, compute_file_hash
)
from .file_handlers import TextHandler, DocumentHandler, MediaHandler
from .processors import TextCleaner, TextChunker
from .storage import NoSQLStore, DeliveryBrainVectorStore

logger = logging.getLogger(__name__)


class DeliveryBrainPipeline:
    """
    Main ingestion pipeline for Delivery Brain.

    Handles:
    1. File discovery and type detection
    2. Content extraction (text, documents, media)
    3. Text cleaning and normalization
    4. Chunking for embeddings
    5. Storage in NoSQL and Vector databases
    """

    def __init__(self, config: IngestionConfig = None):
        """
        Initialize the pipeline.

        Args:
            config: Ingestion configuration (uses defaults if None)
        """
        self.config = config or IngestionConfig()

        # Initialize handlers
        self.text_handler = TextHandler()
        self.document_handler = DocumentHandler()
        self.media_handler = MediaHandler(
            whisper_model=self.config.transcription.model_size,
            device=self.config.transcription.device,
            enable_diarization=self.config.transcription.enable_diarization,
            min_speakers=self.config.transcription.min_speakers,
            max_speakers=self.config.transcription.max_speakers
        )

        # Initialize processors
        self.cleaner = TextCleaner(
            remove_extra_whitespace=self.config.cleaning.remove_extra_whitespace,
            fix_encoding=self.config.cleaning.fix_encoding,
            remove_special_chars=self.config.cleaning.remove_special_chars,
            lowercase=self.config.cleaning.lowercase,
            remove_urls=self.config.cleaning.remove_urls,
            remove_emails=self.config.cleaning.remove_emails,
            remove_phone_numbers=self.config.cleaning.remove_phone_numbers
        )

        self.chunker = TextChunker(
            chunk_size=self.config.chunking.chunk_size,
            chunk_overlap=self.config.chunking.chunk_overlap,
            min_chunk_size=self.config.chunking.min_chunk_size,
            split_by=self.config.chunking.split_by
        )

        # Initialize storage (lazy)
        self._nosql_store = None
        self._vector_store = None

        # Progress callback
        self.progress_callback: Optional[Callable] = None

    @property
    def nosql_store(self) -> NoSQLStore:
        """Lazy initialization of NoSQL store"""
        if self._nosql_store is None:
            self._nosql_store = NoSQLStore(
                store_type=self.config.storage.nosql_type,
                tinydb_path=self.config.storage.tinydb_path,
                mongodb_uri=self.config.storage.mongodb_uri,
                mongodb_database=self.config.storage.mongodb_database
            )
        return self._nosql_store

    @property
    def vector_store(self) -> DeliveryBrainVectorStore:
        """Lazy initialization of vector store"""
        if self._vector_store is None:
            self._vector_store = DeliveryBrainVectorStore(
                persist_directory=self.config.storage.chromadb_path,
                collection_name=self.config.storage.chromadb_collection,
                embedding_function=self.config.storage.embedding_model
            )
        return self._vector_store

    def ingest_directory(self,
                         directory: str,
                         recursive: bool = None,
                         file_filter: Callable[[str], bool] = None
                         ) -> IngestionResult:
        """
        Ingest all supported files from a directory.

        Args:
            directory: Path to directory to ingest
            recursive: Whether to scan subdirectories (uses config if None)
            file_filter: Optional filter function for files

        Returns:
            IngestionResult with processing summary
        """
        if recursive is None:
            recursive = self.config.recursive

        # Discover files
        files = self._discover_files(directory, recursive, file_filter)

        result = IngestionResult(
            success=True,
            total_files=len(files),
            processed_files=0,
            failed_files=0,
            skipped_files=0
        )

        logger.info(f"Starting ingestion of {len(files)} files from {directory}")

        # Process files
        # Note: TinyDB is not thread-safe, so force sequential processing when using it
        use_parallel = (
            self.config.parallel_processing and
            len(files) > 1 and
            self.config.storage.nosql_type != "tinydb"
        )
        if use_parallel:
            self._process_files_parallel(files, result)
        else:
            self._process_files_sequential(files, result)

        # Finalize result
        result.finalize()

        # Store ingestion metadata
        self.nosql_store.store_ingestion_metadata({
            "directory": directory,
            "total_files": result.total_files,
            "processed_files": result.processed_files,
            "failed_files": result.failed_files,
            "total_chunks": result.total_chunks,
            "duration_seconds": result.duration_seconds
        })

        logger.info(
            f"Ingestion complete: {result.processed_files}/{result.total_files} files, "
            f"{result.total_chunks} chunks, {result.duration_seconds:.2f}s"
        )

        return result

    def ingest_file(self, filepath: str) -> Optional[IngestedDocument]:
        """
        Ingest a single file.

        Args:
            filepath: Path to file

        Returns:
            IngestedDocument or None if failed
        """
        path = Path(filepath)
        if not path.exists():
            logger.error(f"File not found: {filepath}")
            return None

        # Check file size
        file_size = path.stat().st_size
        if file_size > self.config.max_file_size_mb * 1024 * 1024:
            logger.warning(f"File too large: {filepath} ({file_size / 1024 / 1024:.1f}MB)")
            return None

        # Determine file type and handler
        extension = path.suffix.lower()
        if extension not in self.config.supported_extensions:
            logger.warning(f"Unsupported file type: {extension}")
            return None

        try:
            start_time = datetime.now()

            # Extract content based on file type
            if self.config.is_text_file(filepath):
                content, metadata = self.text_handler.extract_content(filepath)
                file_type = self._get_text_file_type(extension)
                transcription_segments = None
            elif self.config.is_document_file(filepath):
                content, metadata = self.document_handler.extract_content(filepath)
                file_type = self._get_document_file_type(extension)
                transcription_segments = None
            elif self.config.is_media_file(filepath):
                content, metadata, transcription_segments = self.media_handler.extract_content(filepath)
                file_type = FileType.AUDIO if self.config.is_audio_file(filepath) else FileType.VIDEO
            else:
                logger.warning(f"No handler for: {filepath}")
                return None

            # Clean content
            cleaned_content = self.cleaner.clean(content)

            # Detect language if enabled
            if self.config.cleaning.language_detection:
                lang = self.cleaner.detect_language(cleaned_content[:1000])
                if lang:
                    metadata["language"] = lang

            # Create document metadata
            file_stat = path.stat()
            doc_metadata = DocumentMetadata(
                file_path=str(path.absolute()),
                file_name=path.name,
                file_type=file_type,
                file_size_bytes=file_stat.st_size,
                file_hash=compute_file_hash(filepath),
                created_at=datetime.fromtimestamp(file_stat.st_ctime),
                modified_at=datetime.fromtimestamp(file_stat.st_mtime),
                language=metadata.get("language"),
                encoding=metadata.get("encoding"),
                page_count=metadata.get("page_count"),
                word_count=metadata.get("word_count"),
                char_count=metadata.get("char_count"),
                duration_seconds=metadata.get("duration_seconds"),
                title=metadata.get("title"),
                author=metadata.get("author"),
                subject=metadata.get("subject"),
                custom=metadata
            )

            # Create chunks
            document_id = str(uuid.uuid4())
            chunk_infos = self.chunker.chunk(cleaned_content)

            chunks = []
            for i, chunk_info in enumerate(chunk_infos):
                chunk = DocumentChunk(
                    chunk_id=str(uuid.uuid4()),
                    document_id=document_id,
                    content=chunk_info.text,
                    chunk_index=i,
                    total_chunks=len(chunk_infos),
                    start_char=chunk_info.start_char,
                    end_char=chunk_info.end_char,
                    metadata={
                        "file_name": path.name,
                        "file_type": file_type.value,
                    }
                )
                chunks.append(chunk)

            # Calculate processing time
            processing_time = (datetime.now() - start_time).total_seconds()

            # Create ingested document
            document = IngestedDocument(
                document_id=document_id,
                metadata=doc_metadata,
                raw_content=content,
                cleaned_content=cleaned_content,
                chunks=chunks,
                status=ProcessingStatus.COMPLETED,
                transcription_segments=transcription_segments,
                processing_time_seconds=processing_time
            )

            # Store in databases
            self._store_document(document)

            logger.info(f"Ingested: {path.name} ({len(chunks)} chunks, {processing_time:.2f}s)")
            return document

        except Exception as e:
            logger.error(f"Error ingesting {filepath}: {e}")
            if self.config.log_errors:
                import traceback
                logger.debug(traceback.format_exc())
            return None

    def _discover_files(self,
                        directory: str,
                        recursive: bool,
                        file_filter: Callable = None) -> List[str]:
        """Discover files to process"""
        files = []
        dir_path = Path(directory)

        if not dir_path.exists():
            logger.error(f"Directory not found: {directory}")
            return files

        # Get files
        if recursive:
            pattern = "**/*"
        else:
            pattern = "*"

        for path in dir_path.glob(pattern):
            if path.is_file():
                ext = path.suffix.lower()
                if ext in self.config.supported_extensions:
                    if file_filter is None or file_filter(str(path)):
                        files.append(str(path))

        logger.info(f"Discovered {len(files)} files in {directory}")
        return files

    def _process_files_sequential(self, files: List[str], result: IngestionResult):
        """Process files sequentially"""
        for i, filepath in enumerate(files):
            if self.progress_callback:
                self.progress_callback(i + 1, len(files), filepath)

            try:
                doc = self.ingest_file(filepath)
                if doc:
                    result.add_document(doc)
                else:
                    result.skipped_files += 1
            except Exception as e:
                result.add_error(filepath, str(e))
                if not self.config.skip_on_error:
                    raise

    def _process_files_parallel(self, files: List[str], result: IngestionResult):
        """Process files in parallel"""
        with ThreadPoolExecutor(max_workers=self.config.max_workers) as executor:
            futures = {
                executor.submit(self.ingest_file, filepath): filepath
                for filepath in files
            }

            completed = 0
            for future in as_completed(futures):
                filepath = futures[future]
                completed += 1

                if self.progress_callback:
                    self.progress_callback(completed, len(files), filepath)

                try:
                    doc = future.result()
                    if doc:
                        result.add_document(doc)
                    else:
                        result.skipped_files += 1
                except Exception as e:
                    result.add_error(filepath, str(e))
                    if not self.config.skip_on_error:
                        raise

    def _store_document(self, document: IngestedDocument):
        """Store document in both NoSQL and Vector stores"""
        # Store document metadata in NoSQL
        doc_dict = document.to_dict()
        self.nosql_store.store_document(doc_dict)

        # Store chunks in NoSQL
        chunk_dicts = [chunk.to_dict() for chunk in document.chunks]
        self.nosql_store.store_chunks(chunk_dicts)

        # Store chunks in vector store
        vector_chunks = [
            {
                "chunk_id": chunk.chunk_id,
                "document_id": chunk.document_id,
                "content": chunk.content,
                "chunk_index": chunk.chunk_index,
                "total_chunks": chunk.total_chunks,
                "metadata": {
                    "file_name": document.metadata.file_name,
                    "file_type": document.metadata.file_type.value,
                }
            }
            for chunk in document.chunks
        ]
        self.vector_store.add_chunks(vector_chunks)

    def _get_text_file_type(self, extension: str) -> FileType:
        """Get FileType for text files"""
        mapping = {
            ".txt": FileType.TEXT,
            ".md": FileType.MARKDOWN,
            ".markdown": FileType.MARKDOWN,
            ".xml": FileType.XML,
            ".json": FileType.JSON,
            ".csv": FileType.CSV,
        }
        return mapping.get(extension, FileType.TEXT)

    def _get_document_file_type(self, extension: str) -> FileType:
        """Get FileType for document files"""
        mapping = {
            ".pdf": FileType.PDF,
            ".docx": FileType.DOCX,
            ".doc": FileType.DOCX,
            ".pptx": FileType.PPTX,
            ".ppt": FileType.PPTX,
            ".xlsx": FileType.XLSX,
            ".xls": FileType.XLSX,
        }
        return mapping.get(extension, FileType.UNKNOWN)

    def search(self, query: str, n_results: int = 10) -> List[Dict[str, Any]]:
        """
        Search ingested documents.

        Args:
            query: Search query
            n_results: Number of results

        Returns:
            List of search results with content and metadata
        """
        return self.vector_store.search(query, n_results)

    def get_statistics(self) -> Dict[str, Any]:
        """Get pipeline statistics"""
        return {
            "nosql": self.nosql_store.get_statistics(),
            "vector": self.vector_store.get_statistics(),
            "config": {
                "chunk_size": self.config.chunking.chunk_size,
                "supported_extensions": self.config.supported_extensions,
            }
        }

    def clear_all_data(self):
        """Clear all stored data (use with caution)"""
        self.nosql_store.clear_all()
        self.vector_store.clear_collection()
        logger.info("All data cleared")

    def close(self):
        """Close database connections"""
        if self._nosql_store:
            self._nosql_store.close()
