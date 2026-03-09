"""
Text Chunker for Delivery Brain

Provides intelligent text chunking for embeddings.
Uses only standard library - no external dependencies required.
"""

import re
import logging
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class ChunkInfo:
    """Information about a text chunk"""
    text: str
    index: int
    start_char: int
    end_char: int
    metadata: Dict[str, Any] = None

    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}


class TextChunker:
    """
    Intelligent text chunking for vector embeddings.

    Supports multiple splitting strategies:
    - sentence: Split by sentences (best for narrative text)
    - paragraph: Split by paragraphs (best for structured documents)
    - fixed: Split by fixed character count (fallback)
    - semantic: Split by semantic boundaries (headings, sections)
    """

    # Sentence boundary patterns
    SENTENCE_PATTERN = re.compile(
        r'(?<=[.!?])\s+(?=[A-Z])|(?<=[.!?])\s*\n+'
    )

    # Paragraph boundary pattern
    PARAGRAPH_PATTERN = re.compile(r'\n\s*\n+')

    # Section/heading patterns
    HEADING_PATTERN = re.compile(
        r'^(?:#+\s+.+|[A-Z][^a-z]*:|\d+\.\s+[A-Z]|\*\*[^*]+\*\*)',
        re.MULTILINE
    )

    def __init__(self,
                 chunk_size: int = 1000,
                 chunk_overlap: int = 200,
                 min_chunk_size: int = 100,
                 split_by: str = "sentence",
                 respect_boundaries: bool = True):
        """
        Initialize text chunker.

        Args:
            chunk_size: Target chunk size in characters
            chunk_overlap: Overlap between chunks in characters
            min_chunk_size: Minimum chunk size
            split_by: Splitting strategy (sentence, paragraph, fixed, semantic)
            respect_boundaries: Try to split at natural boundaries
        """
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self.min_chunk_size = min_chunk_size
        self.split_by = split_by
        self.respect_boundaries = respect_boundaries

    def chunk(self, text: str) -> List[ChunkInfo]:
        """
        Split text into chunks.

        Args:
            text: Input text to chunk

        Returns:
            List of ChunkInfo objects
        """
        if not text or len(text) < self.min_chunk_size:
            if text:
                return [ChunkInfo(
                    text=text,
                    index=0,
                    start_char=0,
                    end_char=len(text)
                )]
            return []

        if self.split_by == "sentence":
            return self._chunk_by_sentences(text)
        elif self.split_by == "paragraph":
            return self._chunk_by_paragraphs(text)
        elif self.split_by == "semantic":
            return self._chunk_by_semantic(text)
        else:  # fixed
            return self._chunk_by_fixed(text)

    def _chunk_by_sentences(self, text: str) -> List[ChunkInfo]:
        """Split by sentences, combining to target size"""
        sentences = self._split_sentences(text)
        return self._combine_into_chunks(sentences, text)

    def _chunk_by_paragraphs(self, text: str) -> List[ChunkInfo]:
        """Split by paragraphs, combining to target size"""
        paragraphs = self.PARAGRAPH_PATTERN.split(text)
        paragraphs = [p.strip() for p in paragraphs if p.strip()]
        return self._combine_into_chunks(paragraphs, text)

    def _chunk_by_semantic(self, text: str) -> List[ChunkInfo]:
        """Split by semantic boundaries (headings, sections)"""
        # Find all heading positions
        sections = []
        last_end = 0

        for match in self.HEADING_PATTERN.finditer(text):
            if match.start() > last_end:
                # Add content before this heading
                content = text[last_end:match.start()].strip()
                if content:
                    sections.append(content)
            last_end = match.start()

        # Add remaining content
        if last_end < len(text):
            content = text[last_end:].strip()
            if content:
                sections.append(content)

        if not sections:
            # Fallback to paragraph splitting
            return self._chunk_by_paragraphs(text)

        return self._combine_into_chunks(sections, text)

    def _chunk_by_fixed(self, text: str) -> List[ChunkInfo]:
        """Split by fixed character count with overlap"""
        chunks = []
        start = 0
        index = 0

        while start < len(text):
            # Calculate end position
            end = start + self.chunk_size

            if end >= len(text):
                # Last chunk
                chunk_text = text[start:].strip()
                if chunk_text and len(chunk_text) >= self.min_chunk_size:
                    chunks.append(ChunkInfo(
                        text=chunk_text,
                        index=index,
                        start_char=start,
                        end_char=len(text)
                    ))
                break

            # Find a good break point if respecting boundaries
            if self.respect_boundaries:
                # Look for sentence boundary
                break_pos = self._find_break_point(text, end)
                if break_pos > start:
                    end = break_pos

            chunk_text = text[start:end].strip()
            if chunk_text and len(chunk_text) >= self.min_chunk_size:
                chunks.append(ChunkInfo(
                    text=chunk_text,
                    index=index,
                    start_char=start,
                    end_char=end
                ))
                index += 1

            # Move start with overlap
            start = end - self.chunk_overlap
            if start <= chunks[-1].start_char if chunks else 0:
                start = end  # Prevent infinite loop

        return chunks

    def _split_sentences(self, text: str) -> List[str]:
        """Split text into sentences"""
        # Use regex to split while keeping delimiters
        parts = self.SENTENCE_PATTERN.split(text)
        sentences = [p.strip() for p in parts if p.strip()]

        # Handle case where regex doesn't split well
        if len(sentences) <= 1 and len(text) > self.chunk_size:
            # Fallback: split on periods
            sentences = [s.strip() + '.' for s in text.split('.') if s.strip()]

        return sentences

    def _combine_into_chunks(self, parts: List[str], original_text: str) -> List[ChunkInfo]:
        """Combine parts into chunks of target size"""
        chunks = []
        current_parts = []
        current_length = 0
        current_start = 0

        for part in parts:
            part_length = len(part)

            # Check if adding this part exceeds target size
            if current_length + part_length > self.chunk_size and current_parts:
                # Save current chunk
                chunk_text = ' '.join(current_parts)
                chunk_end = current_start + len(chunk_text)

                chunks.append(ChunkInfo(
                    text=chunk_text,
                    index=len(chunks),
                    start_char=current_start,
                    end_char=chunk_end
                ))

                # Handle overlap
                if self.chunk_overlap > 0:
                    # Keep some parts for overlap
                    overlap_parts = []
                    overlap_length = 0
                    for p in reversed(current_parts):
                        if overlap_length + len(p) <= self.chunk_overlap:
                            overlap_parts.insert(0, p)
                            overlap_length += len(p) + 1
                        else:
                            break
                    current_parts = overlap_parts
                    current_length = overlap_length
                    current_start = chunk_end - overlap_length
                else:
                    current_parts = []
                    current_length = 0
                    current_start = chunk_end

            current_parts.append(part)
            current_length += part_length + 1  # +1 for space

        # Add remaining parts
        if current_parts:
            chunk_text = ' '.join(current_parts)
            if len(chunk_text) >= self.min_chunk_size:
                chunks.append(ChunkInfo(
                    text=chunk_text,
                    index=len(chunks),
                    start_char=current_start,
                    end_char=current_start + len(chunk_text)
                ))

        return chunks

    def _find_break_point(self, text: str, position: int) -> int:
        """Find a good break point near the position"""
        # Search window
        search_start = max(0, position - 100)
        search_end = min(len(text), position + 100)
        search_text = text[search_start:search_end]

        # Look for sentence boundaries
        for pattern in ['. ', '! ', '? ', '.\n', '!\n', '?\n']:
            idx = search_text.rfind(pattern, 0, position - search_start + 50)
            if idx != -1:
                return search_start + idx + len(pattern)

        # Look for paragraph boundary
        idx = search_text.rfind('\n\n', 0, position - search_start + 50)
        if idx != -1:
            return search_start + idx + 2

        # Look for any newline
        idx = search_text.rfind('\n', 0, position - search_start + 50)
        if idx != -1:
            return search_start + idx + 1

        return position

    def chunk_with_metadata(self,
                            text: str,
                            document_id: str,
                            base_metadata: Dict[str, Any] = None
                            ) -> List[Dict[str, Any]]:
        """
        Chunk text and return with full metadata for storage.

        Args:
            text: Input text
            document_id: Document identifier
            base_metadata: Base metadata to include in each chunk

        Returns:
            List of chunk dictionaries ready for storage
        """
        chunks = self.chunk(text)
        total_chunks = len(chunks)

        result = []
        for chunk in chunks:
            chunk_dict = {
                "document_id": document_id,
                "chunk_index": chunk.index,
                "total_chunks": total_chunks,
                "content": chunk.text,
                "start_char": chunk.start_char,
                "end_char": chunk.end_char,
                "char_count": len(chunk.text),
                "word_count": len(chunk.text.split()),
            }

            if base_metadata:
                chunk_dict["metadata"] = base_metadata.copy()

            result.append(chunk_dict)

        return result


# Convenience functions
def chunk_text(text: str,
               chunk_size: int = 1000,
               overlap: int = 200,
               split_by: str = "sentence") -> List[str]:
    """Chunk text and return just the text chunks"""
    chunker = TextChunker(
        chunk_size=chunk_size,
        chunk_overlap=overlap,
        split_by=split_by
    )
    chunks = chunker.chunk(text)
    return [c.text for c in chunks]
