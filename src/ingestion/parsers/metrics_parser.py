"""
Metrics Parser
Parses project metrics and developer metrics markdown files.
"""

import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional

from .base_parser import BaseParser, ParsedDocument, ParsedEntity, ParsedRelationship


@dataclass
class ParsedMetricValue:
    """A parsed metric value"""
    metric_name: str
    value: float
    unit: str
    entity_type: Optional[str]
    entity_id: Optional[str]
    timestamp: Optional[datetime]
    period: Optional[str]  # e.g., "December", "Week 1", "Sprint 3"


class MetricsParser(BaseParser):
    """Parser for metrics markdown files"""

    def can_parse(self, filepath: Path) -> bool:
        """Check if file is a metrics file"""
        filename = filepath.name.lower()
        return ('metric' in filename or 'trend' in filename) and filepath.suffix == '.md'

    def parse(self, filepath: Path) -> ParsedDocument:
        """Parse a metrics markdown file"""
        content = filepath.read_text(encoding='utf-8')

        # Determine metrics type
        metrics_type = self._determine_metrics_type(filepath, content)

        entities = []
        relationships = []
        all_metrics = {}

        if metrics_type == "developer":
            # Parse individual developer metrics
            metrics = self._parse_developer_metrics(content)
            for metric in metrics:
                entity_id = f"METRIC_{metric.metric_name}_{metric.entity_id}_{metric.period or 'overall'}"
                entities.append(ParsedEntity(
                    entity_type="MetricSnapshot",
                    entity_id=entity_id,
                    properties={
                        "metric_name": metric.metric_name,
                        "value": metric.value,
                        "unit": metric.unit,
                        "entity_type": metric.entity_type,
                        "entity_id": metric.entity_id,
                        "timestamp": metric.timestamp,
                        "period": metric.period,
                    },
                    source_file=str(filepath)
                ))

                # Link to person if developer metric
                if metric.entity_type == "Person" and metric.entity_id:
                    person_id = f"PERSON_{metric.entity_id.upper().replace(' ', '_')}"
                    relationships.append(ParsedRelationship(
                        relation_type="HAS_METRIC",
                        from_entity=person_id,
                        to_entity=entity_id
                    ))

            all_metrics = self._aggregate_metrics(metrics)

        elif metrics_type == "project":
            # Parse project-level metrics
            metrics = self._parse_project_metrics(content)
            for metric in metrics:
                entity_id = f"METRIC_{metric.metric_name}_{metric.period or 'overall'}"
                entities.append(ParsedEntity(
                    entity_type="MetricSnapshot",
                    entity_id=entity_id,
                    properties={
                        "metric_name": metric.metric_name,
                        "value": metric.value,
                        "unit": metric.unit,
                        "timestamp": metric.timestamp,
                        "period": metric.period,
                    },
                    source_file=str(filepath)
                ))

            all_metrics = self._aggregate_metrics(metrics)

        elif metrics_type == "trends":
            # Parse headline trends
            metrics, events = self._parse_trend_data(content)
            for metric in metrics:
                entity_id = f"METRIC_{metric.metric_name}_{metric.period or 'overall'}"
                entities.append(ParsedEntity(
                    entity_type="MetricSnapshot",
                    entity_id=entity_id,
                    properties={
                        "metric_name": metric.metric_name,
                        "value": metric.value,
                        "unit": metric.unit,
                        "timestamp": metric.timestamp,
                        "period": metric.period,
                    },
                    source_file=str(filepath)
                ))

            # Add events as entities
            for event in events:
                event_id = f"EVENT_{event['date'].strftime('%Y%m%d')}_{event['type']}"
                entities.append(ParsedEntity(
                    entity_type="Event",
                    entity_id=event_id,
                    properties=event,
                    source_file=str(filepath)
                ))

            all_metrics = self._aggregate_metrics(metrics)

        return ParsedDocument(
            document_type=f"{metrics_type.title()}Metrics",
            source_file=str(filepath),
            timestamp=datetime.now(),
            entities=entities,
            relationships=relationships,
            metrics=all_metrics,
            raw_text=content,
            metadata={
                "metrics_type": metrics_type,
            }
        )

    def _determine_metrics_type(self, filepath: Path, content: str) -> str:
        """Determine the type of metrics file"""
        filename = filepath.name.lower()
        content_lower = content.lower()

        if 'developer' in filename or 'individual' in filename:
            return "developer"
        elif 'trend' in filename or 'headline' in filename:
            return "trends"
        elif 'velocity' in content_lower and 'developer' in content_lower:
            return "developer"
        else:
            return "project"

    def _parse_developer_metrics(self, content: str) -> List[ParsedMetricValue]:
        """Parse developer-specific metrics"""
        metrics = []

        # Parse commit activity table
        # | Developer | Dec Commits | Jan Commits | Feb Commits | Total |
        commit_section = self.extract_section(content, "Commit Activity")
        if commit_section:
            metrics.extend(self._parse_monthly_table(
                commit_section, "commits", "count", "Person"
            ))

        # Parse LOC metrics
        loc_section = self.extract_section(content, "Lines of Code")
        if loc_section:
            metrics.extend(self._parse_monthly_table(
                loc_section, "loc_added", "lines", "Person"
            ))

        # Parse velocity metrics
        velocity_section = self.extract_section(content, "Story Point Velocity")
        if velocity_section:
            metrics.extend(self._parse_sprint_table(
                velocity_section, "velocity", "story_points", "Person"
            ))

        # Parse quality scores
        quality_section = self.extract_section(content, "Code Efficiency")
        if quality_section:
            metrics.extend(self._parse_monthly_table(
                quality_section, "efficiency_score", "score", "Person"
            ))

        return metrics

    def _parse_project_metrics(self, content: str) -> List[ParsedMetricValue]:
        """Parse project-level metrics"""
        metrics = []

        # Repository statistics
        repo_section = self.extract_section(content, "Repository Statistics")
        if repo_section:
            kv = self.extract_key_value_pairs(repo_section)
            for key, value in kv.items():
                numeric = self._extract_numeric(value)
                if numeric is not None:
                    metrics.append(ParsedMetricValue(
                        metric_name=self._normalize_metric_name(key),
                        value=numeric,
                        unit=self._infer_unit(key),
                        entity_type="Project",
                        entity_id="ABC_Inc_Migration",
                        timestamp=None,
                        period="overall"
                    ))

        # Development activity
        dev_section = self.extract_section(content, "Development Activity")
        if dev_section:
            kv = self.extract_key_value_pairs(dev_section)
            for key, value in kv.items():
                numeric = self._extract_numeric(value)
                if numeric is not None:
                    metrics.append(ParsedMetricValue(
                        metric_name=self._normalize_metric_name(key),
                        value=numeric,
                        unit=self._infer_unit(key),
                        entity_type="Project",
                        entity_id="ABC_Inc_Migration",
                        timestamp=None,
                        period="overall"
                    ))

        # Testing coverage
        test_section = self.extract_section(content, "Testing Coverage")
        if test_section:
            tables = self.extract_tables(test_section)
            for table in tables:
                for row in table:
                    if len(row) >= 2:
                        numeric = self._extract_numeric(row[1])
                        if numeric is not None:
                            metrics.append(ParsedMetricValue(
                                metric_name=self._normalize_metric_name(row[0]),
                                value=numeric,
                                unit="count" if "test" in row[0].lower() else "percentage",
                                entity_type="Project",
                                entity_id="ABC_Inc_Migration",
                                timestamp=None,
                                period="overall"
                            ))

        return metrics

    def _parse_trend_data(self, content: str) -> tuple:
        """Parse trend data including timeline events"""
        metrics = []
        events = []

        # KPI table
        # | KPI | December | January | February | Trend |
        kpi_section = self.extract_section(content, "Key Performance Indicators")
        if kpi_section:
            tables = self.extract_tables(kpi_section)
            for table in tables:
                header = table[0] if table else []
                for row in table[1:]:
                    if len(row) >= 4:
                        metric_name = self._normalize_metric_name(row[0])
                        periods = ["December", "January", "February"]
                        for i, period in enumerate(periods):
                            if i + 1 < len(row):
                                numeric = self._extract_numeric(row[i + 1])
                                if numeric is not None:
                                    metrics.append(ParsedMetricValue(
                                        metric_name=metric_name,
                                        value=numeric,
                                        unit=self._infer_unit(row[0]),
                                        entity_type="Project",
                                        entity_id="ABC_Inc_Migration",
                                        timestamp=self._period_to_date(period),
                                        period=period
                                    ))

        # Resource events timeline
        events_section = self.extract_section(content, "Resource Events Timeline")
        if events_section:
            events.extend(self._parse_timeline_events(events_section))

        # Milestone data
        milestone_section = self.extract_section(content, "Milestone Achievement")
        if milestone_section:
            tables = self.extract_tables(milestone_section)
            for table in tables:
                for row in table:
                    if len(row) >= 4 and row[0].lower() != 'milestone':
                        events.append({
                            "type": "MilestoneReached",
                            "description": row[0],
                            "date": self.parse_date_flexible(row[1]) or datetime.now(),
                            "target_date": self.parse_date_flexible(row[1]),
                            "actual_date": self.parse_date_flexible(row[2]) if len(row) > 2 else None,
                            "status": row[4] if len(row) > 4 else "Unknown",
                        })

        return metrics, events

    def _parse_monthly_table(self, content: str, metric_name: str, unit: str, entity_type: str) -> List[ParsedMetricValue]:
        """Parse table with monthly columns"""
        metrics = []
        tables = self.extract_tables(content)

        for table in tables:
            if not table:
                continue

            header = table[0]
            month_cols = {}

            # Find month columns
            for i, col in enumerate(header):
                col_lower = col.lower()
                if 'dec' in col_lower:
                    month_cols['December'] = i
                elif 'jan' in col_lower:
                    month_cols['January'] = i
                elif 'feb' in col_lower:
                    month_cols['February'] = i

            # Parse data rows
            for row in table[1:]:
                if len(row) < 2:
                    continue

                entity_id = row[0].strip()
                if entity_id.lower() in ['developer', 'total', 'team total', '**team total**']:
                    continue

                for month, col_idx in month_cols.items():
                    if col_idx < len(row):
                        value = self._extract_numeric(row[col_idx])
                        if value is not None:
                            metrics.append(ParsedMetricValue(
                                metric_name=metric_name,
                                value=value,
                                unit=unit,
                                entity_type=entity_type,
                                entity_id=entity_id,
                                timestamp=self._period_to_date(month),
                                period=month
                            ))

        return metrics

    def _parse_sprint_table(self, content: str, metric_name: str, unit: str, entity_type: str) -> List[ParsedMetricValue]:
        """Parse table with sprint columns"""
        metrics = []
        tables = self.extract_tables(content)

        for table in tables:
            if not table:
                continue

            header = table[0]
            sprint_cols = {}

            # Find sprint columns
            for i, col in enumerate(header):
                sprint_match = re.search(r'sprint\s*(\d+)', col, re.IGNORECASE)
                if sprint_match:
                    sprint_cols[f"Sprint {sprint_match.group(1)}"] = i

            # Parse data rows
            for row in table[1:]:
                if len(row) < 2:
                    continue

                entity_id = row[0].strip()
                if entity_id.lower() in ['developer', 'total']:
                    continue

                for sprint, col_idx in sprint_cols.items():
                    if col_idx < len(row):
                        value = self._extract_numeric(row[col_idx])
                        if value is not None:
                            metrics.append(ParsedMetricValue(
                                metric_name=metric_name,
                                value=value,
                                unit=unit,
                                entity_type=entity_type,
                                entity_id=entity_id,
                                timestamp=None,
                                period=sprint
                            ))

        return metrics

    def _parse_timeline_events(self, content: str) -> List[Dict[str, Any]]:
        """Parse timeline events from content"""
        events = []

        # Pattern: ├── Jan 12: Description
        event_pattern = r'[├└]──\s*(\w+\s+\d+):\s*(.+)'

        current_month = None
        for line in content.split('\n'):
            # Check for month headers
            month_match = re.search(r'(December|January|February)\s+\d{4}', line)
            if month_match:
                current_month = month_match.group(0)

            event_match = re.search(event_pattern, line)
            if event_match:
                date_str, description = event_match.groups()
                event_date = self.parse_date_flexible(date_str)

                event_type = "General"
                if 'leave' in description.lower():
                    event_type = "ResourceLeave"
                elif 'return' in description.lower():
                    event_type = "ResourceReturn"
                elif 'resign' in description.lower() or 'depart' in description.lower():
                    event_type = "ResourceDepart"
                elif 'join' in description.lower() or 'onboard' in description.lower():
                    event_type = "ResourceJoin"
                elif 'cr' in description.lower() and 'approv' in description.lower():
                    event_type = "CRApproved"
                elif 'consultant' in description.lower():
                    event_type = "ConsultantEngaged"

                events.append({
                    "type": event_type,
                    "description": description.strip(),
                    "date": event_date or datetime.now(),
                    "impact": "Medium"
                })

        return events

    def _extract_numeric(self, value: str) -> Optional[float]:
        """Extract numeric value from string"""
        if not value:
            return None

        # Remove common non-numeric characters
        cleaned = value.replace(',', '').replace('$', '').replace('%', '').replace('*', '')
        cleaned = cleaned.strip()

        # Handle special cases
        if cleaned == '-' or cleaned.lower() == 'n/a':
            return None

        # Try to extract number
        match = re.search(r'-?[\d.]+', cleaned)
        if match:
            try:
                return float(match.group())
            except ValueError:
                pass

        return None

    def _normalize_metric_name(self, name: str) -> str:
        """Normalize metric name to standard format"""
        # Convert to snake_case
        name = name.lower().strip()
        name = re.sub(r'[^\w\s]', '', name)
        name = re.sub(r'\s+', '_', name)
        return name

    def _infer_unit(self, metric_name: str) -> str:
        """Infer unit from metric name"""
        name_lower = metric_name.lower()

        if '%' in metric_name or 'percent' in name_lower or 'rate' in name_lower or 'coverage' in name_lower:
            return "percentage"
        elif 'count' in name_lower or 'commits' in name_lower or 'tests' in name_lower:
            return "count"
        elif 'loc' in name_lower or 'lines' in name_lower:
            return "lines"
        elif 'score' in name_lower:
            return "score"
        elif 'hours' in name_lower or 'time' in name_lower:
            return "hours"
        elif 'days' in name_lower:
            return "days"
        elif '$' in metric_name or 'cost' in name_lower or 'budget' in name_lower:
            return "dollars"
        elif 'velocity' in name_lower or 'points' in name_lower:
            return "story_points"
        else:
            return "value"

    def _period_to_date(self, period: str) -> Optional[datetime]:
        """Convert period string to representative date"""
        period_lower = period.lower()

        if 'december' in period_lower:
            return datetime(2025, 12, 15)
        elif 'january' in period_lower:
            return datetime(2026, 1, 15)
        elif 'february' in period_lower:
            return datetime(2026, 2, 15)
        elif 'march' in period_lower:
            return datetime(2026, 3, 15)

        # Try sprint
        sprint_match = re.search(r'sprint\s*(\d+)', period_lower)
        if sprint_match:
            sprint_num = int(sprint_match.group(1))
            base = datetime(2025, 12, 1)
            from datetime import timedelta
            return base + timedelta(weeks=(sprint_num - 1) * 2)

        # Try week
        week_match = re.search(r'week\s*(\d+)', period_lower)
        if week_match:
            week_num = int(week_match.group(1))
            base = datetime(2025, 12, 1)
            from datetime import timedelta
            return base + timedelta(weeks=week_num - 1)

        return None

    def _aggregate_metrics(self, metrics: List[ParsedMetricValue]) -> Dict[str, Any]:
        """Aggregate metrics into summary dict"""
        summary = {}

        for metric in metrics:
            key = metric.metric_name
            if metric.entity_id:
                key = f"{metric.entity_id}_{metric.metric_name}"
            if metric.period:
                key = f"{key}_{metric.period}"

            summary[key] = metric.value

        return summary
