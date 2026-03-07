"""
Base Parser - Abstract base class for all document parsers
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional
import re


@dataclass
class ParsedEntity:
    """Represents an extracted entity"""
    entity_type: str
    entity_id: str
    properties: Dict[str, Any]
    source_file: str
    source_line: Optional[int] = None


@dataclass
class ParsedRelationship:
    """Represents an extracted relationship"""
    relation_type: str
    from_entity: str
    to_entity: str
    properties: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ParsedDocument:
    """Result of parsing a document"""
    document_type: str
    source_file: str
    timestamp: datetime
    entities: List[ParsedEntity] = field(default_factory=list)
    relationships: List[ParsedRelationship] = field(default_factory=list)
    metrics: Dict[str, Any] = field(default_factory=dict)
    raw_text: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)


class BaseParser(ABC):
    """Abstract base class for document parsers"""

    # Common regex patterns
    DATE_PATTERNS = [
        (r'\*\*Date:\*\*\s*(\w+,\s*\w+\s+\d+,\s+\d+)', '%A, %B %d, %Y'),
        (r'(\d{4}-\d{2}-\d{2})', '%Y-%m-%d'),
        (r'(\w+\s+\d+,\s+\d{4})', '%B %d, %Y'),
        (r'(\d{1,2}/\d{1,2}/\d{4})', '%m/%d/%Y'),
    ]

    TABLE_ROW_PATTERN = r'\|([^|]+(?:\|[^|]+)*)\|'

    def __init__(self, known_entities: Dict[str, List[str]] = None):
        """
        Initialize parser with known entities for better extraction.

        Args:
            known_entities: Dict mapping entity types to known values
                           e.g., {"Person": ["Ryan", "Dhyanesh"], "Stream": ["SD", "EWM"]}
        """
        self.known_entities = known_entities or {}

    @abstractmethod
    def parse(self, filepath: Path) -> ParsedDocument:
        """Parse a document and return structured data"""
        pass

    @abstractmethod
    def can_parse(self, filepath: Path) -> bool:
        """Check if this parser can handle the given file"""
        pass

    def extract_date(self, content: str) -> Optional[datetime]:
        """Extract date from content using multiple patterns"""
        for pattern, fmt in self.DATE_PATTERNS:
            match = re.search(pattern, content)
            if match:
                try:
                    return datetime.strptime(match.group(1), fmt)
                except ValueError:
                    continue
        return None

    def extract_tables(self, content: str) -> List[List[List[str]]]:
        """Extract all markdown tables from content"""
        tables = []
        lines = content.split('\n')
        current_table = []
        in_table = False

        for line in lines:
            line = line.strip()
            if line.startswith('|') and line.endswith('|'):
                if '---' in line:
                    # Header separator, skip
                    continue
                cells = [c.strip() for c in line.split('|')[1:-1]]
                current_table.append(cells)
                in_table = True
            else:
                if in_table and current_table:
                    tables.append(current_table)
                    current_table = []
                in_table = False

        if current_table:
            tables.append(current_table)

        return tables

    def extract_section(self, content: str, section_name: str) -> str:
        """Extract content under a specific markdown section"""
        pattern = rf'##\s*{re.escape(section_name)}\s*\n(.*?)(?=\n##|\Z)'
        match = re.search(pattern, content, re.DOTALL | re.IGNORECASE)
        return match.group(1).strip() if match else ""

    def extract_bullet_points(self, content: str) -> List[str]:
        """Extract bullet points from content"""
        pattern = r'^[\s]*[-*]\s+(.+)$'
        return re.findall(pattern, content, re.MULTILINE)

    def extract_numbered_list(self, content: str) -> List[str]:
        """Extract numbered list items from content"""
        pattern = r'^\d+\.\s+(.+)$'
        return re.findall(pattern, content, re.MULTILINE)

    def extract_quotes(self, content: str) -> List[Dict[str, str]]:
        """Extract quoted text with optional speaker"""
        quotes = []

        # Pattern: **Speaker:** "quote" or **Speaker:** 'quote'
        speaker_pattern = r'\*\*(\w+)(?:\s+\w+)?:\*\*\s*["\']([^"\']+)["\']'
        for match in re.finditer(speaker_pattern, content):
            quotes.append({
                "speaker": match.group(1),
                "quote": match.group(2)
            })

        # Pattern: > blockquote
        blockquote_pattern = r'>\s*["\']?([^"\'\n]+)["\']?'
        for match in re.finditer(blockquote_pattern, content):
            quotes.append({
                "speaker": "Unknown",
                "quote": match.group(1)
            })

        return quotes

    def extract_key_value_pairs(self, content: str) -> Dict[str, str]:
        """Extract key-value pairs like **Key:** Value"""
        pattern = r'\*\*([^*]+):\*\*\s*(.+?)(?=\n|$)'
        pairs = {}
        for match in re.finditer(pattern, content):
            key = match.group(1).strip()
            value = match.group(2).strip()
            pairs[key] = value
        return pairs

    def normalize_status(self, status: str) -> str:
        """Normalize status values to standard enum"""
        status_lower = status.lower().strip()

        status_map = {
            # Project/Stream status
            'green': 'Green',
            'amber': 'Amber',
            'red': 'Red',
            'on track': 'Green',
            'at risk': 'Amber',
            'critical': 'Red',

            # Task status
            'not started': 'NotStarted',
            'in progress': 'InProgress',
            'complete': 'Complete',
            'completed': 'Complete',
            'done': 'Complete',
            'blocked': 'Blocked',

            # Risk status
            'open': 'Open',
            'mitigating': 'Mitigating',
            'closed': 'Closed',
            'materialized': 'Materialized',

            # Person status
            'active': 'Active',
            'on leave': 'OnLeave',
            'departed': 'Departed',
            'present': 'Active',
            'absent': 'OnLeave',
        }

        return status_map.get(status_lower, status)

    def normalize_severity(self, severity: str) -> str:
        """Normalize severity values"""
        severity_lower = severity.lower().strip()
        severity_map = {
            'low': 'Low',
            'medium': 'Medium',
            'med': 'Medium',
            'high': 'High',
            'critical': 'Critical',
            'crit': 'Critical',
            'p1': 'Critical',
            'p2': 'High',
            'p3': 'Medium',
            'p4': 'Low',
        }
        return severity_map.get(severity_lower, severity)

    def parse_date_flexible(self, date_str: str, default_year: int = 2026) -> Optional[datetime]:
        """Parse date with flexible formats"""
        if not date_str or date_str.strip() == '-':
            return None

        date_str = date_str.strip()

        formats = [
            '%Y-%m-%d',
            '%b %d, %Y',
            '%B %d, %Y',
            '%b %d',
            '%B %d',
            '%d/%m/%Y',
            '%m/%d/%Y',
        ]

        for fmt in formats:
            try:
                dt = datetime.strptime(date_str, fmt)
                # If year is 1900 (no year in format), use default
                if dt.year == 1900:
                    dt = dt.replace(year=default_year)
                return dt
            except ValueError:
                continue

        return None
