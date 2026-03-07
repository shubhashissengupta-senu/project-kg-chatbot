"""
Client Review Meeting Parser
Parses monthly client review meeting markdown files.
"""

import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Optional, Any

from .base_parser import BaseParser, ParsedDocument, ParsedEntity, ParsedRelationship


@dataclass
class ParsedChangeRequest:
    """Parsed change request"""
    cr_id: str
    description: str
    value: Optional[float]
    status: str
    raised_date: Optional[datetime]
    approved_date: Optional[datetime]
    impact_weeks: Optional[float]


@dataclass
class ParsedClientConcern:
    """Parsed client concern"""
    description: str
    severity: str
    resolution: Optional[str]


@dataclass
class ParsedCommitment:
    """Parsed commitment to client"""
    description: str
    made_date: datetime
    delivered_date: Optional[datetime]
    status: str


class ClientReviewParser(BaseParser):
    """Parser for client review meeting markdown files"""

    def can_parse(self, filepath: Path) -> bool:
        """Check if file is a client review file"""
        filename = filepath.name.lower()
        return 'client' in filename and 'review' in filename and filepath.suffix == '.md'

    def parse(self, filepath: Path) -> ParsedDocument:
        """Parse a client review markdown file"""
        content = filepath.read_text(encoding='utf-8')

        # Extract metadata
        meeting_date = self._extract_meeting_date(content, filepath)
        meeting_number = self._extract_meeting_number(filepath)

        # Create meeting entity ID
        meeting_id = f"MEETING_CLIENT_{meeting_date.strftime('%Y%m%d')}" if meeting_date else f"MEETING_{filepath.stem}"

        # Parse components
        attendees = self._extract_attendees(content)
        change_requests = self._extract_change_requests(content)
        concerns = self._extract_client_concerns(content)
        appreciations = self._extract_client_appreciations(content)
        commitments = self._extract_commitments(content)
        stream_ratings = self._extract_stream_ratings(content)
        quotes = self.extract_quotes(content)

        entities = []
        relationships = []

        # Meeting entity
        entities.append(ParsedEntity(
            entity_type="Meeting",
            entity_id=meeting_id,
            properties={
                "meeting_type": "ClientReview",
                "date": meeting_date,
                "meeting_number": meeting_number,
                "stream1_rating": stream_ratings.get("stream1"),
                "stream2_rating": stream_ratings.get("stream2"),
                "overall_rating": stream_ratings.get("overall"),
                "client_sentiment": self._assess_sentiment(content),
                "key_concerns": [c.description for c in concerns],
                "key_appreciations": appreciations,
            },
            source_file=str(filepath)
        ))

        # Attendee entities
        for attendee in attendees:
            person_id = f"PERSON_{attendee['name'].upper().replace(' ', '_')}"
            entities.append(ParsedEntity(
                entity_type="Person",
                entity_id=person_id,
                properties={
                    "name": attendee['name'],
                    "role": attendee.get('role', ''),
                    "organization": attendee.get('organization', 'Unknown'),
                },
                source_file=str(filepath)
            ))
            relationships.append(ParsedRelationship(
                relation_type="ATTENDED",
                from_entity=person_id,
                to_entity=meeting_id,
                properties={"role_in_meeting": attendee.get('role', '')}
            ))

        # Change Request entities
        for cr in change_requests:
            cr_entity_id = f"CR_{cr.cr_id}"
            entities.append(ParsedEntity(
                entity_type="ChangeRequest",
                entity_id=cr_entity_id,
                properties={
                    "cr_id": cr.cr_id,
                    "description": cr.description,
                    "value": cr.value,
                    "status": self.normalize_status(cr.status),
                    "raised_date": cr.raised_date,
                    "approved_date": cr.approved_date,
                    "impact_weeks": cr.impact_weeks,
                },
                source_file=str(filepath)
            ))
            relationships.append(ParsedRelationship(
                relation_type="DISCUSSED_IN",
                from_entity=cr_entity_id,
                to_entity=meeting_id
            ))

        # Commitment entities
        for idx, commitment in enumerate(commitments):
            commitment_id = f"COMMITMENT_{meeting_id}_{idx}"
            entities.append(ParsedEntity(
                entity_type="ActionItem",
                entity_id=commitment_id,
                properties={
                    "description": commitment.description,
                    "status": commitment.status,
                    "due_date": commitment.delivered_date,
                    "source_meeting": meeting_id,
                    "commitment_type": "client",
                },
                source_file=str(filepath)
            ))

        # Event entities for significant occurrences
        events = self._extract_events(content, meeting_date)
        for event in events:
            event_id = f"EVENT_{meeting_id}_{event['type']}"
            entities.append(ParsedEntity(
                entity_type="Event",
                entity_id=event_id,
                properties={
                    "event_type": event['type'],
                    "date": meeting_date,
                    "description": event['description'],
                    "impact": event.get('impact', 'Medium'),
                },
                source_file=str(filepath)
            ))

        return ParsedDocument(
            document_type="ClientReview",
            source_file=str(filepath),
            timestamp=meeting_date or datetime.now(),
            entities=entities,
            relationships=relationships,
            metrics=self._extract_metrics(content, stream_ratings),
            raw_text=content,
            metadata={
                "meeting_number": meeting_number,
                "concerns": [c.__dict__ for c in concerns],
                "appreciations": appreciations,
                "quotes": quotes,
                "sentiment": self._assess_sentiment(content),
            }
        )

    def _extract_meeting_date(self, content: str, filepath: Path) -> Optional[datetime]:
        """Extract meeting date from content or filename"""
        # Try filename: Client_Review_01_Dec18_2025.md
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

    def _extract_attendees(self, content: str) -> List[Dict[str, str]]:
        """Extract attendees with organization"""
        attendees = []

        # Look for attendee tables
        # ABC Inc. Representatives and Accenture Representatives
        abc_section = self.extract_section(content, "ABC Inc. Representatives")
        acc_section = self.extract_section(content, "Accenture Representatives")

        for section, org in [(abc_section, "ABCInc"), (acc_section, "Accenture")]:
            if section:
                tables = self.extract_tables(section)
                for table in tables:
                    for row in table:
                        if len(row) >= 2 and row[0].lower() != 'name':
                            attendees.append({
                                "name": row[0].strip(),
                                "role": row[1].strip() if len(row) > 1 else "",
                                "organization": org,
                            })

        return attendees

    def _extract_change_requests(self, content: str) -> List[ParsedChangeRequest]:
        """Extract change requests"""
        crs = []

        # Pattern: | CR-001 | Voice Picking Integration | $42,000 | Approved |
        cr_pattern = r'\|\s*(CR-?\d+)\s*\|\s*([^|]+)\s*\|\s*\$?([\d,]+)?\s*\|\s*([^|]+)\s*\|'

        for match in re.finditer(cr_pattern, content):
            cr_id, desc, value, status = match.groups()
            crs.append(ParsedChangeRequest(
                cr_id=cr_id.replace('-', '-').upper(),
                description=desc.strip(),
                value=float(value.replace(',', '')) if value else None,
                status=status.strip(),
                raised_date=None,
                approved_date=None,
                impact_weeks=None
            ))

        return crs

    def _extract_client_concerns(self, content: str) -> List[ParsedClientConcern]:
        """Extract client concerns"""
        concerns = []
        section = self.extract_section(content, "Key Client Concerns")
        if not section:
            section = self.extract_section(content, "Client Concerns")

        if section:
            items = self.extract_numbered_list(section)
            if not items:
                items = self.extract_bullet_points(section)

            for item in items:
                concerns.append(ParsedClientConcern(
                    description=item,
                    severity="Medium",  # Default
                    resolution=None
                ))

        return concerns

    def _extract_client_appreciations(self, content: str) -> List[str]:
        """Extract client appreciations"""
        section = self.extract_section(content, "Key Client Appreciations")
        if not section:
            section = self.extract_section(content, "Client Appreciations")

        if section:
            items = self.extract_numbered_list(section)
            if not items:
                items = self.extract_bullet_points(section)
            return items

        return []

    def _extract_commitments(self, content: str) -> List[ParsedCommitment]:
        """Extract commitments made to client"""
        commitments = []
        section = self.extract_section(content, "Commitments Made")

        if section:
            tables = self.extract_tables(section)
            for table in tables:
                for row in table:
                    if len(row) >= 4 and row[0].lower() != 'commitment':
                        status = row[3].strip() if len(row) > 3 else "Open"
                        # Check for checkmark indicators
                        if '✅' in status or 'met' in status.lower():
                            status = "Complete"
                        commitments.append(ParsedCommitment(
                            description=row[0].strip(),
                            made_date=self.parse_date_flexible(row[1]) if len(row) > 1 else None,
                            delivered_date=self.parse_date_flexible(row[2]) if len(row) > 2 else None,
                            status=status
                        ))

        return commitments

    def _extract_stream_ratings(self, content: str) -> Dict[str, Any]:
        """Extract stream satisfaction ratings"""
        ratings = {}

        # Pattern: | December | 8/10 | - | Strong start |
        rating_pattern = r'\|\s*\w+\s*\|\s*(\d+)/10\s*\|'

        # Look for Stream 1 and Stream 2 ratings
        stream1_section = self.extract_section(content, "Stream 1")
        stream2_section = self.extract_section(content, "Stream 2")
        overall_section = self.extract_section(content, "Overall Project")

        for section, key in [(stream1_section, "stream1"), (stream2_section, "stream2"), (overall_section, "overall")]:
            if section:
                match = re.search(r'(\d+)/10', section)
                if match:
                    ratings[key] = int(match.group(1))

        return ratings

    def _assess_sentiment(self, content: str) -> str:
        """Assess overall client sentiment from content"""
        content_lower = content.lower()

        positive_indicators = ['impressed', 'excellent', 'great', 'confident', 'satisfied', 'appreciate', 'well done']
        negative_indicators = ['concerned', 'frustrated', 'disappointed', 'worried', 'issue', 'problem', 'risk']
        neutral_indicators = ['cautious', 'mixed', 'moderate']

        positive_count = sum(1 for word in positive_indicators if word in content_lower)
        negative_count = sum(1 for word in negative_indicators if word in content_lower)

        if positive_count > negative_count + 2:
            return "Positive"
        elif negative_count > positive_count + 2:
            return "Negative"
        elif positive_count > negative_count:
            return "CautiouslyPositive"
        elif negative_count > positive_count:
            return "Concerned"
        else:
            return "Neutral"

    def _extract_events(self, content: str, meeting_date: datetime) -> List[Dict[str, Any]]:
        """Extract significant events mentioned"""
        events = []

        # Look for status changes
        if 'red' in content.lower() and 'status' in content.lower():
            events.append({
                "type": "StatusChange",
                "description": "Stream status changed to Red",
                "impact": "High"
            })

        # Look for CR approvals
        if 'approved' in content.lower() and 'cr' in content.lower():
            events.append({
                "type": "CRApproved",
                "description": "Change request(s) approved",
                "impact": "Medium"
            })

        # Look for resource mentions
        if 'departure' in content.lower() or 'leaving' in content.lower() or 'resigned' in content.lower():
            events.append({
                "type": "ResourceDepart",
                "description": "Team member departure discussed",
                "impact": "High"
            })

        return events

    def _extract_metrics(self, content: str, ratings: Dict) -> Dict[str, Any]:
        """Extract metrics from client review"""
        metrics = {
            "stream1_satisfaction": ratings.get("stream1"),
            "stream2_satisfaction": ratings.get("stream2"),
            "overall_satisfaction": ratings.get("overall"),
        }

        # Extract test pass rates if mentioned
        pass_rate_match = re.search(r'(\d+(?:\.\d+)?)\s*%\s*(?:pass|test)', content, re.IGNORECASE)
        if pass_rate_match:
            metrics["test_pass_rate"] = float(pass_rate_match.group(1))

        # Extract latency if mentioned
        latency_match = re.search(r'(\d+)\s*(?:-?\s*)?second', content, re.IGNORECASE)
        if latency_match:
            metrics["integration_latency_seconds"] = int(latency_match.group(1))

        return metrics
