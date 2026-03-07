"""
Query Planner
Plans query execution strategy based on user intent.
"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Any
from enum import Enum
import re


class QueryType(Enum):
    """Types of queries the system can handle"""
    POINT_IN_TIME = "point_in_time"      # "What was X on date Y?"
    TRAJECTORY = "trajectory"             # "How did X change over time?"
    COMPARISON = "comparison"             # "Compare X between A and B"
    CAUSAL = "causal"                     # "Why did X happen?"
    PREDICTIVE = "predictive"             # "What will happen with X?"
    ENTITY_LOOKUP = "entity_lookup"       # "Who is X? What is Y?"
    RELATIONSHIP = "relationship"         # "Who worked on X?"
    AGGREGATION = "aggregation"           # "How many X?"
    TIMELINE = "timeline"                 # "What happened in January?"
    STATUS = "status"                     # "What is the current status?"


@dataclass
class ExtractedEntity:
    """An entity extracted from user query"""
    entity_type: str
    value: str
    confidence: float = 1.0


@dataclass
class ExtractedDate:
    """A date reference extracted from user query"""
    date_type: str  # absolute, relative, period
    value: datetime
    label: str
    confidence: float = 1.0


@dataclass
class QueryPlan:
    """Execution plan for a query"""
    query_type: QueryType
    entities: List[ExtractedEntity]
    dates: List[ExtractedDate]
    time_constraints: Optional[Dict] = None
    filters: Dict = field(default_factory=dict)
    aggregations: List[str] = field(default_factory=list)
    output_format: str = "narrative"
    sub_queries: List['QueryPlan'] = None


class IntentClassifier:
    """Classifies user query intent"""

    INTENT_PATTERNS = {
        QueryType.POINT_IN_TIME: [
            r"what was", r"status on", r"at that time", r"on \w+ \d+",
            r"as of", r"at the end of", r"during \w+",
        ],
        QueryType.TRAJECTORY: [
            r"how did .* change", r"evolution of", r"trend",
            r"history of", r"progression", r"over time", r"throughout"
        ],
        QueryType.COMPARISON: [
            r"compare", r"difference between", r"versus", r" vs ",
            r"better than", r"worse than", r"changed from .* to"
        ],
        QueryType.CAUSAL: [
            r"why did", r"what caused", r"reason for", r"because",
            r"led to", r"resulted in", r"impact of", r"root cause"
        ],
        QueryType.PREDICTIVE: [
            r"will .* happen", r"forecast", r"predict", r"likely to",
            r"expected", r"what if", r"outlook", r"going to",
            r"main risks", r"what are the risks", r"risks"
        ],
        QueryType.ENTITY_LOOKUP: [
            r"who is", r"tell me about", r"describe",
            r"details of", r"information about", r"show me"
        ],
        QueryType.RELATIONSHIP: [
            r"who worked on", r"assigned to", r"responsible for",
            r"related to", r"connected to", r"involved in", r"owned by",
            r"who is on the team", r"team members", r"who are the", r"who left"
        ],
        QueryType.AGGREGATION: [
            r"how many", r"total", r"count", r"sum of",
            r"average", r"maximum", r"minimum", r"number of"
        ],
        QueryType.TIMELINE: [
            r"what happened", r"events in", r"timeline",
            r"sequence of", r"chronology", r"history"
        ],
        QueryType.STATUS: [
            r"current status", r"project status", r"status", r"right now", r"today", r"latest",
            r"where are we", r"how are we doing", r"how is the project", r"how are things"
        ]
    }

    def classify(self, query: str) -> QueryType:
        """Classify query intent"""
        query_lower = query.lower()

        scores = {qt: 0 for qt in QueryType}

        for query_type, patterns in self.INTENT_PATTERNS.items():
            for pattern in patterns:
                if re.search(pattern, query_lower):
                    scores[query_type] += 1

        max_score = max(scores.values())
        if max_score == 0:
            return QueryType.ENTITY_LOOKUP  # Default

        return max(scores, key=scores.get)


class EntityExtractor:
    """Extracts entities from user queries"""

    # Known entity patterns
    KNOWN_PERSONS = [
        "Ambarish", "Ryan", "Dhyanesh", "Raj", "Riaz",
        "Mousumi", "Nayan", "Lakshmi", "Jhanvi", "Krutika",
        "Sandeep", "Tara", "Vipul", "Tyler", "Jones",
        "Rick", "Roshan", "Sandra", "Michael", "David", "Priya"
    ]

    STREAMS = {
        "stream 1": "SD", "sd": "SD", "sales": "SD", "distribution": "SD",
        "stream 2": "EWM", "ewm": "EWM", "warehouse": "EWM"
    }

    METRICS = {
        "velocity": "velocity",
        "quality": "quality_score",
        "coverage": "test_coverage",
        "engagement": "engagement_score",
        "budget": "budget_variance",
        "defect": "defect_density",
        "test pass": "test_pass_rate"
    }

    def extract(self, query: str) -> List[ExtractedEntity]:
        """Extract entities from query"""
        entities = []
        query_lower = query.lower()

        # Extract persons
        for person in self.KNOWN_PERSONS:
            if person.lower() in query_lower:
                entities.append(ExtractedEntity(
                    entity_type="Person",
                    value=person
                ))

        # Extract streams
        for pattern, stream in self.STREAMS.items():
            if pattern in query_lower:
                entities.append(ExtractedEntity(
                    entity_type="Stream",
                    value=stream
                ))
                break

        # Extract change requests
        cr_matches = re.findall(r'cr[- ]?(\d+)', query_lower)
        for cr_num in cr_matches:
            entities.append(ExtractedEntity(
                entity_type="ChangeRequest",
                value=f"CR-{cr_num.zfill(3)}"
            ))

        # Extract risks
        risk_matches = re.findall(r'r[- ]?(\d+)', query_lower)
        for risk_num in risk_matches:
            entities.append(ExtractedEntity(
                entity_type="Risk",
                value=f"R-{risk_num.zfill(3)}"
            ))

        # Extract defects
        defect_matches = re.findall(r'def[- ]?(\d+)', query_lower)
        for defect_num in defect_matches:
            entities.append(ExtractedEntity(
                entity_type="Defect",
                value=f"DEF-{defect_num.zfill(3)}"
            ))

        # Extract metrics
        for keyword, metric in self.METRICS.items():
            if keyword in query_lower:
                entities.append(ExtractedEntity(
                    entity_type="Metric",
                    value=metric
                ))

        return entities


class DateExtractor:
    """Extracts date references from user queries"""

    # Project timeline reference
    PROJECT_START = datetime(2025, 12, 1)
    CURRENT_DATE = datetime(2026, 3, 7)

    MONTHS = {
        "december": datetime(2025, 12, 15),
        "january": datetime(2026, 1, 15),
        "february": datetime(2026, 2, 15),
        "march": datetime(2026, 3, 15),
        "april": datetime(2026, 4, 15)
    }

    def extract(self, query: str) -> List[ExtractedDate]:
        """Extract date references from query"""
        dates = []
        query_lower = query.lower()

        # Extract month references
        for month, date in self.MONTHS.items():
            if month in query_lower:
                dates.append(ExtractedDate(
                    date_type="period",
                    value=date,
                    label=month.title()
                ))

        # Extract week references
        week_matches = re.findall(r'week\s*(\d+)', query_lower)
        for week_num in week_matches:
            week_date = self.PROJECT_START + timedelta(weeks=int(week_num) - 1)
            dates.append(ExtractedDate(
                date_type="period",
                value=week_date,
                label=f"Week {week_num}"
            ))

        # Extract sprint references
        sprint_matches = re.findall(r'sprint\s*(\d+)', query_lower)
        for sprint_num in sprint_matches:
            sprint_date = self.PROJECT_START + timedelta(weeks=(int(sprint_num) - 1) * 2)
            dates.append(ExtractedDate(
                date_type="period",
                value=sprint_date,
                label=f"Sprint {sprint_num}"
            ))

        # Relative dates
        if "now" in query_lower or "current" in query_lower or "today" in query_lower:
            dates.append(ExtractedDate(
                date_type="relative",
                value=self.CURRENT_DATE,
                label="now"
            ))

        if "beginning" in query_lower or "start" in query_lower:
            dates.append(ExtractedDate(
                date_type="relative",
                value=self.PROJECT_START,
                label="project start"
            ))

        return dates


class QueryPlanner:
    """Plans query execution strategy"""

    def __init__(self):
        self.intent_classifier = IntentClassifier()
        self.entity_extractor = EntityExtractor()
        self.date_extractor = DateExtractor()

    def create_plan(self, query: str) -> QueryPlan:
        """
        Create execution plan for a query.

        Args:
            query: User's natural language query

        Returns:
            QueryPlan with execution strategy
        """
        # Classify intent
        query_type = self.intent_classifier.classify(query)

        # Extract entities and dates
        entities = self.entity_extractor.extract(query)
        dates = self.date_extractor.extract(query)

        # Build time constraints
        time_constraints = self._build_time_constraints(dates, query_type)

        # Build filters
        filters = self._build_filters(entities)

        # Determine aggregations
        aggregations = self._determine_aggregations(query, query_type)

        # Determine output format
        output_format = self._determine_output_format(query_type, query)

        plan = QueryPlan(
            query_type=query_type,
            entities=entities,
            dates=dates,
            time_constraints=time_constraints,
            filters=filters,
            aggregations=aggregations,
            output_format=output_format
        )

        # Create sub-queries for complex queries
        if query_type in [QueryType.COMPARISON, QueryType.CAUSAL]:
            plan.sub_queries = self._create_sub_queries(plan, query)

        return plan

    def _build_time_constraints(self,
                                dates: List[ExtractedDate],
                                query_type: QueryType) -> Optional[Dict]:
        """Build time constraints from extracted dates"""
        if not dates:
            if query_type == QueryType.STATUS:
                return {"point": datetime(2026, 3, 7)}
            return None

        if len(dates) == 1:
            if query_type == QueryType.POINT_IN_TIME:
                return {"point": dates[0].value}
            return {"start": dates[0].value}

        if len(dates) >= 2:
            sorted_dates = sorted(dates, key=lambda d: d.value)
            return {
                "start": sorted_dates[0].value,
                "end": sorted_dates[-1].value
            }

        return None

    def _build_filters(self, entities: List[ExtractedEntity]) -> Dict:
        """Build filters from extracted entities"""
        filters = {}
        for entity in entities:
            if entity.entity_type not in filters:
                filters[entity.entity_type] = []
            filters[entity.entity_type].append(entity.value)
        return filters

    def _determine_aggregations(self,
                                query: str,
                                query_type: QueryType) -> List[str]:
        """Determine what aggregations are needed"""
        aggregations = []
        query_lower = query.lower()

        if "average" in query_lower or "mean" in query_lower:
            aggregations.append("avg")
        if "total" in query_lower or "sum" in query_lower:
            aggregations.append("sum")
        if "count" in query_lower or "how many" in query_lower:
            aggregations.append("count")
        if "maximum" in query_lower or "highest" in query_lower or "best" in query_lower:
            aggregations.append("max")
        if "minimum" in query_lower or "lowest" in query_lower or "worst" in query_lower:
            aggregations.append("min")

        # Default aggregations for certain query types
        if query_type == QueryType.TRAJECTORY and not aggregations:
            aggregations = ["timeline"]
        if query_type == QueryType.COMPARISON and not aggregations:
            aggregations = ["diff"]
        if query_type == QueryType.AGGREGATION and not aggregations:
            aggregations = ["count"]

        return aggregations

    def _determine_output_format(self,
                                 query_type: QueryType,
                                 query: str) -> str:
        """Determine best output format"""
        query_lower = query.lower()

        if "chart" in query_lower or "graph" in query_lower or "visualiz" in query_lower:
            return "chart"
        if "table" in query_lower or "list" in query_lower:
            return "table"
        if "summary" in query_lower:
            return "summary"

        format_map = {
            QueryType.TRAJECTORY: "timeline",
            QueryType.COMPARISON: "comparison",
            QueryType.AGGREGATION: "metric",
            QueryType.TIMELINE: "timeline",
            QueryType.ENTITY_LOOKUP: "detail",
            QueryType.PREDICTIVE: "forecast",
            QueryType.STATUS: "status"
        }

        return format_map.get(query_type, "narrative")

    def _create_sub_queries(self,
                            parent_plan: QueryPlan,
                            query: str) -> List[QueryPlan]:
        """Create sub-queries for complex queries"""
        sub_queries = []

        if parent_plan.query_type == QueryType.COMPARISON:
            if parent_plan.time_constraints:
                # Create point-in-time queries for each period
                if "start" in parent_plan.time_constraints:
                    sub_queries.append(QueryPlan(
                        query_type=QueryType.POINT_IN_TIME,
                        entities=parent_plan.entities,
                        dates=[],
                        time_constraints={"point": parent_plan.time_constraints["start"]},
                        filters=parent_plan.filters,
                        output_format="data"
                    ))
                if "end" in parent_plan.time_constraints:
                    sub_queries.append(QueryPlan(
                        query_type=QueryType.POINT_IN_TIME,
                        entities=parent_plan.entities,
                        dates=[],
                        time_constraints={"point": parent_plan.time_constraints["end"]},
                        filters=parent_plan.filters,
                        output_format="data"
                    ))

        elif parent_plan.query_type == QueryType.CAUSAL:
            # Get timeline of events
            sub_queries.append(QueryPlan(
                query_type=QueryType.TIMELINE,
                entities=parent_plan.entities,
                dates=parent_plan.dates,
                time_constraints=parent_plan.time_constraints,
                filters={"entity_type": ["Event", "Risk", "ChangeRequest"]},
                output_format="timeline"
            ))

        return sub_queries
