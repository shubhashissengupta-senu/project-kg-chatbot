"""
Chat Engine
Main conversational interface for project queries.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional, Any, TYPE_CHECKING
import logging

from .query_planner import QueryPlanner, QueryPlan, QueryType
from ..inference.query_engine import TemporalQueryEngine
from ..inference.risk_predictor import RiskPredictor
from ..time_series.metrics_store import TimeSeriesMetricsStore
from ..time_series.trend_analyzer import TrendAnalyzer
from ..rag.rag_engine import RAGEngine
from ..llm.llm_service import LLMService

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
                 llm_client: LLMService = None):
        self.query_engine = query_engine
        self.risk_predictor = risk_predictor
        self.metrics = metrics_store
        self.trend_analyzer = TrendAnalyzer(metrics_store)
        self.rag_engine = rag_engine
        self.llm: LLMService = llm_client

        self.query_planner = QueryPlanner()
        self.context = ConversationContext()

        # Log LLM availability
        if self.llm and self.llm.is_available():
            logger.info("ChatEngine initialized with LLM support")
        else:
            logger.info("ChatEngine initialized without LLM (using templates)")

    def _get_latest_data_timestamp(self) -> datetime:
        """Get the latest timestamp from the knowledge graph data (documents/events)"""
        try:
            # Get timeline events to find the latest actual data date
            timeline = self.query_engine.get_timeline(
                datetime(2025, 1, 1),
                datetime(2027, 12, 31)
            )
            if timeline:
                # Filter for meaningful events (meetings, reviews)
                meaningful_events = [
                    e for e in timeline
                    if e.get('type') and 'Meeting' in str(e.get('type', ''))
                ]
                if meaningful_events:
                    # Get the latest event timestamp
                    latest = max(meaningful_events, key=lambda x: x.get('timestamp', datetime.min))
                    ts = latest.get('timestamp')
                    if isinstance(ts, datetime):
                        return ts
                    elif isinstance(ts, str):
                        return datetime.fromisoformat(ts.replace('Z', '+00:00').split('+')[0])
        except Exception as e:
            logger.warning(f"Could not get latest timestamp from timeline: {e}")

        # Fallback: try snapshots
        try:
            snapshots = self.query_engine.snapshots
            if hasattr(snapshots, 'timeline') and snapshots.timeline:
                # Filter out "today" dates - look for actual document dates
                valid_dates = [t for t in snapshots.timeline if t < datetime.now()]
                if valid_dates:
                    return max(valid_dates)
        except Exception as e:
            logger.warning(f"Could not get latest timestamp from snapshots: {e}")

        # Default fallback - last known document date
        return datetime(2026, 2, 23)

    def _get_kg_person_summary(self) -> str:
        """Get summary of all persons from Knowledge Graph with their status and timestamps.
        Checks across all temporal snapshots to find departure/joining events."""
        try:
            # Get all person nodes from KG
            persons = self.query_engine.graph.get_nodes_by_type("Person")
            if not persons:
                return ""

            active = []
            departed = []
            joined_recently = []

            # Also check all temporal snapshots for person status changes
            snapshots = self.query_engine.snapshots
            person_history = {}

            if hasattr(snapshots, 'timeline') and snapshots.timeline:
                for ts in snapshots.timeline:
                    try:
                        snapshot = snapshots.get_snapshot(ts)
                        if snapshot:
                            for node_id, node_data in snapshot.items():
                                if 'PERSON_' in node_id or node_data.get('entity_type') == 'Person':
                                    name = node_data.get('name', node_id.replace('PERSON_', '').replace('_', ' ').title())
                                    if name not in person_history:
                                        person_history[name] = {'statuses': [], 'timestamps': [], 'roles': set()}
                                    status = node_data.get('status', '')
                                    if status:
                                        person_history[name]['statuses'].append(status)
                                        person_history[name]['timestamps'].append(ts)
                                    role = node_data.get('role', '')
                                    if role:
                                        person_history[name]['roles'].add(role)
                    except Exception:
                        continue

            for person in persons:
                name = person.get('name', 'Unknown')
                status = person.get('status', '')
                first_seen = person.get('first_seen', '')
                last_seen = person.get('last_seen', '')
                role = person.get('role', '')

                # Check history for departure signals
                history = person_history.get(name, {})
                all_statuses = ' '.join(history.get('statuses', []) + [status]).lower()

                # Categorize by status - check both current and historical statuses
                is_departed = ('final' in all_statuses or 'depart' in all_statuses or
                               'left' in all_statuses or 'last week' in all_statuses or
                               'leaving' in all_statuses or 'resignation' in all_statuses)

                is_new_joiner = ('new' in all_statuses or 'joined' in all_statuses or
                                 'onboard' in all_statuses or 'joining' in all_statuses or
                                 'replacement' in all_statuses or 'hired' in all_statuses)

                if is_departed:
                    departed.append(f"- **{name}** ({role}): {status or 'Departed'}, last seen {last_seen[:10] if last_seen else 'N/A'}")
                elif is_new_joiner or (first_seen and first_seen > '2026-01-15'):  # Joined after mid-January
                    join_date = first_seen[:10] if first_seen else 'N/A'
                    joined_recently.append(f"- **{name}** ({role}): {status or 'New joiner'}, joined {join_date}")
                else:
                    active.append(f"- **{name}** ({role}): {status or 'Active'}")

            summary_parts = []
            if departed:
                summary_parts.append("**Team Members Who Left:**\n" + "\n".join(departed))
            if joined_recently:
                summary_parts.append("**Recently Joined:**\n" + "\n".join(joined_recently))
            if active:
                summary_parts.append("**Current Active Members:**\n" + "\n".join(active))

            return "\n\n".join(summary_parts)
        except Exception as e:
            logger.warning(f"Could not get KG person summary: {e}")
            return ""

    def _get_kg_role_summary(self) -> str:
        """Get roles and responsibilities from Knowledge Graph."""
        try:
            # Get all person nodes with their roles
            persons = self.query_engine.graph.get_nodes_by_type("Person")
            if not persons:
                return ""

            role_data = []
            for person in persons:
                name = person.get('name', 'Unknown')
                role = person.get('role', '')
                responsibilities = person.get('responsibilities', '')
                stream = person.get('stream', '')

                if role or responsibilities:
                    parts = [f"- **{name}**"]
                    if role:
                        parts.append(f"Role: {role}")
                    if stream:
                        parts.append(f"Stream: {stream}")
                    if responsibilities:
                        parts.append(f"Responsibilities: {responsibilities}")
                    role_data.append(" | ".join(parts))

            if role_data:
                return "**Team Roles and Responsibilities:**\n" + "\n".join(role_data)
            return ""
        except Exception as e:
            logger.warning(f"Could not get KG role summary: {e}")
            return ""

    def _get_kg_temporal_summary(self, query: str) -> str:
        """Get temporal data from KG snapshots based on query context.
        Useful for timestamp-based queries when RAG confidence is low."""
        try:
            snapshots = self.query_engine.snapshots
            if not hasattr(snapshots, 'timeline') or not snapshots.timeline:
                return ""

            # Extract month/time hints from query
            query_lower = query.lower()
            relevant_snapshots = []

            for ts in sorted(snapshots.timeline):
                try:
                    month_name = ts.strftime("%B").lower() if hasattr(ts, 'strftime') else ""
                    year = str(ts.year) if hasattr(ts, 'year') else ""

                    # Check if this timestamp matches query context
                    is_relevant = (
                        month_name in query_lower or
                        year in query_lower or
                        'all' in query_lower or
                        'timeline' in query_lower or
                        'history' in query_lower
                    )

                    if is_relevant:
                        snapshot = snapshots.get_snapshot(ts)
                        if snapshot:
                            relevant_snapshots.append((ts, snapshot))
                except Exception:
                    continue

            if not relevant_snapshots:
                # If no specific match, get last 3 snapshots
                for ts in sorted(snapshots.timeline)[-3:]:
                    try:
                        snapshot = snapshots.get_snapshot(ts)
                        if snapshot:
                            relevant_snapshots.append((ts, snapshot))
                    except Exception:
                        continue

            if not relevant_snapshots:
                return ""

            # Build summary from snapshots
            summary_parts = ["**Timeline from Knowledge Graph:**"]
            for ts, snapshot in relevant_snapshots[:5]:  # Limit to 5 snapshots
                ts_str = ts.strftime("%B %d, %Y") if hasattr(ts, 'strftime') else str(ts)
                summary_parts.append(f"\n**{ts_str}:**")

                # Extract key entities from snapshot
                events = []
                for node_id, node_data in list(snapshot.items())[:10]:
                    if isinstance(node_data, dict):
                        name = node_data.get('name', node_id)
                        status = node_data.get('status', '')
                        if status:
                            events.append(f"- {name}: {status}")

                if events:
                    summary_parts.extend(events[:5])

            return "\n".join(summary_parts)
        except Exception as e:
            logger.warning(f"Could not get KG temporal summary: {e}")
            return ""

    def chat(self, user_message: str, allowed_doc_types: List[str] = None) -> ChatResponse:
        """
        Process user message and generate response.

        Strategy: RAG (semantic search) first, fall back to Knowledge Graph if confidence < 0.4

        Args:
            user_message: User's natural language query
            allowed_doc_types: List of document types user can access (for RBAC)

        Returns:
            ChatResponse with answer and metadata
        """
        RAG_CONFIDENCE_THRESHOLD = 0.4

        # Add to context
        self.context.add_message(ChatMessage(
            role="user",
            content=user_message,
            timestamp=datetime.now()
        ))

        # Check if this is a personnel/team query that might need query expansion
        personnel_keywords = ['who left', 'who joined', 'departed', 'resignation', 'new member',
                             'team change', 'left the project', 'joined the project', 'quit', 'hired']
        is_personnel_query = any(kw in user_message.lower() for kw in personnel_keywords)

        # Check if this is a temporal/timestamp query
        temporal_keywords = ['when', 'december', 'january', 'february', 'march', 'april',
                             'last week', 'last month', 'what happened', 'timeline',
                             'history', 'over time', 'changed', 'trend', 'before', 'after',
                             '2025', '2026', 'sprint']
        is_temporal_query = any(kw in user_message.lower() for kw in temporal_keywords)

        # Check if this is a roles/responsibility query - should always consult KG
        role_keywords = ['role', 'responsibility', 'responsibilities', 'who is responsible',
                        'who handles', 'who manages', 'lead', 'owner', 'assigned to',
                        'working on', 'team member', 'developer', 'qa', 'tester']
        is_role_query = any(kw in user_message.lower() for kw in role_keywords)

        try:
            # Step 1: Try RAG (semantic search) first - this is now the default
            if self.rag_engine:
                logger.info("Using RAG (semantic search) as primary source")

                # Expand personnel queries for better RAG results
                query_for_rag = user_message
                if is_personnel_query:
                    query_for_rag = f"{user_message} team member departures resignations new joiners staffing changes"
                    logger.info(f"Expanded personnel query: {query_for_rag}")

                rag_response = self._query_rag(query_for_rag, allowed_doc_types)

                if rag_response and rag_response.confidence >= RAG_CONFIDENCE_THRESHOLD:
                    logger.info(f"RAG confidence {rag_response.confidence:.2f} >= {RAG_CONFIDENCE_THRESHOLD}, using RAG response")

                    # Add data timestamp info to RAG response
                    latest_timestamp = self._get_latest_data_timestamp()
                    date_str = latest_timestamp.strftime("%B %d, %Y")

                    # Append data freshness note to answer if asking about status/latest
                    answer_text = rag_response.answer
                    if any(word in user_message.lower() for word in ['status', 'latest', 'current', 'now', 'today']):
                        answer_text = f"{answer_text}\n\n---\n*Data as of: {date_str}*"

                    # For personnel queries, supplement with KG person data to ensure completeness
                    if is_personnel_query:
                        logger.info(f"Personnel query detected: {user_message}")
                        try:
                            kg_person_summary = self._get_kg_person_summary()
                            if kg_person_summary:
                                logger.info("Supplementing RAG response with KG person data for personnel query")
                                answer_text = f"{answer_text}\n\n**Knowledge Graph Team Summary:**\n{kg_person_summary}"
                        except Exception as e:
                            logger.error(f"Error getting KG person summary: {e}")

                    # For role/responsibility queries, supplement with KG role data
                    if is_role_query:
                        kg_role_summary = self._get_kg_role_summary()
                        if kg_role_summary:
                            logger.info("Supplementing RAG response with KG role data")
                            answer_text = f"{answer_text}\n\n{kg_role_summary}"

                    response = ChatResponse(
                        answer=answer_text,
                        sources=rag_response.sources,
                        data={"rag_used": True, "source": "vector_db", "data_as_of": date_str},
                        follow_up_questions=["What else would you like to know?", "Can you tell me more about this?"],
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
                else:
                    logger.info(f"RAG confidence {rag_response.confidence if rag_response else 0:.2f} < {RAG_CONFIDENCE_THRESHOLD}, falling back to Knowledge Graph")

                    # For temporal queries with low RAG confidence, supplement with KG snapshot data
                    if is_temporal_query and rag_response:
                        kg_temporal = self._get_kg_temporal_summary(user_message)
                        if kg_temporal:
                            logger.info("Supplementing low-confidence RAG response with KG temporal data")
                            answer_text = rag_response.answer
                            answer_text = f"{answer_text}\n\n{kg_temporal}"

                            # For personnel queries, also add person summary
                            if is_personnel_query:
                                kg_person_summary = self._get_kg_person_summary()
                                if kg_person_summary:
                                    answer_text = f"{answer_text}\n\n{kg_person_summary}"

                            # For role queries, also add role summary
                            if is_role_query:
                                kg_role_summary = self._get_kg_role_summary()
                                if kg_role_summary:
                                    answer_text = f"{answer_text}\n\n{kg_role_summary}"

                            response = ChatResponse(
                                answer=answer_text,
                                sources=rag_response.sources,
                                data={"rag_used": True, "kg_supplemented": True, "source": "hybrid"},
                                follow_up_questions=["What else would you like to know?"],
                                confidence=min(0.6, rag_response.confidence + 0.2),  # Boost confidence
                                query_type="hybrid_retrieval"
                            )

                            self.context.add_message(ChatMessage(
                                role="assistant",
                                content=response.answer,
                                timestamp=datetime.now(),
                                metadata={"sources": response.sources}
                            ))
                            return response

            # Step 2: Fall back to Knowledge Graph if RAG confidence is low
            logger.info("Using Knowledge Graph as source")
            plan = self.query_planner.create_plan(user_message)
            logger.debug(f"Query plan: {plan.query_type.value}")

            # Execute query plan
            results = self._execute_plan(plan)

            # Generate response
            response = self._generate_response(user_message, plan, results)
            response.data["source"] = "knowledge_graph"

            # For temporal queries, also add KG snapshot summary
            if is_temporal_query:
                kg_temporal = self._get_kg_temporal_summary(user_message)
                if kg_temporal:
                    response.answer = f"{response.answer}\n\n{kg_temporal}"

            # For personnel queries, also add person summary
            if is_personnel_query:
                kg_person_summary = self._get_kg_person_summary()
                if kg_person_summary:
                    response.answer = f"{response.answer}\n\n{kg_person_summary}"

            # For role queries, also add role summary
            if is_role_query:
                kg_role_summary = self._get_kg_role_summary()
                if kg_role_summary:
                    response.answer = f"{response.answer}\n\n{kg_role_summary}"

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
            # Use actual latest data timestamp instead of hardcoded date
            timestamp = timestamp or self._get_latest_data_timestamp()
            results["data"] = self.query_engine.get_project_state_at(timestamp)
            results["data"]["data_as_of"] = timestamp  # Ensure timestamp is included

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
                # Handle "list all" queries
                if entity.value == "_ALL_":
                    all_entities = self.query_engine.graph.get_nodes_by_type(entity.entity_type)
                    results["data"][f"all_{entity.entity_type.lower()}s"] = all_entities
                else:
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
        """Generate natural language response, using LLM when available"""

        # Try LLM-based response generation first
        if self.llm and self.llm.is_available():
            try:
                answer = self._generate_llm_response(query, plan, results)
                confidence = self._calculate_confidence(results)
                # Boost confidence when using LLM
                confidence = min(0.95, confidence + 0.2)
            except Exception as e:
                logger.warning(f"LLM response generation failed: {e}")
                answer = self._build_answer(plan, results)
                confidence = self._calculate_confidence(results)
        else:
            # Fallback to template-based response
            answer = self._build_answer(plan, results)
            confidence = self._calculate_confidence(results)

        # Extract sources
        sources = self._extract_sources(results)

        # Generate follow-up questions
        follow_ups = self._generate_follow_ups(plan, results)

        return ChatResponse(
            answer=answer,
            sources=sources,
            data=results.get("data", {}),
            follow_up_questions=follow_ups,
            confidence=confidence,
            query_type=plan.query_type.value
        )

    def _generate_llm_response(self, query: str, plan: QueryPlan, results: Dict) -> str:
        """Generate response using LLM"""
        # Format the data as context for the LLM
        data = results.get("data", {})
        metrics = results.get("metrics", {})

        context_parts = []
        context_parts.append(f"Query Type: {plan.query_type.value}")

        if plan.entities:
            entities_str = ", ".join([f"{e.entity_type}:{e.value}" for e in plan.entities])
            context_parts.append(f"Entities: {entities_str}")

        if plan.time_constraints:
            context_parts.append(f"Time Context: {plan.time_constraints}")

        context_parts.append(f"\nData Retrieved:\n{self._format_data_for_llm(data)}")

        if metrics:
            context_parts.append(f"\nMetrics:\n{self._format_data_for_llm(metrics)}")

        context = "\n".join(context_parts)

        system_prompt = """You are a project assistant for the ABC Inc. SAP S/4HANA Migration Project.
