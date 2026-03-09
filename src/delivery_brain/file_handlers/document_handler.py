"""
Document File Handler for Delivery Brain

Handles: PDF, DOCX, PPTX, XLSX files
License-compliant dependencies:
- pypdf (BSD-3-Clause) for PDF
- python-docx (MIT) for Word documents
- python-pptx (MIT) for PowerPoint
- openpyxl (MIT) for Excel
"""

import logging
from pathlib import Path
from typing import Optional, Dict, Any, Tuple, List
from datetime import datetime

logger = logging.getLogger(__name__)


class DocumentHandler:
    """Handler for document files (PDF, DOCX, PPTX, XLSX)"""

    SUPPORTED_EXTENSIONS = [".pdf", ".docx", ".doc", ".pptx", ".ppt", ".xlsx", ".xls"]

    def __init__(self):
        self._pypdf_available = False
        self._docx_available = False
        self._pptx_available = False
        self._openpyxl_available = False
        self._check_dependencies()

    def _check_dependencies(self):
        """Check for required dependencies"""
        try:
            import pypdf
            self._pypdf_available = True
        except ImportError:
            logger.warning("pypdf not available - PDF extraction disabled")

        try:
            import docx
            self._docx_available = True
        except ImportError:
            logger.warning("python-docx not available - DOCX extraction disabled")

        try:
            import pptx
            self._pptx_available = True
        except ImportError:
            logger.warning("python-pptx not available - PPTX extraction disabled")

        try:
            import openpyxl
            self._openpyxl_available = True
        except ImportError:
            logger.warning("openpyxl not available - XLSX extraction disabled")

    def can_handle(self, filepath: str) -> bool:
        """Check if this handler can process the file"""
        ext = Path(filepath).suffix.lower()
        if ext not in self.SUPPORTED_EXTENSIONS:
            return False

        # Check if we have the required library
        if ext == ".pdf":
            return self._pypdf_available
        elif ext in [".docx", ".doc"]:
            return self._docx_available
        elif ext in [".pptx", ".ppt"]:
            return self._pptx_available
        elif ext in [".xlsx", ".xls"]:
            return self._openpyxl_available

        return False

    def extract_content(self,
                        filepath: str,
                        page_start: int = None,
                        page_end: int = None) -> Tuple[str, Dict[str, Any]]:
        """
        Extract content from a document file.

        Args:
            filepath: Path to the document
            page_start: Starting page (1-indexed, inclusive). None = start from first page.
            page_end: Ending page (1-indexed, inclusive). None = read to last page.

        Returns:
            Tuple of (content, metadata)
        """
        path = Path(filepath)
        extension = path.suffix.lower()
        metadata = {
            "file_type": extension[1:],
            "file_name": path.name,
        }

        try:
            if extension == ".pdf":
                content, doc_metadata = self._extract_pdf(filepath, page_start, page_end)
            elif extension in [".docx", ".doc"]:
                content, doc_metadata = self._extract_docx(filepath)
            elif extension in [".pptx", ".ppt"]:
                content, doc_metadata = self._extract_pptx(filepath)
            elif extension in [".xlsx", ".xls"]:
                content, doc_metadata = self._extract_xlsx(filepath)
            else:
                raise ValueError(f"Unsupported extension: {extension}")

            metadata.update(doc_metadata)

        except Exception as e:
            logger.error(f"Error extracting content from {filepath}: {e}")
            raise

        # Calculate basic stats
        metadata["char_count"] = len(content)
        metadata["word_count"] = len(content.split())

        return content, metadata

    def _extract_pdf(self,
                     filepath: str,
                     page_start: int = None,
                     page_end: int = None) -> Tuple[str, Dict[str, Any]]:
        """
        Extract content from PDF file.

        Args:
            filepath: Path to PDF file
            page_start: Starting page (1-indexed, inclusive). None = first page.
            page_end: Ending page (1-indexed, inclusive). None = last page.

        Returns:
            Tuple of (content, metadata)
        """
        import pypdf

        metadata = {}
        text_parts = []

        with open(filepath, "rb") as f:
            reader = pypdf.PdfReader(f)
            total_pages = len(reader.pages)
            metadata["page_count"] = total_pages

            # Calculate page range (convert to 0-indexed)
            start_idx = (page_start - 1) if page_start and page_start > 0 else 0
            end_idx = page_end if page_end and page_end <= total_pages else total_pages

            # Validate range
            if start_idx >= total_pages:
                start_idx = 0
            if end_idx < start_idx:
                end_idx = total_pages

            metadata["pages_extracted"] = f"{start_idx + 1}-{end_idx}"
            metadata["pages_extracted_count"] = end_idx - start_idx

            # Extract document info
            if reader.metadata:
                if reader.metadata.title:
                    metadata["title"] = reader.metadata.title
                if reader.metadata.author:
                    metadata["author"] = reader.metadata.author
                if reader.metadata.subject:
                    metadata["subject"] = reader.metadata.subject
                if reader.metadata.creator:
                    metadata["creator"] = reader.metadata.creator

            # Extract text from selected pages
            for i in range(start_idx, end_idx):
                page = reader.pages[i]
                try:
                    page_text = page.extract_text()
                    if page_text:
                        text_parts.append(f"[Page {i + 1}]\n{page_text}")
                except Exception as e:
                    logger.warning(f"Error extracting page {i + 1}: {e}")
                    text_parts.append(f"[Page {i + 1}] - Error extracting text")

        content = "\n\n".join(text_parts)
        return content, metadata

    def _extract_docx(self, filepath: str) -> Tuple[str, Dict[str, Any]]:
        """Extract content from DOCX file"""
        from docx import Document

        metadata = {}
        text_parts = []

        doc = Document(filepath)

        # Extract core properties
        try:
            if doc.core_properties.title:
                metadata["title"] = doc.core_properties.title
            if doc.core_properties.author:
                metadata["author"] = doc.core_properties.author
            if doc.core_properties.subject:
                metadata["subject"] = doc.core_properties.subject
            if doc.core_properties.keywords:
                metadata["keywords"] = doc.core_properties.keywords
            if doc.core_properties.created:
                metadata["created"] = doc.core_properties.created.isoformat()
            if doc.core_properties.modified:
                metadata["modified"] = doc.core_properties.modified.isoformat()
        except Exception as e:
            logger.warning(f"Error extracting DOCX properties: {e}")

        # Extract paragraphs
        for para in doc.paragraphs:
            if para.text.strip():
                # Include heading style info
                if para.style and para.style.name.startswith("Heading"):
                    text_parts.append(f"\n[{para.style.name}] {para.text}\n")
                else:
                    text_parts.append(para.text)

        # Extract tables
        for table in doc.tables:
            table_text = []
            for row in table.rows:
                row_text = [cell.text.strip() for cell in row.cells]
                table_text.append(" | ".join(row_text))
            if table_text:
                text_parts.append("\n[Table]\n" + "\n".join(table_text))

        metadata["paragraph_count"] = len(doc.paragraphs)
        metadata["table_count"] = len(doc.tables)

        content = "\n".join(text_parts)
        return content, metadata

    def _extract_pptx(self, filepath: str) -> Tuple[str, Dict[str, Any]]:
        """Extract content from PPTX file"""
        from pptx import Presentation

        metadata = {}
        text_parts = []

        prs = Presentation(filepath)

        # Extract core properties
        try:
            if prs.core_properties.title:
                metadata["title"] = prs.core_properties.title
            if prs.core_properties.author:
                metadata["author"] = prs.core_properties.author
            if prs.core_properties.subject:
                metadata["subject"] = prs.core_properties.subject
        except Exception as e:
            logger.warning(f"Error extracting PPTX properties: {e}")

        metadata["slide_count"] = len(prs.slides)

        # Extract text from each slide
        for i, slide in enumerate(prs.slides):
            slide_text = [f"\n[Slide {i + 1}]"]

            for shape in slide.shapes:
                if hasattr(shape, "text") and shape.text.strip():
                    slide_text.append(shape.text)

                # Extract text from tables
                if shape.has_table:
                    table = shape.table
                    for row in table.rows:
                        row_text = [cell.text.strip() for cell in row.cells]
                        slide_text.append(" | ".join(row_text))

            text_parts.append("\n".join(slide_text))

        # Extract notes
        notes_count = 0
        for slide in prs.slides:
            if slide.has_notes_slide:
                notes_frame = slide.notes_slide.notes_text_frame
                if notes_frame.text.strip():
                    notes_count += 1

        metadata["notes_count"] = notes_count

        content = "\n".join(text_parts)
        return content, metadata

    def _extract_xlsx(self, filepath: str) -> Tuple[str, Dict[str, Any]]:
        """Extract content from XLSX file"""
        from openpyxl import load_workbook

        metadata = {}
        text_parts = []

        wb = load_workbook(filepath, read_only=True, data_only=True)

        metadata["sheet_count"] = len(wb.sheetnames)
        metadata["sheet_names"] = wb.sheetnames

        # Extract content from each sheet
        for sheet_name in wb.sheetnames:
            sheet = wb[sheet_name]
            sheet_text = [f"\n[Sheet: {sheet_name}]"]

            row_count = 0
            for row in sheet.iter_rows(values_only=True):
                if any(cell is not None for cell in row):
                    row_text = [str(cell) if cell is not None else "" for cell in row]
                    sheet_text.append(" | ".join(row_text))
                    row_count += 1

            if row_count > 0:
                text_parts.append("\n".join(sheet_text))

        wb.close()

        content = "\n".join(text_parts)
        return content, metadata


# Convenience function
def extract_document_content(filepath: str) -> Tuple[str, Dict[str, Any]]:
    """Extract content from a document file"""
    handler = DocumentHandler()
    return handler.extract_content(filepath)
