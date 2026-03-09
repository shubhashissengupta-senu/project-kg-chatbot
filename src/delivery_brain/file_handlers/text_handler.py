"""
Text File Handler for Delivery Brain

Handles: TXT, MD, Markdown, XML, JSON, CSV files
License-compliant dependencies: chardet (LGPL), lxml (BSD)
"""

import json
import csv
import re
import logging
from pathlib import Path
from typing import Optional, Dict, Any, Tuple
from datetime import datetime
from io import StringIO

logger = logging.getLogger(__name__)


class TextHandler:
    """Handler for text-based files"""

    SUPPORTED_EXTENSIONS = [".txt", ".md", ".markdown", ".xml", ".json", ".csv"]

    def __init__(self):
        self._chardet_available = False
        self._lxml_available = False
        self._check_dependencies()

    def _check_dependencies(self):
        """Check for optional dependencies"""
        try:
            import chardet
            self._chardet_available = True
        except ImportError:
            logger.warning("chardet not available - encoding detection limited")

        try:
            import lxml
            self._lxml_available = True
        except ImportError:
            logger.warning("lxml not available - XML parsing limited")

    def can_handle(self, filepath: str) -> bool:
        """Check if this handler can process the file"""
        return Path(filepath).suffix.lower() in self.SUPPORTED_EXTENSIONS

    def detect_encoding(self, filepath: str) -> str:
        """Detect file encoding"""
        if self._chardet_available:
            import chardet
            with open(filepath, "rb") as f:
                raw_data = f.read(10000)  # Read first 10KB
                result = chardet.detect(raw_data)
                return result.get("encoding", "utf-8") or "utf-8"
        return "utf-8"

    def extract_content(self, filepath: str) -> Tuple[str, Dict[str, Any]]:
        """
        Extract content from a text file.

        Returns:
            Tuple of (content, metadata)
        """
        path = Path(filepath)
        extension = path.suffix.lower()
        metadata = {
            "file_type": extension[1:],  # Remove dot
            "file_name": path.name,
        }

        # Detect encoding
        encoding = self.detect_encoding(filepath)
        metadata["encoding"] = encoding

        try:
            with open(filepath, "r", encoding=encoding, errors="replace") as f:
                raw_content = f.read()
        except Exception as e:
            logger.error(f"Error reading file {filepath}: {e}")
            raise

        # Process based on file type
        if extension == ".json":
            content, json_metadata = self._process_json(raw_content)
            metadata.update(json_metadata)
        elif extension == ".xml":
            content, xml_metadata = self._process_xml(raw_content)
            metadata.update(xml_metadata)
        elif extension == ".csv":
            content, csv_metadata = self._process_csv(raw_content)
            metadata.update(csv_metadata)
        elif extension in [".md", ".markdown"]:
            content, md_metadata = self._process_markdown(raw_content)
            metadata.update(md_metadata)
        else:
            content = raw_content

        # Calculate basic stats
        metadata["char_count"] = len(content)
        metadata["word_count"] = len(content.split())
        metadata["line_count"] = content.count("\n") + 1

        return content, metadata

    def _process_json(self, content: str) -> Tuple[str, Dict[str, Any]]:
        """Process JSON content"""
        metadata = {"json_valid": False}

        try:
            data = json.loads(content)
            metadata["json_valid"] = True

            # Convert to readable text
            if isinstance(data, dict):
                text_parts = []
                for key, value in data.items():
                    text_parts.append(f"{key}: {json.dumps(value, indent=2)}")
                content = "\n\n".join(text_parts)
                metadata["json_keys"] = list(data.keys())
            elif isinstance(data, list):
                content = "\n".join(json.dumps(item, indent=2) for item in data)
                metadata["json_items"] = len(data)

        except json.JSONDecodeError as e:
            logger.warning(f"Invalid JSON: {e}")
            metadata["json_error"] = str(e)

        return content, metadata

    def _process_xml(self, content: str) -> Tuple[str, Dict[str, Any]]:
        """Process XML content"""
        metadata = {"xml_valid": False}

        if self._lxml_available:
            try:
                from lxml import etree
                root = etree.fromstring(content.encode())
                metadata["xml_valid"] = True
                metadata["xml_root"] = root.tag

                # Extract text content
                text_parts = []
                for elem in root.iter():
                    if elem.text and elem.text.strip():
                        text_parts.append(elem.text.strip())
                    if elem.tail and elem.tail.strip():
                        text_parts.append(elem.tail.strip())

                content = "\n".join(text_parts)
                metadata["xml_elements"] = len(list(root.iter()))

            except Exception as e:
                logger.warning(f"XML parsing error: {e}")
                metadata["xml_error"] = str(e)
        else:
            # Fallback: strip XML tags with regex
            content = re.sub(r"<[^>]+>", " ", content)
            content = re.sub(r"\s+", " ", content).strip()

        return content, metadata

    def _process_csv(self, content: str) -> Tuple[str, Dict[str, Any]]:
        """Process CSV content"""
        metadata = {"csv_valid": False}

        try:
            reader = csv.reader(StringIO(content))
            rows = list(reader)

            if rows:
                metadata["csv_valid"] = True
                metadata["csv_columns"] = len(rows[0]) if rows else 0
                metadata["csv_rows"] = len(rows)

                # Check if first row is header
                if rows and not any(cell.isdigit() for cell in rows[0]):
                    metadata["csv_headers"] = rows[0]

                # Convert to readable format
                text_parts = []
                for i, row in enumerate(rows):
                    text_parts.append(" | ".join(row))

                content = "\n".join(text_parts)

        except csv.Error as e:
            logger.warning(f"CSV parsing error: {e}")
            metadata["csv_error"] = str(e)

        return content, metadata

    def _process_markdown(self, content: str) -> Tuple[str, Dict[str, Any]]:
        """Process Markdown content"""
        metadata = {}

        # Extract title from first heading
        title_match = re.search(r"^#\s+(.+)$", content, re.MULTILINE)
        if title_match:
            metadata["title"] = title_match.group(1).strip()

        # Count headings
        headings = re.findall(r"^#+\s+.+$", content, re.MULTILINE)
        metadata["heading_count"] = len(headings)

        # Count code blocks
        code_blocks = re.findall(r"```[\s\S]*?```", content)
        metadata["code_block_count"] = len(code_blocks)

        # Count links
        links = re.findall(r"\[([^\]]+)\]\(([^\)]+)\)", content)
        metadata["link_count"] = len(links)

        # Strip markdown formatting for cleaner text (optional)
        # For now, keep markdown as-is since it's readable

        return content, metadata


# Convenience function
def extract_text_content(filepath: str) -> Tuple[str, Dict[str, Any]]:
    """Extract content from a text file"""
    handler = TextHandler()
    return handler.extract_content(filepath)
