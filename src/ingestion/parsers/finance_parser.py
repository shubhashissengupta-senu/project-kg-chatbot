"""
Finance Review Meeting Parser
Parses monthly finance review meeting markdown files.
"""

import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Optional, Any

from .base_parser import BaseParser, ParsedDocument, ParsedEntity, ParsedRelationship


@dataclass
class FinancialMetric:
    """A financial metric"""
    name: str
    budget: Optional[float]
    actual: Optional[float]
    variance: Optional[float]
    variance_pct: Optional[float]


@dataclass
class ContingencyItem:
    """Contingency allocation item"""
    category: str
    allocated: float
    used: float
    remaining: float


class FinanceReviewParser(BaseParser):
    """Parser for finance review meeting markdown files"""

    def can_parse(self, filepath: Path) -> bool:
        """Check if file is a finance review file"""
        filename = filepath.name.lower()
        return 'finance' in filename and 'review' in filename and filepath.suffix == '.md'

    def parse(self, filepath: Path) -> ParsedDocument:
        """Parse a finance review markdown file"""
        content = filepath.read_text(encoding='utf-8')

        # Extract metadata
        meeting_date = self._extract_meeting_date(content, filepath)
        meeting_number = self._extract_meeting_number(filepath)

        # Create meeting entity ID
        meeting_id = f"MEETING_FINANCE_{meeting_date.strftime('%Y%m%d')}" if meeting_date else f"MEETING_{filepath.stem}"

        # Parse components
        financial_metrics = self._extract_financial_metrics(content)
        contingency = self._extract_contingency(content)
        cr_financials = self._extract_cr_financials(content)
        cost_performance = self._extract_cost_performance(content)

        entities = []
        relationships = []
        metrics_dict = {}

        # Meeting entity
        entities.append(ParsedEntity(
            entity_type="Meeting",
            entity_id=meeting_id,
            properties={
                "meeting_type": "FinanceReview",
                "date": meeting_date,
                "meeting_number": meeting_number,
                "finance_controller": self._extract_finance_controller(content),
                "financial_status": self._extract_financial_status(content),
                "financial_grade": self._extract_financial_grade(content),
                "cpi": cost_performance.get("cpi"),
                "spi": cost_performance.get("spi"),
                "budget_variance_pct": cost_performance.get("variance_pct"),
                "projected_margin": self._extract_projected_margin(content),
            },
            source_file=str(filepath)
        ))

        # Financial metrics as entities
        for metric in financial_metrics:
            metric_id = f"METRIC_FIN_{metric.name}_{meeting_date.strftime('%Y%m%d')}" if meeting_date else f"METRIC_{metric.name}"
            entities.append(ParsedEntity(
                entity_type="MetricSnapshot",
                entity_id=metric_id,
                properties={
                    "metric_name": f"financial_{metric.name}",
                    "budget": metric.budget,
                    "actual": metric.actual,
                    "variance": metric.variance,
                    "variance_pct": metric.variance_pct,
                    "timestamp": meeting_date,
                    "source": "Finance Review"
                },
                source_file=str(filepath)
            ))

            if metric.actual is not None:
                metrics_dict[f"budget_{metric.name}"] = metric.budget
                metrics_dict[f"actual_{metric.name}"] = metric.actual
                if metric.variance_pct is not None:
                    metrics_dict[f"variance_pct_{metric.name}"] = metric.variance_pct

        # Cost performance metrics
        for key, value in cost_performance.items():
            if value is not None:
                metrics_dict[key] = value

        # Contingency metrics
        for item in contingency:
            metrics_dict[f"contingency_{item.category}_allocated"] = item.allocated
            metrics_dict[f"contingency_{item.category}_used"] = item.used
            metrics_dict[f"contingency_{item.category}_remaining"] = item.remaining

        # CR financial impact
        for cr_id, cr_data in cr_financials.items():
            cr_entity_id = f"CR_{cr_id}"
            # Check if CR entity exists, update financial data
            entities.append(ParsedEntity(
                entity_type="ChangeRequest",
                entity_id=cr_entity_id,
                properties={
                    "cr_id": cr_id,
                    "value": cr_data.get("value"),
                    "margin": cr_data.get("margin"),
                    "margin_pct": cr_data.get("margin_pct"),
                    "status": cr_data.get("status"),
                },
                source_file=str(filepath)
            ))

            relationships.append(ParsedRelationship(
                relation_type="DISCUSSED_IN",
                from_entity=cr_entity_id,
                to_entity=meeting_id
            ))

        return ParsedDocument(
            document_type="FinanceReview",
            source_file=str(filepath),
            timestamp=meeting_date or datetime.now(),
            entities=entities,
            relationships=relationships,
            metrics=metrics_dict,
            raw_text=content,
            metadata={
                "meeting_number": meeting_number,
                "cost_performance": cost_performance,
                "contingency_summary": {
                    "total_allocated": sum(c.allocated for c in contingency),
                    "total_used": sum(c.used for c in contingency),
                    "total_remaining": sum(c.remaining for c in contingency),
                },
                "cr_financials": cr_financials,
            }
        )

    def _extract_meeting_date(self, content: str, filepath: Path) -> Optional[datetime]:
        """Extract meeting date"""
        # Try filename: Finance_Review_01_Dec23_2025.md
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

    def _extract_finance_controller(self, content: str) -> Optional[str]:
        """Extract Finance Controller name"""
        match = re.search(r'\*\*Finance Controller:\*\*\s*(\w+\s*\w*)', content)
        return match.group(1).strip() if match else "Rick Stratford"

    def _extract_financial_status(self, content: str) -> str:
        """Extract financial status (RAG)"""
        match = re.search(r'Financial Status[:\s]*[🟢🟡🔴]?\s*(\w+)', content, re.IGNORECASE)
        if match:
            return self.normalize_status(match.group(1))
        return "Unknown"

    def _extract_financial_grade(self, content: str) -> Optional[str]:
        """Extract financial grade"""
        match = re.search(r'Financial Grade:\s*([A-F][+-]?)', content, re.IGNORECASE)
        return match.group(1) if match else None

    def _extract_financial_metrics(self, content: str) -> List[FinancialMetric]:
        """Extract financial metrics"""
        metrics = []

        # Pattern for budget vs actual table
        # | Month | Budget | Actual | Variance |
        metric_pattern = r'\|\s*(\w+)\s*\|\s*\$?([\d,]+)\s*\|\s*\$?([\d,]+)\s*\|\s*([+-]?[\d.]+%?)\s*\|'

        for match in re.finditer(metric_pattern, content):
            name, budget, actual, variance = match.groups()

            # Skip headers
            if 'budget' in name.lower() or 'month' in name.lower():
                continue

            try:
                budget_num = float(budget.replace(',', ''))
                actual_num = float(actual.replace(',', ''))
                variance_str = variance.replace('%', '').replace('+', '')
                variance_pct = float(variance_str) if variance_str else None
            except ValueError:
                continue

            metrics.append(FinancialMetric(
                name=name.strip().lower(),
                budget=budget_num,
                actual=actual_num,
                variance=actual_num - budget_num,
                variance_pct=variance_pct
            ))

        return metrics

    def _extract_contingency(self, content: str) -> List[ContingencyItem]:
        """Extract contingency allocation"""
        contingency = []

        # Pattern for contingency table
        # | Category | Allocated | Used | Remaining |
        contingency_pattern = r'\|\s*(\w+)\s*\|\s*\$?([\d,]+)\s*\|\s*\$?([\d,]+)\s*\|\s*\$?([\d,]+)\s*\|'

        section = self.extract_section(content, "Contingency")
        if section:
            for match in re.finditer(contingency_pattern, section):
                category, allocated, used, remaining = match.groups()

                # Skip headers
                if 'category' in category.lower() or 'allocated' in category.lower():
                    continue

                try:
                    contingency.append(ContingencyItem(
                        category=category.strip().lower(),
                        allocated=float(allocated.replace(',', '')),
                        used=float(used.replace(',', '')),
                        remaining=float(remaining.replace(',', ''))
                    ))
                except ValueError:
                    continue

        return contingency

    def _extract_cost_performance(self, content: str) -> Dict[str, float]:
        """Extract cost performance indices"""
        performance = {}

        # CPI
        cpi_match = re.search(r'CPI[:\s]*(\d+\.?\d*)', content, re.IGNORECASE)
        if cpi_match:
            performance["cpi"] = float(cpi_match.group(1))

        # SPI
        spi_match = re.search(r'SPI[:\s]*(\d+\.?\d*)', content, re.IGNORECASE)
        if spi_match:
            performance["spi"] = float(spi_match.group(1))

        # Budget variance
        variance_match = re.search(r'[Bb]udget\s*[Vv]ariance[:\s]*([+-]?\d+\.?\d*)%', content)
        if variance_match:
            performance["variance_pct"] = float(variance_match.group(1))

        return performance

    def _extract_projected_margin(self, content: str) -> Optional[float]:
        """Extract projected margin percentage"""
        match = re.search(r'[Mm]argin[:\s]*(\d+\.?\d*)%', content)
        return float(match.group(1)) if match else None

    def _extract_cr_financials(self, content: str) -> Dict[str, Dict]:
        """Extract CR financial details"""
        cr_financials = {}

        # Pattern for CR financial table
        # | CR | Description | Value | Margin | Status |
        cr_pattern = r'\|\s*(CR-?\d+)\s*\|\s*([^|]+)\s*\|\s*\$?([\d,]+)\s*\|\s*([\d.]+%?)\s*\|\s*([^|]+)\s*\|'

        for match in re.finditer(cr_pattern, content):
            cr_id, desc, value, margin, status = match.groups()

            # Skip headers
            if 'description' in desc.lower():
                continue

            try:
                value_num = float(value.replace(',', ''))
                margin_str = margin.replace('%', '')
                margin_num = float(margin_str) if margin_str else None
            except ValueError:
                continue

            cr_id_normalized = cr_id.replace('-', '-').upper()
            cr_financials[cr_id_normalized] = {
                "description": desc.strip(),
                "value": value_num,
                "margin_pct": margin_num,
                "margin": value_num * margin_num / 100 if margin_num else None,
                "status": self.normalize_status(status.strip())
            }

        return cr_financials
