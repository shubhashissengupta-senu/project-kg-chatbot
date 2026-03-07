"""
QA Review Meeting Parser
Parses monthly QA review meeting markdown files.
"""

import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Optional, Any

from .base_parser import BaseParser, ParsedDocument, ParsedEntity, ParsedRelationship


@dataclass
class QAFinding:
    """A QA finding/issue"""
    finding_id: str
    category: str
    severity: str
    description: str
    status: str
    recommendation: str


@dataclass
class QualityMetric:
    """A quality metric measurement"""
    name: str
    value: float
    target: Optional[float]
    status: str  # Green, Amber, Red


class QAReviewParser(BaseParser):
    """Parser for QA review meeting markdown files"""

    def can_parse(self, filepath: Path) -> bool:
        """Check if file is a QA review file"""
        filename = filepath.name.lower()
        return 'qa' in filename and 'review' in filename and filepath.suffix == '.md'

    def parse(self, filepath: Path) -> ParsedDocument:
        """Parse a QA review markdown file"""
        content = filepath.read_text(encoding='utf-8')

        # Extract metadata
        meeting_date = self._extract_meeting_date(content, filepath)
        meeting_number = self._extract_meeting_number(filepath)

        # Create meeting entity ID
        meeting_id = f"MEETING_QA_{meeting_date.strftime('%Y%m%d')}" if meeting_date else f"MEETING_{filepath.stem}"

        # Parse components
        findings = self._extract_findings(content)
        quality_metrics = self._extract_quality_metrics(content)
        recommendations = self._extract_recommendations(content)
        stream_assessments = self._extract_stream_assessments(content)

        entities = []
        relationships = []

        # Meeting entity
        entities.append(ParsedEntity(
            entity_type="Meeting",
            entity_id=meeting_id,
            properties={
                "meeting_type": "QAReview",
                "date": meeting_date,
                "meeting_number": meeting_number,
                "qa_director": self._extract_qa_director(content),
                "stream1_assessment": stream_assessments.get("SD"),
                "stream2_assessment": stream_assessments.get("EWM"),
                "overall_quality_grade": self._extract_quality_grade(content),
                "uat_readiness": self._extract_uat_readiness(content),
                "key_recommendations": recommendations[:5],
            },
            source_file=str(filepath)
        ))

        # QA Findings as entities
        for finding in findings:
            finding_id = f"QA_FINDING_{meeting_id}_{finding.finding_id}"
            entities.append(ParsedEntity(
                entity_type="QAFinding",
                entity_id=finding_id,
                properties={
                    "finding_id": finding.finding_id,
                    "category": finding.category,
                    "severity": finding.severity,
                    "description": finding.description,
                    "status": finding.status,
                    "recommendation": finding.recommendation,
                    "found_date": meeting_date,
                },
                source_file=str(filepath)
            ))

            relationships.append(ParsedRelationship(
                relation_type="RAISED_IN",
                from_entity=finding_id,
                to_entity=meeting_id
            ))

        # Quality metrics
        metrics_dict = {}
        for metric in quality_metrics:
            metric_id = f"METRIC_QA_{metric.name}_{meeting_date.strftime('%Y%m%d')}" if meeting_date else f"METRIC_{metric.name}"
            entities.append(ParsedEntity(
                entity_type="MetricSnapshot",
                entity_id=metric_id,
                properties={
                    "metric_name": metric.name,
                    "value": metric.value,
                    "target": metric.target,
                    "status": metric.status,
                    "timestamp": meeting_date,
                    "source": "QA Review"
                },
                source_file=str(filepath)
            ))
            metrics_dict[metric.name] = metric.value

        return ParsedDocument(
            document_type="QAReview",
            source_file=str(filepath),
            timestamp=meeting_date or datetime.now(),
            entities=entities,
            relationships=relationships,
            metrics=metrics_dict,
            raw_text=content,
            metadata={
                "meeting_number": meeting_number,
                "findings_count": len(findings),
                "recommendations": recommendations,
                "stream_assessments": stream_assessments,
            }
        )

    def _extract_meeting_date(self, content: str, filepath: Path) -> Optional[datetime]:
        """Extract meeting date"""
        # Try filename: QA_Review_01_Dec19_2025.md
        filename_match = re.search(r'(\w{3})(\d{2})_(\d{4})', filepath.name)
        if filename_match:
            month, day, year = filename_match.groups()
            try:
                return datetime.strptime(f"{month} {day}, {year}", "%b %d, %Y")
            except ValueError:
                pass
        return self.extract_date(content)

    def _extract_meeting_number(self, filepath: Path) -> Optional[int]:
        """Extract meeting number from filename"""
        match = re.search(r'Review_(\d+)', filepath.name)
        return int(match.group(1)) if match else None

    def _extract_qa_director(self, content: str) -> Optional[str]:
        """Extract QA Director name"""
        match = re.search(r'\*\*QA Director:\*\*\s*(\w+\s*\w*)', content)
        return match.group(1).strip() if match else "Roshan Arora"

    def _extract_findings(self, content: str) -> List[QAFinding]:
        """Extract QA findings"""
        findings = []

        # Pattern for findings table
        # | ID | Category | Severity | Description | Status |
        finding_pattern = r'\|\s*([A-Z]+-\d+)\s*\|\s*([^|]+)\s*\|\s*(\w+)\s*\|\s*([^|]+)\s*\|\s*([^|]+)\s*\|'

        for match in re.finditer(finding_pattern, content):
            fid, category, severity, desc, status = match.groups()
            findings.append(QAFinding(
                finding_id=fid.strip(),
                category=category.strip(),
                severity=self.normalize_severity(severity.strip()),
                description=desc.strip(),
                status=self.normalize_status(status.strip()),
                recommendation=""
            ))

        return findings

    def _extract_quality_metrics(self, content: str) -> List[QualityMetric]:
        """Extract quality metrics"""
        metrics = []

        # Pattern for metrics table
        # | Metric | Value | Target | Status |
        metric_pattern = r'\|\s*([^|]+)\s*\|\s*([\d.]+%?)\s*\|\s*([\d.]+%?)\s*\|\s*([^|]+)\s*\|'

        for match in re.finditer(metric_pattern, content):
            name, value, target, status = match.groups()

            # Skip header rows
            if 'metric' in name.lower():
                continue

            # Parse value
            value_str = value.strip().replace('%', '')
            target_str = target.strip().replace('%', '')

            try:
                value_num = float(value_str)
                target_num = float(target_str) if target_str and target_str != '-' else None
            except ValueError:
                continue

            metrics.append(QualityMetric(
                name=self._normalize_metric_name(name.strip()),
                value=value_num,
                target=target_num,
                status=self._normalize_rag_status(status.strip())
            ))

        return metrics

    def _extract_recommendations(self, content: str) -> List[str]:
        """Extract recommendations"""
        section = self.extract_section(content, "Recommendations")
        if section:
            return self.extract_numbered_list(section) or self.extract_bullet_points(section)
        return []

    def _extract_stream_assessments(self, content: str) -> Dict[str, str]:
        """Extract stream quality assessments"""
        assessments = {}

        # Look for stream assessment patterns
        sd_match = re.search(r'Stream\s*1[^:]*:\s*(\w+)', content, re.IGNORECASE)
        ewm_match = re.search(r'Stream\s*2[^:]*:\s*(\w+)', content, re.IGNORECASE)

        if sd_match:
            assessments["SD"] = self._normalize_rag_status(sd_match.group(1))
        if ewm_match:
            assessments["EWM"] = self._normalize_rag_status(ewm_match.group(1))

        return assessments

    def _extract_quality_grade(self, content: str) -> Optional[str]:
        """Extract overall quality grade"""
        match = re.search(r'(?:Quality|Overall)\s*Grade:\s*([A-F][+-]?)', content, re.IGNORECASE)
        return match.group(1) if match else None

    def _extract_uat_readiness(self, content: str) -> Dict[str, Any]:
        """Extract UAT readiness assessment"""
        readiness = {}

        # Look for readiness percentages
        sd_ready = re.search(r'SD[^:]*:\s*(\d+)%\s*(?:ready|confidence)', content, re.IGNORECASE)
        ewm_ready = re.search(r'EWM[^:]*:\s*(\d+)%\s*(?:ready|confidence)', content, re.IGNORECASE)

        if sd_ready:
            readiness["SD"] = int(sd_ready.group(1))
        if ewm_ready:
            readiness["EWM"] = int(ewm_ready.group(1))

        return readiness

    def _normalize_metric_name(self, name: str) -> str:
        """Normalize metric name"""
        name = name.lower().strip()
        name = re.sub(r'[^\w\s]', '', name)
        name = re.sub(r'\s+', '_', name)
        return name

    def _normalize_rag_status(self, status: str) -> str:
        """Normalize RAG status"""
        status_lower = status.lower().strip()
        if 'green' in status_lower or '🟢' in status:
            return "Green"
        if 'amber' in status_lower or 'yellow' in status_lower or '🟡' in status:
            return "Amber"
        if 'red' in status_lower or '🔴' in status:
            return "Red"
        return status
