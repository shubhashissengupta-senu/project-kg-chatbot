"""
Document Store for RAG
Loads, chunks, and stores documents for retrieval.
"""

import os
import re
from pathlib import Path
from dataclasses import dataclass, field
from typing import List, Dict, Optional
from datetime import datetime
import hashlib


@dataclass
class DocumentChunk:
    """A chunk of text from a document"""
    chunk_id: str
    content: str
    source_file: str
    source_title: str
    chunk_index: int
    metadata: Dict = field(default_factory=dict)

    def to_dict(self) -> Dict:
        return {
            'chunk_id': self.chunk_id,
            'content': self.content,
            'source_file': self.source_file,
            'source_title': self.source_title,
            'chunk_index': self.chunk_index,
            'metadata': self.metadata
        }


class DocumentStore:
    """
    Stores and manages document chunks for retrieval.
    """

    def __init__(self, chunk_size: int = 500, chunk_overlap: int = 100):
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self.chunks: List[DocumentChunk] = []
        self.documents: Dict[str, str] = {}  # filename -> full content

    def load_directory(self, directory: Path) -> int:
        """Load all markdown files from a directory recursively"""
        directory = Path(directory)
        if not directory.exists():
            return 0

        count = 0
        for md_file in directory.rglob("*.md"):
            try:
                self.load_file(md_file)
                count += 1
            except Exception as e:
                print(f"Error loading {md_file}: {e}")

        return count

    def load_file(self, file_path: Path) -> List[DocumentChunk]:
        """Load and chunk a single file"""
        file_path = Path(file_path)

        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()

        # Store full document
        self.documents[str(file_path)] = content

        # Extract title
        title = self._extract_title(content, file_path.stem)

        # Extract date from filename if present
        date = self._extract_date(file_path.stem)

        # Extract document type for RBAC filtering
        doc_type = self._extract_document_type(file_path.stem)

        # Chunk the document
        chunks = self._chunk_document(content, str(file_path), title, date, doc_type)
        self.chunks.extend(chunks)

        return chunks

    def _extract_title(self, content: str, default: str) -> str:
        """Extract title from markdown content"""
        # Look for # heading
        match = re.search(r'^#\s+(.+)$', content, re.MULTILINE)
        if match:
            return match.group(1).strip()
        return default.replace('_', ' ').title()

    def _extract_document_type(self, filename: str) -> str:
        """Extract document type from filename for RBAC filtering"""
        filename_lower = filename.lower()

        if 'scrum' in filename_lower or 'sprint' in filename_lower:
            return 'Scrum'
        elif 'client_review' in filename_lower or 'client-review' in filename_lower:
            return 'ClientReview'
        elif 'qa_review' in filename_lower or 'qa-review' in filename_lower:
            return 'QAReview'
        elif 'finance' in filename_lower or 'financial' in filename_lower:
            return 'FinanceReview'
        elif 'delivery_review' in filename_lower or 'delivery-review' in filename_lower:
            return 'DeliveryReview'
        elif 'developer' in filename_lower or 'metric' in filename_lower:
            return 'DeveloperMetrics'
        else:
            return 'General'

    def _extract_date(self, filename: str) -> Optional[datetime]:
        """Extract date from filename"""
        # Pattern: Dec01_2025, Jan20_2026, etc.
        patterns = [
            r'(\w{3})(\d{1,2})_(\d{4})',  # Dec01_2025
            r'(\d{4})-(\d{2})-(\d{2})',    # 2025-12-01
        ]

        month_map = {
            'Jan': 1, 'Feb': 2, 'Mar': 3, 'Apr': 4, 'May': 5, 'Jun': 6,
            'Jul': 7, 'Aug': 8, 'Sep': 9, 'Oct': 10, 'Nov': 11, 'Dec': 12
        }

        for pattern in patterns:
            match = re.search(pattern, filename)
            if match:
                groups = match.groups()
                try:
                    if len(groups[0]) == 3:  # Month abbreviation
                        month = month_map.get(groups[0], 1)
                        day = int(groups[1])
                        year = int(groups[2])
                    else:  # ISO format
                        year = int(groups[0])
                        month = int(groups[1])
                        day = int(groups[2])
                    return datetime(year, month, day)
                except:
                    pass
        return None

    def _chunk_document(self, content: str, source_file: str,
                        title: str, date: Optional[datetime],
                        doc_type: str = 'General') -> List[DocumentChunk]:
        """Split document into chunks"""
        chunks = []

        # Split by sections (## headings) first
        sections = self._split_by_sections(content)

        chunk_index = 0
        for section_title, section_content in sections:
            # Further chunk if section is too long
            text_chunks = self._split_text(section_content)

            for text in text_chunks:
                if len(text.strip()) < 50:  # Skip very short chunks
                    continue

                chunk_id = hashlib.md5(
                    f"{source_file}:{chunk_index}".encode()
                ).hexdigest()[:12]

                metadata = {
                    'section': section_title,
                    'document_type': doc_type,  # For RBAC filtering
                }
                if date:
                    metadata['date'] = date.isoformat()
                    metadata['date_str'] = date.strftime('%B %d, %Y')

                chunk = DocumentChunk(
                    chunk_id=chunk_id,
                    content=text.strip(),
                    source_file=source_file,
                    source_title=title,
                    chunk_index=chunk_index,
                    metadata=metadata
                )
                chunks.append(chunk)
                chunk_index += 1

        return chunks

    def _split_by_sections(self, content: str) -> List[tuple]:
        """Split content by markdown sections"""
        sections = []
        current_title = "Introduction"
        current_content = []

        for line in content.split('\n'):
            if line.startswith('## '):
                # Save previous section
                if current_content:
                    sections.append((current_title, '\n'.join(current_content)))
                current_title = line[3:].strip()
                current_content = []
            elif line.startswith('# '):
                # Main title - include in intro
                current_content.append(line)
            else:
                current_content.append(line)

        # Don't forget the last section
        if current_content:
            sections.append((current_title, '\n'.join(current_content)))

        return sections

    def _split_text(self, text: str) -> List[str]:
        """Split text into chunks of approximately chunk_size"""
        if len(text) <= self.chunk_size:
            return [text]

        chunks = []

        # Split by paragraphs first
        paragraphs = text.split('\n\n')
        current_chunk = []
        current_length = 0

        for para in paragraphs:
            para_length = len(para)

            if current_length + para_length > self.chunk_size and current_chunk:
                # Save current chunk
                chunks.append('\n\n'.join(current_chunk))
                # Start new chunk with overlap
                if self.chunk_overlap > 0 and current_chunk:
                    overlap_text = current_chunk[-1][-self.chunk_overlap:]
                    current_chunk = [overlap_text]
                    current_length = len(overlap_text)
                else:
                    current_chunk = []
                    current_length = 0

            current_chunk.append(para)
            current_length += para_length

        if current_chunk:
            chunks.append('\n\n'.join(current_chunk))

        return chunks

    def get_all_chunks(self) -> List[DocumentChunk]:
        """Get all stored chunks"""
        return self.chunks

    def get_chunk_by_id(self, chunk_id: str) -> Optional[DocumentChunk]:
        """Get a specific chunk by ID"""
        for chunk in self.chunks:
            if chunk.chunk_id == chunk_id:
                return chunk
        return None

    def get_document(self, source_file: str) -> Optional[str]:
        """Get full document content"""
        return self.documents.get(source_file)

    def stats(self) -> Dict:
        """Get store statistics"""
        return {
            'total_documents': len(self.documents),
            'total_chunks': len(self.chunks),
            'avg_chunk_size': sum(len(c.content) for c in self.chunks) / len(self.chunks) if self.chunks else 0
        }