Answer questions clearly and concisely based on the knowledge graph data provided.

Guidelines:
- Use the data provided to give accurate answers
- Format responses with markdown for readability
- Include specific dates, names, and numbers when available
- If data is incomplete, acknowledge limitations
- Be helpful and provide actionable insights when possible"""

        return self.llm.generate_response(query, context, system_prompt)

    def _format_data_for_llm(self, data: Any, indent: int = 0) -> str:
        """Format data for LLM context"""
        if data is None:
            return "No data"

        if isinstance(data, dict):
            if not data:
                return "Empty"
            lines = []
            for k, v in list(data.items())[:20]:  # Limit items
                if isinstance(v, (dict, list)) and v:
                    lines.append(f"{'  ' * indent}{k}:")
                    lines.append(self._format_data_for_llm(v, indent + 1))
                else:
                    lines.append(f"{'  ' * indent}{k}: {v}")
            return "\n".join(lines)
        elif isinstance(data, list):
            if not data:
                return "Empty list"
            lines = []
            for item in data[:15]:  # Limit items
                formatted = self._format_data_for_llm(item, indent)
                if '\n' in formatted:
                    lines.append(f"{'  ' * indent}-")
                    lines.append(formatted)
                else:
                    lines.append(f"{'  ' * indent}- {formatted}")
            if len(data) > 15:
                lines.append(f"{'  ' * indent}... and {len(data) - 15} more items")
            return "\n".join(lines)
        else:
            return str(data)

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

        # Format the data timestamp clearly
        data_timestamp = data.get('data_as_of') or data.get('timestamp')
        if isinstance(data_timestamp, datetime):
            date_str = data_timestamp.strftime("%B %d, %Y")
        else:
            date_str = str(data_timestamp) if data_timestamp else "latest available"

        parts.append(f"**Project Status**")
        parts.append(f"*Data as of: {date_str}*")

        # Team
        team = data.get("team", [])
        parts.append(f"\n**Team:** {len(team)} active members")
        if team:
            team_names = [t.get('name', 'Unknown') for t in team[:5]]
            parts.append(f"  Members: {', '.join(team_names)}" + (" ..." if len(team) > 5 else ""))

        # Streams
        streams = data.get("streams", [])
        if streams:
            parts.append("\n**Work Streams:**")
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

        # Add note about data freshness
        parts.append(f"\n---\n*Note: This information reflects the project state as of {date_str}.*")

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
        # Use RAG if data is empty - semantic search may find relevant info
        if not response.data or (isinstance(response.data, dict) and len(response.data) == 0):
            return True
        if "empty" in response.answer.lower() and "data" in response.answer.lower():
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
