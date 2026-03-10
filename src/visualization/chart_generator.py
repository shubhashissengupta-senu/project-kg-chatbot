"""
Chart Generator for Vega-Lite Visualizations
Generates appropriate chart specs based on data and query type.
"""

import json
import re
from typing import Dict, List, Any, Optional
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


class ChartGenerator:
    """Generates Vega-Lite chart specifications for data visualization."""

    # Keywords that suggest visualization would be helpful
    TREND_KEYWORDS = ['trend', 'over time', 'history', 'changed', 'progress', 'evolution']
    COMPARISON_KEYWORDS = ['compare', 'comparison', 'versus', 'vs', 'between', 'difference']
    DISTRIBUTION_KEYWORDS = ['distribution', 'breakdown', 'split', 'composition', 'allocation']
    METRICS_KEYWORDS = ['metrics', 'velocity', 'defects', 'bugs', 'coverage', 'productivity',
                        'performance', 'quality', 'code churn', 'commits', 'completion',
                        'rates', 'percentage', 'score', 'statistics', 'stats']
    FINANCIAL_KEYWORDS = ['budget', 'cost', 'revenue', 'margin', 'cpi', 'spi', 'expense']
    TIMELINE_KEYWORDS = ['timeline', 'staffing', 'personnel', 'gantt', 'schedule', 'joined',
                         'left the project', 'departed', 'onboarding', 'offboarding', 'team changes',
                         'staff changes', 'who joined', 'who left', 'resource changes']

    def __init__(self):
        self.chart_width = 500
        self.chart_height = 300

    def should_visualize(self, query: str, data: Dict, answer: str) -> bool:
        """Determine if the response should include a visualization."""
        query_lower = query.lower()

        # Check for visualization-worthy keywords
        has_trend = any(kw in query_lower for kw in self.TREND_KEYWORDS)
        has_comparison = any(kw in query_lower for kw in self.COMPARISON_KEYWORDS)
        has_distribution = any(kw in query_lower for kw in self.DISTRIBUTION_KEYWORDS)
        has_metrics = any(kw in query_lower for kw in self.METRICS_KEYWORDS)
        has_financial = any(kw in query_lower for kw in self.FINANCIAL_KEYWORDS)
        has_timeline = any(kw in query_lower for kw in self.TIMELINE_KEYWORDS)

        # Check if data contains numeric values worth visualizing
        has_numeric_data = self._has_visualizable_data(data, answer)

        # Timeline charts can work with date-based text data too
        if has_timeline:
            has_timeline_data = self._has_timeline_data(data, answer)
            return has_timeline_data

        return (has_trend or has_comparison or has_distribution or has_metrics or has_financial) and has_numeric_data

    def _has_visualizable_data(self, data: Dict, answer: str) -> bool:
        """Check if there's numeric data worth visualizing."""
        # Check data dict for numeric values
        if data:
            for key, value in data.items():
                if isinstance(value, (int, float)):
                    return True
                if isinstance(value, list) and len(value) >= 2:
                    return True
                if isinstance(value, dict):
                    for v in value.values():
                        if isinstance(v, (int, float)):
                            return True

        # Check answer text for numeric patterns (dates with values, percentages, etc.)
        numeric_patterns = [
            r'\d+%',  # percentages
            r'\d+\.\d+',  # decimals
            r'[\$\₹]\s*[\d,]+',  # currency
            r'\b\d{1,3}(?:,\d{3})+\b',  # large numbers with commas (450,000)
            r'\b\d{4,}\b',  # large numbers without commas (450000)
            r':\s*\d+\b',  # numbers after colon (Category: 123)
            r'\b\d+(?:ms|s|/s|kb|mb|gb)\b',  # numbers with units (200ms, 1000/s)
            r'\w+:\s*\d+(?:\s*,|\s*$)',  # label: number pattern (SD: 5, EWM: 4)
        ]
        for pattern in numeric_patterns:
            if len(re.findall(pattern, answer)) >= 2:
                return True

        return False

    def _has_timeline_data(self, data: Dict, answer: str) -> bool:
        """Check if there's timeline/staffing data worth visualizing."""
        # Check for date patterns in answer (staffing events)
        date_patterns = [
            r'(?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2},?\s*\d{4}',
            r'\d{1,2}/\d{1,2}/\d{4}',
            r'(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+\d{1,2}',
        ]
        for pattern in date_patterns:
            if len(re.findall(pattern, answer, re.IGNORECASE)) >= 1:
                return True

        # Check for staffing event keywords with names
        staffing_patterns = [
            r'(\w+)\s+(?:joined|left|departed|started|resigned)',
            r'(?:joined|left|departed|started|resigned).*?(\w+)',
        ]
        for pattern in staffing_patterns:
            if re.search(pattern, answer, re.IGNORECASE):
                return True

        # Check data dict for timeline info
        if data:
            timeline_keys = ['events', 'timeline', 'staffing', 'personnel', 'changes']
            for key in timeline_keys:
                if key in data:
                    return True

        return False

    def generate_chart(self, query: str, data: Dict, answer: str, query_type: str) -> Optional[Dict]:
        """Generate appropriate Vega-Lite chart spec based on query and data."""
        if not self.should_visualize(query, data, answer):
            return None

        query_lower = query.lower()

        # Check for timeline queries FIRST - they don't need numeric chart_data
        if any(kw in query_lower for kw in self.TIMELINE_KEYWORDS):
            timeline_data = self._extract_timeline_data(query, data, answer)
            if timeline_data and len(timeline_data) >= 1:
                return self._create_timeline_chart(timeline_data, query)
            # Fallback: try to extract regular chart data
            chart_data = self._extract_chart_data(query, data, answer, query_type)
            return self._create_bar_chart(chart_data, query) if chart_data and len(chart_data) >= 2 else None

        # Try to extract structured data from answer if data dict is sparse
        chart_data = self._extract_chart_data(query, data, answer, query_type)

        if not chart_data or len(chart_data) < 2:
            return None

        # Determine chart type based on query
        if any(kw in query_lower for kw in self.TREND_KEYWORDS):
            return self._create_line_chart(chart_data, query)
        elif any(kw in query_lower for kw in self.COMPARISON_KEYWORDS):
            return self._create_bar_chart(chart_data, query)
        elif any(kw in query_lower for kw in self.DISTRIBUTION_KEYWORDS):
            return self._create_pie_chart(chart_data, query)
        elif any(kw in query_lower for kw in self.METRICS_KEYWORDS + self.FINANCIAL_KEYWORDS):
            # For metrics, prefer line chart if temporal, else bar chart
            if self._has_temporal_data(chart_data):
                return self._create_line_chart(chart_data, query)
            else:
                return self._create_bar_chart(chart_data, query)

        # Default to bar chart
        return self._create_bar_chart(chart_data, query)

    def _has_temporal_data(self, data: List[Dict]) -> bool:
        """Check if data has temporal dimension."""
        if not data:
            return False
        first = data[0]
        return any(key in first for key in ['date', 'time', 'month', 'week', 'sprint', 'period'])

    def _extract_chart_data(self, query: str, data: Dict, answer: str, query_type: str) -> List[Dict]:
        """Extract structured data for charting from various sources."""
        chart_data = []

        # Try to get data from the data dict first
        if data:
            # Check for metrics data
            if 'metrics' in data:
                metrics = data['metrics']
                if isinstance(metrics, dict):
                    for key, value in metrics.items():
                        if isinstance(value, (int, float)):
                            chart_data.append({'category': key, 'value': value})

            # Check for timeline/temporal data
            if 'timeline' in data or 'history' in data:
                timeline = data.get('timeline') or data.get('history', [])
                if isinstance(timeline, list):
                    for item in timeline:
                        if isinstance(item, dict):
                            chart_data.append(item)

            # Check for sprint/velocity data
            if 'velocity' in data or 'sprints' in data:
                velocity_data = data.get('velocity') or data.get('sprints', [])
                if isinstance(velocity_data, list):
                    for item in velocity_data:
                        if isinstance(item, dict):
                            chart_data.append(item)

        # If no structured data, try to extract from answer text
        if not chart_data:
            chart_data = self._parse_answer_for_data(answer, query)

        return chart_data

    def _parse_answer_for_data(self, answer: str, query: str) -> List[Dict]:
        """Parse answer text to extract chartable data."""
        data = []

        # Pattern for "Month/Date: value" or "Category: value"
        patterns = [
            # "December 2025: 85%" or "January: 92%"
            r'((?:January|February|March|April|May|June|July|August|September|October|November|December)(?:\s+\d{4})?)[:\s]+(\d+(?:\.\d+)?)\s*%?',
            # "Sprint 1: 45 points"
            r'(Sprint\s+\d+)[:\s]+(\d+(?:\.\d+)?)',
            # "Week 1: 23"
            r'(Week\s+\d+)[:\s]+(\d+(?:\.\d+)?)',
            # "Velocity: 45" or "Defects: 12"
            r'([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)[:\s]+(\d+(?:\.\d+)?)\s*(?:points|%|bugs|defects)?',
        ]

        for pattern in patterns:
            matches = re.findall(pattern, answer, re.IGNORECASE)
            if len(matches) >= 2:
                for match in matches:
                    category, value = match
                    try:
                        data.append({
                            'category': category.strip(),
                            'value': float(value)
                        })
                    except ValueError:
                        continue
                if data:
                    break

        return data

    def _create_line_chart(self, data: List[Dict], query: str) -> Dict:
        """Create a Vega-Lite line chart specification."""
        # Determine x and y fields
        x_field = 'category'
        y_field = 'value'

        # Check if data has specific field names
        if data and isinstance(data[0], dict):
            keys = list(data[0].keys())
            for key in ['date', 'time', 'month', 'week', 'sprint', 'period', 'category']:
                if key in keys:
                    x_field = key
                    break
            for key in ['value', 'count', 'total', 'velocity', 'defects', 'score']:
                if key in keys:
                    y_field = key
                    break

        title = self._generate_chart_title(query, 'trend')

        return {
            "$schema": "https://vega.github.io/schema/vega-lite/v5.json",
            "title": title,
            "width": self.chart_width,
            "height": self.chart_height,
            "data": {"values": data},
            "mark": {
                "type": "line",
                "point": True,
                "color": "#667eea"
            },
            "encoding": {
                "x": {
                    "field": x_field,
                    "type": "ordinal",
                    "title": x_field.replace('_', ' ').title(),
                    "axis": {"labelAngle": -45}
                },
                "y": {
                    "field": y_field,
                    "type": "quantitative",
                    "title": y_field.replace('_', ' ').title()
                },
                "tooltip": [
                    {"field": x_field, "type": "nominal"},
                    {"field": y_field, "type": "quantitative"}
                ]
            },
            "config": {
                "background": "transparent",
                "axis": {
                    "labelColor": "#aaa",
                    "titleColor": "#fff",
                    "gridColor": "#333"
                },
                "title": {"color": "#fff"}
            }
        }

    def _create_bar_chart(self, data: List[Dict], query: str) -> Dict:
        """Create a Vega-Lite bar chart specification."""
        x_field = 'category'
        y_field = 'value'

        if data and isinstance(data[0], dict):
            keys = list(data[0].keys())
            for key in ['category', 'name', 'label', 'type', 'metric']:
                if key in keys:
                    x_field = key
                    break
            for key in ['value', 'count', 'total', 'amount', 'score']:
                if key in keys:
                    y_field = key
                    break

        title = self._generate_chart_title(query, 'comparison')

        return {
            "$schema": "https://vega.github.io/schema/vega-lite/v5.json",
            "title": title,
            "width": self.chart_width,
            "height": self.chart_height,
            "data": {"values": data},
            "mark": {
                "type": "bar",
                "color": "#667eea",
                "cornerRadiusTopLeft": 4,
                "cornerRadiusTopRight": 4
            },
            "encoding": {
                "x": {
                    "field": x_field,
                    "type": "nominal",
                    "title": x_field.replace('_', ' ').title(),
                    "axis": {"labelAngle": -45}
                },
                "y": {
                    "field": y_field,
                    "type": "quantitative",
                    "title": y_field.replace('_', ' ').title()
                },
                "tooltip": [
                    {"field": x_field, "type": "nominal"},
                    {"field": y_field, "type": "quantitative"}
                ]
            },
            "config": {
                "background": "transparent",
                "axis": {
                    "labelColor": "#aaa",
                    "titleColor": "#fff",
                    "gridColor": "#333"
                },
                "title": {"color": "#fff"}
            }
        }

    def _create_pie_chart(self, data: List[Dict], query: str) -> Dict:
        """Create a Vega-Lite pie/donut chart specification."""
        category_field = 'category'
        value_field = 'value'

        if data and isinstance(data[0], dict):
            keys = list(data[0].keys())
            for key in ['category', 'name', 'label', 'type']:
                if key in keys:
                    category_field = key
                    break
            for key in ['value', 'count', 'total', 'amount', 'percentage']:
                if key in keys:
                    value_field = key
                    break

        title = self._generate_chart_title(query, 'distribution')

        return {
            "$schema": "https://vega.github.io/schema/vega-lite/v5.json",
            "title": title,
            "width": self.chart_width,
            "height": self.chart_height,
            "data": {"values": data},
            "mark": {
                "type": "arc",
                "innerRadius": 50
            },
            "encoding": {
                "theta": {
                    "field": value_field,
                    "type": "quantitative"
                },
                "color": {
                    "field": category_field,
                    "type": "nominal",
                    "scale": {"scheme": "category10"},
                    "legend": {"labelColor": "#aaa", "titleColor": "#fff"}
                },
                "tooltip": [
                    {"field": category_field, "type": "nominal"},
                    {"field": value_field, "type": "quantitative"}
                ]
            },
            "config": {
                "background": "transparent",
                "title": {"color": "#fff"}
            }
        }

    def _extract_timeline_data(self, query: str, data: Dict, answer: str) -> List[Dict]:
        """Extract staffing/timeline events from answer text."""
        events = []
        seen_events = set()  # Avoid duplicates

        # Pattern to extract staffing events - multiple formats
        patterns = [
            # "Mousumi left January 23, 2026" or "Mousumi departed on Jan 23"
            (r'(\w+(?:\s+\w+)?)\s+(?:left|departed|resigned|exited)\s+(?:on\s+)?(?:the\s+project\s+)?(?:on\s+)?((?:January|February|March|April|May|June|July|August|September|October|November|December|Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+\d{1,2},?\s*\d{0,4})', 'departure'),
            # "Nayan joined January 28, 2026"
            (r'(\w+(?:\s+\w+)?)\s+(?:joined|started|onboarded)\s+(?:on\s+)?(?:the\s+project\s+)?(?:on\s+)?((?:January|February|March|April|May|June|July|August|September|October|November|December|Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+\d{1,2},?\s*\d{0,4})', 'joining'),
            # "Raj on medical leave December 26 - January 10"
            (r'(\w+)\s+(?:was\s+)?(?:on\s+)?(?:medical\s+)?leave\s+((?:January|February|March|April|May|June|July|August|September|October|November|December|Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+\d{1,2})', 'leave'),
            # "Lakshmi leaving March 6"
            (r'(\w+(?:\s+\w+)?)\s+(?:leaving|will leave|notice)\s+(?:on\s+)?((?:January|February|March|April|May|June|July|August|September|October|November|December|Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+\d{1,2},?\s*\d{0,4})', 'departure'),
            # "Sandeep joins to assist" - capitalized name followed by action verb
            (r'\b([A-Z][a-z]+)\s+(?:joins|joined|added)\b', 'joining'),
            # "Nayan provides/providing experience support"
            (r'\b([A-Z][a-z]+)\s+(?:provides?|providing|contributing|gives?)\s+(?:\w+\s+)?(?:support|experience|help)', 'joining'),
            # "Sandeep added to assist"
            (r'\b([A-Z][a-z]+)\s+(?:added|assigned|brought in)\s+(?:to\s+)?(?:assist|help|support)', 'joining'),
        ]

        # Also look for date context in surrounding text
        date_context = None
        date_match = re.search(r'((?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2},?\s*\d{4})', answer)
        if date_match:
            date_context = date_match.group(1)

        for pattern, event_type in patterns:
            matches = re.findall(pattern, answer, re.IGNORECASE)
            for match in matches:
                name = None
                date = date_context or 'TBD'

                # Handle both tuple (2 groups) and string (1 group) matches
                if isinstance(match, tuple) and len(match) == 2:
                    first, second = match
                    # Determine which is name and which is date
                    if re.match(r'(?:January|February|March|April|May|June|July|August|September|October|November|December)', first, re.IGNORECASE):
                        date, name = first, second
                    else:
                        name, date = first, second
                elif isinstance(match, str):
                    # Single group match - it's the name
                    name = match

                if not name:
                    continue

                # If no date extracted, use context date
                if date and not re.search(r'\d', str(date)) and date_context:
                    date = date_context

                # Filter out common non-name words
                skip_words = ['the', 'a', 'an', 'project', 'team', 'stream', 'ewm', 'sd',
                              'recovery', 'staffing', 'initial', 'week', 'sprint', 'plan',
                              'update', 'discussed', 'meeting', 'january', 'february', 'march',
                              'april', 'may', 'june', 'july', 'august', 'september', 'october',
                              'november', 'december']
                if name.lower().strip() in skip_words:
                    continue

                event_key = f"{name.strip().lower()}_{event_type}"
                if event_key not in seen_events:
                    seen_events.add(event_key)
                    events.append({
                        'person': name.strip().title(),
                        'date': str(date).strip() if date else 'TBD',
                        'event_type': event_type,
                        'order': len(events)
                    })

        # If no pattern matches, try to parse from data dict
        if not events and data:
            if 'staffing' in data or 'personnel' in data or 'events' in data:
                raw_events = data.get('staffing') or data.get('personnel') or data.get('events', [])
                if isinstance(raw_events, list):
                    for item in raw_events:
                        if isinstance(item, dict):
                            events.append(item)

        return events

    def _create_timeline_chart(self, data: List[Dict], query: str) -> Dict:
        """Create a Vega-Lite timeline/Gantt-style chart for staffing events."""
        title = "Staffing Timeline"
        if 'change' in query.lower():
            title = "Staffing Changes Timeline"

        # Assign colors based on event type
        color_map = {
            'joining': '#4ade80',      # green
            'departure': '#f87171',    # red
            'leave': '#fbbf24',        # yellow/amber
            'return': '#60a5fa',       # blue
        }

        # Enrich data with colors and normalize
        enriched_data = []
        for idx, event in enumerate(data):
            event_type = event.get('event_type', 'joining').lower()
            enriched_data.append({
                'person': event.get('person', f'Person {idx+1}'),
                'date': event.get('date', ''),
                'event_type': event_type.capitalize(),
                'color': color_map.get(event_type, '#667eea'),
                'order': event.get('order', idx)
            })

        return {
            "$schema": "https://vega.github.io/schema/vega-lite/v5.json",
            "title": title,
            "width": self.chart_width,
            "height": max(self.chart_height, len(enriched_data) * 50),
            "data": {"values": enriched_data},
            "mark": {
                "type": "point",
                "size": 200,
                "filled": True
            },
            "encoding": {
                "y": {
                    "field": "person",
                    "type": "nominal",
                    "title": "Team Member",
                    "sort": {"field": "order"},
                    "axis": {"labelColor": "#fff", "titleColor": "#fff"}
                },
                "x": {
                    "field": "date",
                    "type": "ordinal",
                    "title": "Date",
                    "axis": {"labelAngle": -45, "labelColor": "#aaa", "titleColor": "#fff"}
                },
                "color": {
                    "field": "event_type",
                    "type": "nominal",
                    "title": "Event",
                    "scale": {
                        "domain": ["Joining", "Departure", "Leave", "Return"],
                        "range": ["#4ade80", "#f87171", "#fbbf24", "#60a5fa"]
                    },
                    "legend": {"labelColor": "#aaa", "titleColor": "#fff"}
                },
                "shape": {
                    "field": "event_type",
                    "type": "nominal",
                    "scale": {
                        "domain": ["Joining", "Departure", "Leave", "Return"],
                        "range": ["circle", "cross", "triangle-up", "diamond"]
                    }
                },
                "tooltip": [
                    {"field": "person", "type": "nominal", "title": "Person"},
                    {"field": "date", "type": "nominal", "title": "Date"},
                    {"field": "event_type", "type": "nominal", "title": "Event"}
                ]
            },
            "config": {
                "background": "transparent",
                "axis": {
                    "labelColor": "#aaa",
                    "titleColor": "#fff",
                    "gridColor": "#333"
                },
                "title": {"color": "#fff"},
                "legend": {
                    "labelColor": "#aaa",
                    "titleColor": "#fff"
                }
            }
        }

    def _generate_chart_title(self, query: str, chart_type: str) -> str:
        """Generate an appropriate chart title based on query."""
        # Extract key terms from query
        query_lower = query.lower()

        # Common title patterns
        if 'velocity' in query_lower:
            return "Team Velocity Over Time" if chart_type == 'trend' else "Velocity Comparison"
        elif 'defect' in query_lower or 'bug' in query_lower:
            return "Defect Trends" if chart_type == 'trend' else "Defect Distribution"
        elif 'budget' in query_lower or 'cost' in query_lower:
            return "Budget Trend" if chart_type == 'trend' else "Cost Breakdown"
        elif 'quality' in query_lower:
            return "Quality Metrics Over Time" if chart_type == 'trend' else "Quality Metrics"
        elif 'productivity' in query_lower:
            return "Productivity Trends" if chart_type == 'trend' else "Productivity Comparison"
        elif 'coverage' in query_lower:
            return "Test Coverage Over Time" if chart_type == 'trend' else "Coverage by Component"
        elif 'staffing' in query_lower or 'personnel' in query_lower:
            return "Staffing Changes Timeline"
        elif 'timeline' in query_lower:
            return "Project Timeline"

        # Default titles
        type_titles = {
            'trend': "Trend Analysis",
            'comparison': "Comparison",
            'distribution': "Distribution",
            'timeline': "Timeline"
        }
        return type_titles.get(chart_type, "Data Visualization")

    def create_multi_series_line_chart(self, data: List[Dict], series_field: str,
                                        x_field: str, y_field: str, title: str) -> Dict:
        """Create a multi-series line chart for comparing multiple metrics."""
        return {
            "$schema": "https://vega.github.io/schema/vega-lite/v5.json",
            "title": title,
            "width": self.chart_width,
            "height": self.chart_height,
            "data": {"values": data},
            "mark": {
                "type": "line",
                "point": True
            },
            "encoding": {
                "x": {
                    "field": x_field,
                    "type": "ordinal",
                    "title": x_field.replace('_', ' ').title(),
                    "axis": {"labelAngle": -45}
                },
                "y": {
                    "field": y_field,
                    "type": "quantitative",
                    "title": y_field.replace('_', ' ').title()
                },
                "color": {
                    "field": series_field,
                    "type": "nominal",
                    "legend": {"labelColor": "#aaa", "titleColor": "#fff"}
                },
                "tooltip": [
                    {"field": series_field, "type": "nominal"},
                    {"field": x_field, "type": "nominal"},
                    {"field": y_field, "type": "quantitative"}
                ]
            },
            "config": {
                "background": "transparent",
                "axis": {
                    "labelColor": "#aaa",
                    "titleColor": "#fff",
                    "gridColor": "#333"
                },
                "title": {"color": "#fff"}
            }
        }

    def create_grouped_bar_chart(self, data: List[Dict], group_field: str,
                                  x_field: str, y_field: str, title: str) -> Dict:
        """Create a grouped bar chart for comparing categories across groups."""
        return {
            "$schema": "https://vega.github.io/schema/vega-lite/v5.json",
            "title": title,
            "width": self.chart_width,
            "height": self.chart_height,
            "data": {"values": data},
            "mark": {
                "type": "bar",
                "cornerRadiusTopLeft": 4,
                "cornerRadiusTopRight": 4
            },
            "encoding": {
                "x": {
                    "field": x_field,
                    "type": "nominal",
                    "title": x_field.replace('_', ' ').title()
                },
                "y": {
                    "field": y_field,
                    "type": "quantitative",
                    "title": y_field.replace('_', ' ').title()
                },
                "xOffset": {"field": group_field},
                "color": {
                    "field": group_field,
                    "type": "nominal",
                    "legend": {"labelColor": "#aaa", "titleColor": "#fff"}
                },
                "tooltip": [
                    {"field": group_field, "type": "nominal"},
                    {"field": x_field, "type": "nominal"},
                    {"field": y_field, "type": "quantitative"}
                ]
            },
            "config": {
                "background": "transparent",
                "axis": {
                    "labelColor": "#aaa",
                    "titleColor": "#fff",
                    "gridColor": "#333"
                },
                "title": {"color": "#fff"}
            }
        }
