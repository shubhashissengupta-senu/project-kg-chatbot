"""
Scrum Meeting Minutes Parser
Parses weekly scrum meeting markdown files.
"""

import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Optional, Any

from .base_parser import BaseParser, ParsedDocument, ParsedEntity, ParsedRelationship


@dataclass
class ParsedAttendee:
    """Parsed attendee from meeting"""
    name: str
    role: str
    stream: str
    attendance: str


@dataclass
class ParsedTask:
    """Parsed task from meeting"""
    task_id: str
    description: str
    assignee: str
    status: str
    target_date: Optional[datetime]
    stream: str


@dataclass
class ParsedRisk:
    """Parsed risk from meeting"""
    risk_id: str
    description: str
    probability: str
    impact: str
    owner: str
    mitigation: str
    status: str = "Open"


@dataclass
class ParsedActionItem:
    """Parsed action item from meeting"""
    action_num: int
    description: str
    owner: str
    due_date: Optional[datetime]


class ScrumMeetingParser(BaseParser):
    """Parser for scrum meeting markdown files"""

    SPRINT_PATTERN = r'\*\*Sprint:\*\*\s*Sprint\s*(\d+)'
    WEEK_PATTERN = r'Week\s*(\d+)'

    def can_parse(self, filepath: Path) -> bool:
        """Check if file is a scrum meeting file"""
        filename = filepath.name.lower()
        return 'scrum' in filename and filepath.suffix == '.md'

    def parse(self, filepath: Path) -> ParsedDocument:
        """Parse a scrum meeting markdown file"""
        content = filepath.read_text(encoding='utf-8')

        # Extract metadata
        meeting_date = self._extract_meeting_date(content)
        sprint_number = self._extract_sprint_number(content)
        week_number = self._extract_week_number(filepath, content)

        # Create meeting entity ID
        meeting_id = f"MEETING_SCRUM_{meeting_date.strftime('%Y%m%d')}" if meeting_date else f"MEETING_{filepath.stem}"

        # Parse all components
        attendees = self._extract_attendees(content)
        tasks = self._extract_tasks(content)
        risks = self._extract_risks(content)
        action_items = self._extract_action_items(content)
        blockers = self._extract_blockers(content)
        decisions = self._extract_decisions(content)
        quotes = self.extract_quotes(content)
        stream_statuses = self._extract_stream_statuses(content)

        # Build entities list
        entities = []
        relationships = []

        # Meeting entity
        entities.append(ParsedEntity(
            entity_type="Meeting",
            entity_id=meeting_id,
            properties={
                "meeting_type": "Scrum",
                "date": meeting_date,
                "sprint_number": sprint_number,
                "week_number": week_number,
                "stream1_status": stream_statuses.get("stream1"),
                "stream2_status": stream_statuses.get("stream2"),
                "key_topics": self._extract_agenda(content),
                "decisions": decisions,
            },
            source_file=str(filepath)
        ))

        # Person entities and ATTENDED relationships
        for attendee in attendees:
            person_id = f"PERSON_{attendee.name.upper().replace(' ', '_')}"
            entities.append(ParsedEntity(
                entity_type="Person",
                entity_id=person_id,
                properties={
                    "name": attendee.name,
                    "role": attendee.role,
                    "stream": attendee.stream,
                    "status": self.normalize_status(attendee.attendance),
                },
                source_file=str(filepath)
            ))
            relationships.append(ParsedRelationship(
                relation_type="ATTENDED",
                from_entity=person_id,
                to_entity=meeting_id,
                properties={"attendance": attendee.attendance}
            ))

        # Task entities
        for task in tasks:
            task_entity_id = f"TASK_{task.task_id}"
            entities.append(ParsedEntity(
                entity_type="Task",
                entity_id=task_entity_id,
                properties={
                    "task_id": task.task_id,
                    "description": task.description,
                    "status": self.normalize_status(task.status),
                    "target_date": task.target_date,
                    "stream": task.stream,
                },
                source_file=str(filepath)
            ))

            # DISCUSSED_IN relationship
            relationships.append(ParsedRelationship(
                relation_type="DISCUSSED_IN",
                from_entity=task_entity_id,
                to_entity=meeting_id
            ))

            # ASSIGNED_TO relationship
            if task.assignee:
                assignee_id = f"PERSON_{task.assignee.upper().replace(' ', '_')}"
                relationships.append(ParsedRelationship(
                    relation_type="ASSIGNED_TO",
                    from_entity=assignee_id,
                    to_entity=task_entity_id,
                    properties={"assigned_date": meeting_date}
                ))

        # Risk entities
        for risk in risks:
            risk_entity_id = f"RISK_{risk.risk_id}"
            entities.append(ParsedEntity(
                entity_type="Risk",
                entity_id=risk_entity_id,
                properties={
                    "risk_id": risk.risk_id,
                    "description": risk.description,
                    "probability": self.normalize_severity(risk.probability),
                    "impact": self.normalize_severity(risk.impact),
                    "owner": risk.owner,
                    "mitigation": risk.mitigation,
                    "status": self.normalize_status(risk.status),
                },
                source_file=str(filepath)
            ))

            relationships.append(ParsedRelationship(
                relation_type="DISCUSSED_IN",
                from_entity=risk_entity_id,
                to_entity=meeting_id
            ))

            if risk.owner:
                owner_id = f"PERSON_{risk.owner.upper().replace(' ', '_')}"
                relationships.append(ParsedRelationship(
                    relation_type="OWNS",
                    from_entity=owner_id,
                    to_entity=risk_entity_id
                ))

        # Action Item entities
        for action in action_items:
            action_id = f"ACTION_{meeting_id}_{action.action_num}"
            entities.append(ParsedEntity(
                entity_type="ActionItem",
                entity_id=action_id,
                properties={
                    "action_id": str(action.action_num),
                    "description": action.description,
                    "owner": action.owner,
                    "due_date": action.due_date,
                    "status": "Open",
                    "source_meeting": meeting_id,
                },
                source_file=str(filepath)
            ))

            relationships.append(ParsedRelationship(
                relation_type="RAISED_IN",
                from_entity=action_id,
                to_entity=meeting_id
            ))

            if action.owner:
                owner_id = f"PERSON_{action.owner.upper().replace(' ', '_')}"
                relationships.append(ParsedRelationship(
                    relation_type="ASSIGNED_TO",
                    from_entity=owner_id,
                    to_entity=action_id
                ))

        return ParsedDocument(
            document_type="ScrumMeeting",
            source_file=str(filepath),
            timestamp=meeting_date or datetime.now(),
            entities=entities,
            relationships=relationships,
            metrics=self._extract_metrics(content),
            raw_text=content,
            metadata={
                "sprint": sprint_number,
                "week": week_number,
                "blockers": blockers,
                "quotes": quotes,
            }
        )

    def _extract_meeting_date(self, content: str) -> Optional[datetime]:
        """Extract meeting date"""
        # Try **Date:** pattern first
        pattern = r'\*\*Date:\*\*\s*(\w+,\s*\w+\s+\d+,\s+\d+)'
        match = re.search(pattern, content)
        if match:
            try:
                return datetime.strptime(match.group(1), '%A, %B %d, %Y')
            except ValueError:
                pass
        return self.extract_date(content)

    def _extract_sprint_number(self, content: str) -> Optional[int]:
        """Extract sprint number"""
        match = re.search(self.SPRINT_PATTERN, content)
        return int(match.group(1)) if match else None

    def _extract_week_number(self, filepath: Path, content: str) -> Optional[int]:
        """Extract week number from filename or content"""
        # Try filename first: Scrum_Meeting_01_Dec01_2025.md
        filename_match = re.search(r'Scrum_Meeting_(\d+)', filepath.name)
        if filename_match:
            return int(filename_match.group(1))

        # Try content
        match = re.search(self.WEEK_PATTERN, content)
        return int(match.group(1)) if match else None

    def _extract_attendees(self, content: str) -> List[ParsedAttendee]:
        """Extract attendees from table"""
        attendees = []
        section = self.extract_section(content, "Attendees")
        if not section:
            return attendees

        tables = self.extract_tables(section)
        if not tables:
            return attendees

        for row in tables[0]:
            if len(row) >= 4:
                # Skip header row
                if row[0].lower() == 'name':
                    continue
                attendees.append(ParsedAttendee(
                    name=row[0].strip(),
                    role=row[1].strip(),
                    stream=row[2].strip(),
                    attendance=row[3].strip()
                ))

        return attendees

    def _extract_tasks(self, content: str) -> List[ParsedTask]:
        """Extract tasks from SD and EWM sections"""
        tasks = []

        # Pattern for task table rows
        # | SD-001 | Description | Assignee | Status | Target |
        task_pattern = r'\|\s*([A-Z]+-\d+)\s*\|\s*([^|]+)\s*\|\s*(\w+)\s*\|\s*([^|]+)\s*\|\s*([^|]+)\s*\|'

        for match in re.finditer(task_pattern, content):
            task_id, desc, assignee, status, target = match.groups()
            tasks.append(ParsedTask(
                task_id=task_id.strip(),
                description=desc.strip(),
                assignee=assignee.strip(),
                status=status.strip(),
                target_date=self.parse_date_flexible(target.strip()),
                stream="SD" if task_id.startswith("SD") else "EWM"
            ))

        return tasks

    def _extract_risks(self, content: str) -> List[ParsedRisk]:
        """Extract risks from risk table"""
        risks = []

        # Pattern for risk table
        # | R-001 | Description | Probability | Impact | Owner | Mitigation |
        risk_pattern = r'\|\s*(R-\d+)\s*\|\s*([^|]+)\s*\|\s*(\w+)\s*\|\s*(\w+)\s*\|\s*(\w+)\s*\|\s*([^|]+)\s*\|'

        for match in re.finditer(risk_pattern, content):
            risk_id, desc, prob, impact, owner, mitigation = match.groups()
            risks.append(ParsedRisk(
                risk_id=risk_id.strip(),
                description=desc.strip(),
                probability=prob.strip(),
                impact=impact.strip(),
                owner=owner.strip(),
                mitigation=mitigation.strip(),
                status="Open"
            ))

        return risks

    def _extract_action_items(self, content: str) -> List[ParsedActionItem]:
        """Extract action items from table"""
        actions = []
        section = self.extract_section(content, "Action Items")
        if not section:
            return actions

        # Pattern: | # | Action | Owner | Due Date |
        action_pattern = r'\|\s*(\d+)\s*\|\s*([^|]+)\s*\|\s*(\w+)\s*\|\s*([^|]+)\s*\|'

        for match in re.finditer(action_pattern, section):
            num, desc, owner, due = match.groups()
            actions.append(ParsedActionItem(
                action_num=int(num.strip()),
                description=desc.strip(),
                owner=owner.strip(),
                due_date=self.parse_date_flexible(due.strip())
            ))

        return actions

    def _extract_blockers(self, content: str) -> List[str]:
        """Extract current blockers"""
        section = self.extract_section(content, "Dependencies & Blockers")
        if not section:
            return []

        blockers = []
        # Look for "Current Blockers:" subsection
        blocker_match = re.search(r'\*\*Current Blockers:\*\*\s*(.+?)(?=\n\n|\*\*|$)', section, re.DOTALL)
        if blocker_match:
            blocker_text = blocker_match.group(1)
            if 'none' not in blocker_text.lower():
                blockers = self.extract_bullet_points(blocker_text)

        return blockers

    def _extract_decisions(self, content: str) -> List[str]:
        """Extract decisions made"""
        section = self.extract_section(content, "Decisions Made")
        if section:
            return self.extract_numbered_list(section)
        return []

    def _extract_agenda(self, content: str) -> List[str]:
        """Extract agenda items"""
        section = self.extract_section(content, "Agenda")
        if section:
            return self.extract_numbered_list(section)
        return []

    def _extract_stream_statuses(self, content: str) -> Dict[str, str]:
        """Extract stream statuses from meeting index or summary"""
        statuses = {}

        # Look for status in table format
        # | Stream 1 Status | Green |
        stream1_match = re.search(r'Stream\s*1[^|]*\|\s*(\w+)', content, re.IGNORECASE)
        stream2_match = re.search(r'Stream\s*2[^|]*\|\s*(\w+)', content, re.IGNORECASE)

        if stream1_match:
            statuses['stream1'] = self.normalize_status(stream1_match.group(1))
        if stream2_match:
            statuses['stream2'] = self.normalize_status(stream2_match.group(1))

        # Also check for status keywords in headers
        if 'stream 1' in content.lower():
            if 'on track' in content.lower():
                statuses.setdefault('stream1', 'Green')
            elif 'at risk' in content.lower():
                statuses.setdefault('stream1', 'Amber')

        return statuses

    def _extract_metrics(self, content: str) -> Dict[str, Any]:
        """Extract any metrics mentioned in the meeting"""
        metrics = {}

        # Velocity pattern
        velocity_match = re.search(r'velocity[:\s]+(\d+)', content, re.IGNORECASE)
        if velocity_match:
            metrics['velocity'] = int(velocity_match.group(1))

        # Coverage pattern
        coverage_match = re.search(r'coverage[:\s]+(\d+(?:\.\d+)?)\s*%', content, re.IGNORECASE)
        if coverage_match:
            metrics['test_coverage'] = float(coverage_match.group(1))

        # Completion pattern
        completion_match = re.search(r'(\d+(?:\.\d+)?)\s*%\s*complet', content, re.IGNORECASE)
        if completion_match:
            metrics['completion'] = float(completion_match.group(1))

        return metrics
