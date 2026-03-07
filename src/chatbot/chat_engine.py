"""
Chat Engine
Main conversational interface for project queries.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional, Any
import logging

from .query_planner import QueryPlanner, QueryPlan, QueryType
from ..inference.query_engine import TemporalQueryEngine
from ..inference.risk_predictor import RiskPredictor
from ..time_series.metrics_store import TimeSeriesMetricsStore
from ..time_series.trend_analyzer import TrendAnalyzer
from ..rag.rag_engine import RAGEngine

logger = logging.getLogger(__name__)


@dataclass
class ChatMessage:
    """A message in the conversation"""
    role: str  # "user" or "assistant"
    content: str
    timestamp: datetime
    metadata: Dict = field(default_factory=dict)


@dataclass
class ChatResponse:
    """Response from the chat engine"""
    answer: str
    sources: List[Dict]
    data: Dict
    follow_up_questions: List[str]
    confidence: float
    query_type: str


class ConversationContext:
    """Manages conversation context and history"""

    def __init__(self, max_history: int = 10):
        self.messages: List[ChatMessage] = []
        self.max_history = max_history
        self.entities_discussed: List[str] = []
        self.time_context: Optional[datetime] = None

    def add_message(self, message: ChatMessage):
        """Add message to history"""
        self.messages.append(message)
        if len(self.messages) > self.max_history:
            self.messages = self.messages[-self.max_history:]

    def get_recent_context(self, n: int = 3) -> str:
        """Get recent conversation as string"""
        recent = self.messages[-n*2:] if len(self.messages) >= n*2 else self.messages
        return "\n".join([f"{m.role}: {m.content}" for m in recent])

    def add_entity(self, entity_id: str):
        """Track discussed entity"""
        if entity_id not in self.entities_discussed:
            self.entities_discussed.append(entity_id)

    def set_time_context(self, timestamp: datetime):
        """Set current time context"""
        self.time_context = timestamp

    def clear(self):
        """Clear conversation context"""
        self.messages = []
        self.entities_discussed = []
        self.time_context = None


class ChatEngine:
    """
    Main chat engine for project queries.
    Orchestrates query planning, execution, and response generation.
    """

    EXAMPLE_QUERIES = [
        "What is the current project status?",
        "What was the project status in January 2026?",
        "Who left the project and when?",
        "How did team velocity change over time?",
        "What caused the Stream 2 delay?",
        "Compare quality metrics between December and February",
        "What risks are predicted for the next sprint?",
        "Who worked on the Voice Picking feature?",
        "What happened when Mousumi left?",
        "Why did the budget go over in January?",
        "Tell me about CR-001",
        "What is the likelihood of meeting the April deadline?"
    ]

    def __init__(self,
                 query_engine: TemporalQueryEngine,
                 risk_predictor: RiskPredictor,
                 metrics_store: TimeSeriesMetricsStore,
                 rag_engine: RAGEngine = None,
                 llm_client: Any = None):
        self.query_engine = query_engine
        self.risk_predictor = risk_predictor
        self.metrics = metrics_store
        self.trend_analyzer = TrendAnalyzer(metrics_store)
        self.rag_engine = rag_engine
        self.llm = llm_client

        self.query_planner = QueryPlanner()
        self.context = ConversationContext()

    def chat(self, user_message: str, allowed_doc_types: List[str] = None) -> ChatResponse:
        """
        Process user message and generate response.

        Args:
            user_message: User's natural language query
            allowed_doc_types: List of document types user can access (for RBAC)

        Returns:
            ChatResponse with answer and metadata
        """
        # Add to context
        self.context.add_message(ChatMessage(
            role="user",
            content=user_message,
            timestamp=datetime.now()
        ))

        try:
            # Step 1: Create query plan
            plan = self.query_planner.create_plan(user_message)
            logger.debug(f"Query plan: {plan.query_type.value}")

            # Step 2: Execute query plan
            results = self._execute_plan(plan)

            # Step 3: Generate response
            response = self._generate_response(user_message, plan, results)

            # Step 4: If response is poor and RAG is available, try RAG
            if self.rag_engine and self._should_use_rag(response):
                logger.info("Falling back to RAG for better response")
                rag_response = self._query_rag(user_message, allowed_doc_types)
                if rag_response and rag_response.confidence > response.confidence:
                    response = ChatResponse(
                        answer=rag_response.answer,
                        sources=rag_response.sources,
                        data={"rag_used": True},
                        follow_up_questions=self._generate_follow_ups(plan, results),
                        confidence=rag_response.confidence,
                        query_type="rag_retrieval"
                    )

            # Add to context
            self.context.add_message(ChatMessage(
                role="assistant",
                content=response.answer,
                timestamp=datetime.now(),
                metadata={"sources": response.sources}
            ))

            return response

        except Exception as e:
            logger.error(f"Error processing query: {e}")
            # Try RAG as last resort
            if self.rag_engine:
                try:
                    rag_response = self._query_rag(user_message, allowed_doc_types)
                    if rag_response and rag_response.confidence > 0.1:
                        return ChatResponse(
                            answer=rag_response.answer,
                            sources=rag_response.sources,
                            data={"rag_used": True, "fallback": True},
                            follow_up_questions=["What else would you like to know?"],
                            confidence=rag_response.confidence,
                            query_type="rag_retrieval"
                        )
                except:
                    pass
            return ChatResponse(
                answer=f"I encountered an error processing your query: {str(e)}",
                sources=[],
                data={},
                follow_up_questions=["Could you rephrase your question?"],
                confidence=0.0,
                query_type="error"
            )

    def _execute_plan(self, plan: QueryPlan) -> Dict[str, Any]:
        """Execute the query plan"""
        results = {
            "plan_type": plan.query_type.value,
            "data": {},
            "metrics": {}
        }

        # Get timestamp for queries
        timestamp = None
        if plan.time_constraints:
            timestamp = plan.time_constraints.get("point") or plan.time_constraints.get("end")

        if plan.query_type == QueryType.STATUS:
            timestamp = timestamp or datetime(2026, 3, 7)
            results["data"] = self.query_engine.get_project_state_at(timestamp)

        elif plan.query_type == QueryType.POINT_IN_TIME:
            if timestamp:
                results["data"] = self.query_engine.get_project_state_at(timestamp)

        elif plan.query_type == QueryType.TRAJECTORY:
            start = plan.time_constraints.get("start") if plan.time_constraints else datetime(2025, 12, 1)
            end = plan.time_constraints.get("end") if plan.time_constraints else datetime(2026, 3, 7)

            # Get trajectory for entities
            for entity in plan.entities:
                entity_id = f"{entity.entity_type.upper()}_{entity.value.upper().replace(' ', '_')}"
                results["data"][entity.value] = self.query_engine.get_entity_trajectory(
                    entity_id, start, end
                )

            # Get metric trends
            for entity in plan.entities:
                if entity.entity_type == "Metric":
                    trend = self.trend_analyzer.get_metric_summary(entity.value)
                    results["metrics"][entity.value] = trend

        elif plan.query_type == QueryType.COMPARISON:
            if plan.sub_queries and len(plan.sub_queries) >= 2:
                results["data"]["period1"] = self._execute_plan(plan.sub_queries[0])
                results["data"]["period2"] = self._execute_plan(plan.sub_queries[1])

                # Compare metrics
                for entity in plan.entities:
                    if entity.entity_type == "Metric":
                        start = plan.time_constraints.get("start") if plan.time_constraints else datetime(2025, 12, 1)
                        end = plan.time_constraints.get("end") if plan.time_constraints else datetime(2026, 3, 7)
                        mid = start + (end - start) / 2
                        comparison = self.metrics.compare_periods(
                            entity.value,
                            (start, mid),
                            (mid, end)
                        )
                        results["metrics"][entity.value] = comparison

        elif plan.query_type == QueryType.PREDICTIVE:
            timestamp = timestamp or datetime(2026, 3, 7)
            predictions = self.risk_predictor.predict_risks(timestamp)
            results["data"]["predictions"] = [
                {
                    "risk_type": p.risk_type,
                    "description": p.description,
                    "probability": p.probability,
                    "severity": p.severity,
                    "factors": p.contributing_factors,
                    "actions": p.recommended_actions
                }
                for p in predictions
            ]

        elif plan.query_type == QueryType.CAUSAL:
            # Get timeline and look for impact chains
            for entity in plan.entities:
                entity_id = f"{entity.entity_type.upper()}_{entity.value.upper().replace(' ', '_')}"
                impact_chain = self.query_engine.find_impact_chain(entity_id)
                results["data"][entity.value] = {
                    "impact_chain": impact_chain
                }

            # Get timeline
            if plan.time_constraints:
                start = plan.time_constraints.get("start", datetime(2025, 12, 1))
                end = plan.time_constraints.get("end", datetime(2026, 3, 7))
                results["data"]["timeline"] = self.query_engine.get_timeline(start, end)

        elif plan.query_type == QueryType.TIMELINE:
            start = plan.time_constraints.get("start") if plan.time_constraints else datetime(2025, 12, 1)
            end = plan.time_constraints.get("end") if plan.time_constraints else datetime(2026, 3, 7)
            results["data"] = self.query_engine.get_timeline(start, end)

        elif plan.query_type == QueryType.ENTITY_LOOKUP:
            for entity in plan.entities:
                entity_id = f"{entity.entity_type.upper()}_{entity.value.upper().replace(' ', '_')}"
                entity_data = self.query_engine.get_entity_state_at(
                    entity_id,
                    timestamp or datetime(2026, 3, 7)
                )
                if entity_data:
                    results["data"][entity.value] = entity_data

                # Get related entities
                related = self.query_engine.get_related_entities(entity_id)
                results["data"][f"{entity.value}_related"] = related

        elif plan.query_type == QueryType.RELATIONSHIP:
            for entity in plan.entities:
                entity_id = f"{entity.entity_type.upper()}_{entity.value.upper().replace(' ', '_')}"
                related = self.query_engine.get_related_entities(entity_id)
                results["data"][entity.value] = related

        elif plan.query_type == QueryType.AGGREGATION:
            for entity in plan.entities:
                if entity.entity_type == "Metric":
                    for agg in plan.aggregations:
                        value = self.query_engine.aggregate_metric(entity.value, agg)
                        results["data"][f"{entity.value}_{agg}"] = value
                else:
                    # Count entities
                    count = self.query_engine.count_entities(
                        entity.entity_type,
                        timestamp
                    )
                    results["data"][f"{entity.entity_type}_count"] = count

        return results

    def _generate_response(self,
                           query: str,
                           plan: QueryPlan,
                           results: Dict) -> ChatResponse:
        """Generate natural language response"""

        # Build response based on query type
        answer = self._build_answer(plan, results)

        # Extract sources
        sources = self._extract_sources(results)

        # Generate follow-up questions
        follow_ups = self._generate_follow_ups(plan, results)

        # Calculate confidence
        confidence = self._calculate_confidence(results)

        return ChatResponse(
            answer=answer,
            sources=sources,
            data=results.get("data", {}),
            follow_up_questions=follow_ups,
            confidence=confidence,
            query_type=plan.query_type.value
        )

    def _build_answer(self, plan: QueryPlan, results: Dict) -> str:
        """Build natural language answer"""
        data = results.get("data", {})

        if plan.query_type == QueryType.STATUS:
            return self._format_status_response(data)

        elif plan.query_type == QueryType.POINT_IN_TIME:
            timestamp = plan.time_constraints.get("point") if plan.time_constraints else None
            return self._format_point_in_time_response(data, timestamp)

        elif plan.query_type == QueryType.TRAJECTORY:
            return self._format_trajectory_response(data, results.get("metrics", {}))

        elif plan.query_type == QueryType.COMPARISON:
            return self._format_comparison_response(data, results.get("metrics", {}))

        elif plan.query_type == QueryType.PREDICTIVE:
            return self._format_predictive_response(data)

        elif plan.query_type == QueryType.CAUSAL:
            return self._format_causal_response(data)

        elif plan.query_type == QueryType.TIMELINE:
            return self._format_timeline_response(data)

        elif plan.query_type == QueryType.ENTITY_LOOKUP:
            return self._format_entity_response(data)

        elif plan.query_type == QueryType.RELATIONSHIP:
            return self._format_relationship_response(data)

        elif plan.query_type == QueryType.AGGREGATION:
            return self._format_aggregation_response(data)

        return "I found relevant information but need help formatting the response."

    def _format_status_response(self, data: Dict) -> str:
        """Format project status response"""
        if "error" in data:
            return f"Unable to retrieve status: {data['error']}"

        parts = []
        parts.append(f"**Project Status as of {data.get('timestamp', 'now')}**")

        # Team
        team = data.get("team", [])
        parts.append(f"\n**Team:** {len(team)} active members")

        # Streams
        streams = data.get("streams", [])
        for stream in streams:
            status = stream.get("status", "Unknown")
            completion = stream.get("completion_pct", 0)
            parts.append(f"- {stream.get('name')}: {status} ({completion:.0f}% complete)")

        # Risks
        risks = data.get("open_risks", [])
        if risks:
            parts.append(f"\n**Open Risks:** {len(risks)}")
            for risk in risks[:3]:
                parts.append(f"- {risk.get('description', 'Unknown risk')}")

        # Metrics
        metrics = data.get("metrics", {})
        if metrics:
            parts.append("\n**Key Metrics:**")
            for key, value in list(metrics.items())[:5]:
                parts.append(f"- {key}: {value}")

        return "\n".join(parts)

    def _format_point_in_time_response(self, data: Dict, timestamp: datetime) -> str:
        """Format point-in-time response"""
        parts = []
        ts_str = timestamp.strftime("%B %d, %Y") if timestamp else "the specified time"
        parts.append(f"**Project State on {ts_str}:**")

        if "team" in data:
            parts.append(f"\nTeam size: {len(data['team'])} members")

        if "streams" in data:
            for stream in data["streams"]:
                parts.append(f"- {stream.get('name')}: {stream.get('status')}")

        return "\n".join(parts)

    def _format_trajectory_response(self, data: Dict, metrics: Dict) -> str:
        """Format trajectory/trend response"""
        parts = ["**Changes Over Time:**"]

        for entity, trajectory in data.items():
            if isinstance(trajectory, list) and trajectory:
                parts.append(f"\n**{entity}:**")
                for state in trajectory[:5]:
                    ts = state.get("timestamp")
                    ts_str = ts.strftime("%b %d") if hasattr(ts, 'strftime') else str(ts)
                    parts.append(f"- {ts_str}: {state.get('label', '')}")

        for metric_name, trend in metrics.items():
            if trend:
                parts.append(f"\n**{metric_name} Trend:**")
                parts.append(f"- Direction: {trend.get('trend', {}).get('direction', 'unknown')}")
                parts.append(f"- Change: {trend.get('trend', {}).get('change_pct', 0):.1f}%")

        return "\n".join(parts)

    def _format_comparison_response(self, data: Dict, metrics: Dict) -> str:
        """Format comparison response"""
        parts = ["**Comparison Results:**"]

        if "period1" in data and "period2" in data:
            parts.append("\nPeriod comparison available.")

        for metric_name, comparison in metrics.items():
            if comparison and "comparison" in comparison:
                parts.append(f"\n**{metric_name}:**")
                comp = comparison["comparison"]
                parts.append(f"- Change: {comp.get('mean_change_pct', 0):.1f}%")

        return "\n".join(parts)

    def _format_predictive_response(self, data: Dict) -> str:
        """Format predictive response"""
        predictions = data.get("predictions", [])
        if not predictions:
            return "No significant risks predicted in the near term."

        parts = ["**Risk Predictions:**"]
        for pred in predictions[:5]:
            prob_pct = pred.get("probability", 0) * 100
            parts.append(f"\n**{pred.get('description')}**")
            parts.append(f"- Probability: {prob_pct:.0f}%")
            parts.append(f"- Severity: {pred.get('severity')}")
            if pred.get("factors"):
                parts.append(f"- Factors: {', '.join(pred['factors'][:2])}")
            if pred.get("actions"):
                parts.append(f"- Recommended: {pred['actions'][0]}")

        return "\n".join(parts)

    def _format_causal_response(self, data: Dict) -> str:
        """Format causal analysis response"""
        parts = ["**Causal Analysis:**"]

        for entity, analysis in data.items():
            if entity == "timeline":
                continue
            if isinstance(analysis, dict) and "impact_chain" in analysis:
                chain = analysis["impact_chain"]
                if chain:
                    parts.append(f"\n**Impact of {entity}:**")
                    parts.append(f"- Affected {len(chain)} entities")

        if "timeline" in data:
            events = data["timeline"]
            if events:
                parts.append("\n**Related Events:**")
                for event in events[:5]:
                    parts.append(f"- {event.get('description', 'Event')}")

        return "\n".join(parts)

    def _format_timeline_response(self, data: Dict) -> str:
        """Format timeline response"""
        if not data or not isinstance(data, list):
            return "No events found in the specified period."

        parts = ["**Timeline of Events:**"]
        for event in data[:10]:
            ts = event.get("timestamp")
            ts_str = ts.strftime("%b %d") if hasattr(ts, 'strftime') else str(ts)
            parts.append(f"- {ts_str}: {event.get('description', event.get('type', 'Event'))}")

        return "\n".join(parts)

    def _format_entity_response(self, data: Dict) -> str:
        """Format entity lookup response"""
        parts = []
        for entity_name, entity_data in data.items():
            if "_related" in entity_name:
                continue

            if entity_data:
                parts.append(f"**{entity_name}:**")
                for key, value in entity_data.items():
                    if key not in ["id", "entity_type", "source"]:
                        parts.append(f"- {key}: {value}")

        return "\n".join(parts) if parts else "Entity not found."

    def _format_relationship_response(self, data: Dict) -> str:
        """Format relationship response"""
        parts = ["**Related Entities:**"]
        for entity, relations in data.items():
            if isinstance(relations, list):
                parts.append(f"\n**{entity}:**")
                for rel in relations[:5]:
                    parts.append(f"- {rel.get('relation')}: {rel.get('entity_id')}")

        return "\n".join(parts)

    def _format_aggregation_response(self, data: Dict) -> str:
        """Format aggregation response"""
        parts = ["**Results:**"]
        for key, value in data.items():
            parts.append(f"- {key}: {value}")

        return "\n".join(parts)

    def _extract_sources(self, results: Dict) -> List[Dict]:
        """Extract source references from results"""
        sources = []
        # Add source tracking logic here
        return sources

    def _generate_follow_ups(self, plan: QueryPlan, results: Dict) -> List[str]:
        """Generate relevant follow-up questions"""
        follow_ups = []

        if plan.query_type == QueryType.STATUS:
            follow_ups.append("How has this changed from last month?")
            follow_ups.append("What are the main risks?")

        elif plan.query_type == QueryType.TRAJECTORY:
            follow_ups.append("What caused the biggest changes?")
            follow_ups.append("How does this compare to the target?")

        elif plan.query_type == QueryType.PREDICTIVE:
            follow_ups.append("What actions can mitigate these risks?")
            follow_ups.append("Which risk should be prioritized?")

        elif plan.query_type == QueryType.ENTITY_LOOKUP:
            follow_ups.append("What is related to this?")
            follow_ups.append("How has this changed over time?")

        elif plan.query_type == QueryType.COMPARISON:
            follow_ups.append("What drove these changes?")
            follow_ups.append("What is the forecast for next month?")

        return follow_ups[:3]

    def _calculate_confidence(self, results: Dict) -> float:
        """Calculate confidence in the response"""
        data = results.get("data", {})

        if not data:
            return 0.3

        # More data = higher confidence
        if isinstance(data, dict):
            data_points = len(data)
        elif isinstance(data, list):
            data_points = len(data)
        else:
            data_points = 1

        return min(0.95, 0.5 + data_points * 0.05)

    def _should_use_rag(self, response: 'ChatResponse') -> bool:
        """Determine if RAG should be used for better response"""
        # Use RAG if response is poor
        if response.confidence < 0.4:
            return True
        if "not found" in response.answer.lower():
            return True
        if "couldn't find" in response.answer.lower():
            return True
        if response.answer.strip() == "":
            return True
        if "Entity not found" in response.answer:
            return True
        # Use RAG for very short responses
        if len(response.answer) < 50 and response.confidence < 0.7:
            return True
        return False

    def _query_rag(self, query: str, allowed_doc_types: List[str] = None) -> Optional[Any]:
        """Query the RAG engine with RBAC filtering"""
        if not self.rag_engine:
            return None
        try:
            return self.rag_engine.query(query, top_k=5, allowed_doc_types=allowed_doc_types)
        except Exception as e:
            logger.error(f"RAG query failed: {e}")
            return None

    def get_examples(self) -> List[str]:
        """Get example queries"""
        return self.EXAMPLE_QUERIES

    def clear_context(self):
        """Clear conversation context"""
        self.context.clear()
