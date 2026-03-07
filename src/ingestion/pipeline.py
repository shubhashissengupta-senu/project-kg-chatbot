"""
Ingestion Pipeline
Orchestrates document parsing and entity extraction.
"""

from pathlib import Path
from typing import List, Dict, Type, Optional
from datetime import datetime
import logging

from .parsers.base_parser import BaseParser, ParsedDocument
from .parsers.scrum_parser import ScrumMeetingParser
from .parsers.client_review_parser import ClientReviewParser
from .parsers.metrics_parser import MetricsParser

logger = logging.getLogger(__name__)


class IngestionPipeline:
    """
    Orchestrates the ingestion of project documents.
    Automatically selects appropriate parsers based on file type.
    """

    def __init__(self, known_entities: Dict[str, List[str]] = None):
        """
        Initialize pipeline with optional known entities.

        Args:
            known_entities: Dict of entity types to known values for better extraction
        """
        self.known_entities = known_entities or {}
        self.parsers: List[BaseParser] = [
            ScrumMeetingParser(known_entities),
            ClientReviewParser(known_entities),
            MetricsParser(known_entities),
        ]
        self.parsed_documents: List[ParsedDocument] = []

    def add_parser(self, parser: BaseParser):
        """Add a custom parser to the pipeline"""
        self.parsers.append(parser)

    def ingest_file(self, filepath: Path) -> Optional[ParsedDocument]:
        """
        Ingest a single file.

        Args:
            filepath: Path to the file to ingest

        Returns:
            ParsedDocument if successful, None otherwise
        """
        filepath = Path(filepath)

        if not filepath.exists():
            logger.error(f"File not found: {filepath}")
            return None

        if filepath.suffix != '.md':
            logger.warning(f"Skipping non-markdown file: {filepath}")
            return None

        # Find appropriate parser
        for parser in self.parsers:
            if parser.can_parse(filepath):
                try:
                    doc = parser.parse(filepath)
                    self.parsed_documents.append(doc)
                    logger.info(f"Successfully parsed {filepath.name} with {parser.__class__.__name__}")
                    return doc
                except Exception as e:
                    logger.error(f"Error parsing {filepath}: {e}")
                    return None

        logger.warning(f"No suitable parser found for {filepath}")
        return None

    def ingest_directory(self, directory: Path, recursive: bool = True) -> List[ParsedDocument]:
        """
        Ingest all markdown files in a directory.

        Args:
            directory: Path to the directory
            recursive: Whether to search subdirectories

        Returns:
            List of parsed documents
        """
        directory = Path(directory)

        if not directory.exists():
            logger.error(f"Directory not found: {directory}")
            return []

        pattern = '**/*.md' if recursive else '*.md'
        files = list(directory.glob(pattern))

        logger.info(f"Found {len(files)} markdown files in {directory}")

        documents = []
        for filepath in sorted(files):
            # Skip index files
            if 'index' in filepath.name.lower():
                continue

            doc = self.ingest_file(filepath)
            if doc:
                documents.append(doc)

        # Sort by timestamp
        documents.sort(key=lambda d: d.timestamp or datetime.min)

        logger.info(f"Successfully parsed {len(documents)} documents")
        return documents

    def get_all_entities(self) -> Dict[str, List[Dict]]:
        """
        Get all entities extracted from parsed documents.

        Returns:
            Dict mapping entity type to list of entity dicts
        """
        entities_by_type: Dict[str, List[Dict]] = {}

        for doc in self.parsed_documents:
            for entity in doc.entities:
                if entity.entity_type not in entities_by_type:
                    entities_by_type[entity.entity_type] = []

                entity_dict = {
                    "id": entity.entity_id,
                    "source": entity.source_file,
                    **entity.properties
                }
                entities_by_type[entity.entity_type].append(entity_dict)

        return entities_by_type

    def get_all_relationships(self) -> List[Dict]:
        """
        Get all relationships extracted from parsed documents.

        Returns:
            List of relationship dicts
        """
        relationships = []

        for doc in self.parsed_documents:
            for rel in doc.relationships:
                relationships.append({
                    "type": rel.relation_type,
                    "from": rel.from_entity,
                    "to": rel.to_entity,
                    "source": doc.source_file,
                    **rel.properties
                })

        return relationships

    def get_timeline(self) -> List[Dict]:
        """
        Get chronological timeline of all documents.

        Returns:
            List of dicts with timestamp and document info
        """
        timeline = []

        for doc in sorted(self.parsed_documents, key=lambda d: d.timestamp or datetime.min):
            timeline.append({
                "timestamp": doc.timestamp,
                "document_type": doc.document_type,
                "source": doc.source_file,
                "entity_count": len(doc.entities),
                "relationship_count": len(doc.relationships),
            })

        return timeline

    def get_metrics_summary(self) -> Dict[str, Dict]:
        """
        Get aggregated metrics from all documents.

        Returns:
            Dict of metric name to metric values
        """
        all_metrics = {}

        for doc in self.parsed_documents:
            for key, value in doc.metrics.items():
                if key not in all_metrics:
                    all_metrics[key] = {
                        "values": [],
                        "sources": []
                    }
                all_metrics[key]["values"].append(value)
                all_metrics[key]["sources"].append(doc.source_file)

        return all_metrics

    def get_document_by_date(self, date: datetime, doc_type: str = None) -> Optional[ParsedDocument]:
        """
        Get document closest to a specific date.

        Args:
            date: Target date
            doc_type: Optional document type filter

        Returns:
            Closest matching document or None
        """
        candidates = self.parsed_documents
        if doc_type:
            candidates = [d for d in candidates if d.document_type == doc_type]

        if not candidates:
            return None

        # Find closest by timestamp
        return min(candidates, key=lambda d: abs((d.timestamp - date).total_seconds()) if d.timestamp else float('inf'))

    def clear(self):
        """Clear all parsed documents"""
        self.parsed_documents = []


def create_default_pipeline() -> IngestionPipeline:
    """
    Create a pipeline with default known entities for the ABC Inc project.

    Returns:
        Configured IngestionPipeline
    """
    known_entities = {
        "Person": [
            "Ambarish", "Ryan", "Dhyanesh", "Raj", "Riaz",
            "Mousumi", "Nayan", "Lakshmi", "Jhanvi", "Krutika",
            "Sandeep", "Tara", "Vipul", "Tyler", "Jones",
            "Rick", "Roshan", "Sandra", "Michael", "David", "Priya"
        ],
        "Stream": ["SD", "EWM", "Stream 1", "Stream 2"],
        "Status": ["Green", "Amber", "Red", "On Track", "At Risk", "Critical"],
    }

    return IngestionPipeline(known_entities)
