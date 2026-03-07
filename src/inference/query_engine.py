"""
Temporal Query Engine
Query processing for the temporal knowledge graph.
"""

from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional, Tuple
import networkx as nx

from ..knowledge_graph.storage.snapshot_manager import SnapshotManager
from ..knowledge_graph.storage.networkx_adapter import NetworkXGraphAdapter
from ..time_series.metrics_store import TimeSeriesMetricsStore


class TemporalQueryEngine:
    """
    Query engine for temporal knowledge graph.
    Supports point-in-time queries, trajectories, and temporal analysis.
    """

    def __init__(self,
                 graph: NetworkXGraphAdapter,
                 snapshot_manager: SnapshotManager,
                 metrics_store: TimeSeriesMetricsStore):
        self.graph = graph
        self.snapshots = snapshot_manager
        self.metrics = metrics_store

    # =========================================================================
    # Point-in-Time Queries
    # =========================================================================

    def get_project_state_at(self, timestamp: datetime) -> Dict:
        """
        Get complete project state at a specific time.

        Args:
            timestamp: Time to query

        Returns:
            Project state dict
        """
        snapshot = self.snapshots.get_snapshot_at(timestamp)
        if not snapshot:
            return {"error": "No snapshot available for this time"}

        g = snapshot.graph

        return {
            "timestamp": timestamp,
            "snapshot_label": snapshot.label,
            "team": self._get_active_team(g),
            "streams": self._get_stream_states(g),
            "open_risks": self._get_open_risks(g),
            "open_defects": self._get_open_defects(g),
            "change_requests": self._get_change_requests(g),
            "metrics": snapshot.metrics,
            "entity_counts": snapshot.summary().get("entity_types", {})
        }

    def get_entity_state_at(self,
                            entity_id: str,
                            timestamp: datetime) -> Optional[Dict]:
        """
        Get entity state at specific time.

        Args:
            entity_id: Entity to query
            timestamp: Time to query

        Returns:
            Entity state or None
        """
        snapshot = self.snapshots.get_snapshot_at(timestamp)
        if not snapshot:
            return None

        node = snapshot.get_node(entity_id)
        if not node:
            return None

        # Add metrics if available
        metrics = self.metrics.get_entity_metrics_at(entity_id, timestamp)
        if metrics:
            node["metrics"] = metrics

        return node

    # =========================================================================
    # Time Range Queries
    # =========================================================================

    def get_changes_between(self,
                            start: datetime,
                            end: datetime,
                            entity_type: str = None) -> Dict:
        """
        Get all changes between two timestamps.

        Args:
            start: Start of range
            end: End of range
            entity_type: Optional filter by entity type

        Returns:
            Dict with added, removed, modified entities
        """
        comparison = self.snapshots.compare_snapshots(start, end)

        if entity_type:
            # Filter by entity type
            comparison["added"] = [
                e for e in comparison.get("added", [])
                if e.get("data", {}).get("entity_type") == entity_type
            ]
            comparison["removed"] = [
                e for e in comparison.get("removed", [])
                if e.get("data", {}).get("entity_type") == entity_type
            ]

        return comparison

    def get_entity_trajectory(self,
                              entity_id: str,
                              start: datetime = None,
                              end: datetime = None) -> List[Dict]:
        """
        Get entity state changes over time.

        Args:
            entity_id: Entity to track
            start: Start of range (defaults to beginning)
            end: End of range (defaults to now)

        Returns:
            List of state changes with timestamps
        """
        start = start or datetime(2025, 12, 1)
        end = end or datetime.now()

        return self.snapshots.get_entity_trajectory(entity_id, start, end)

    def get_timeline(self,
                     start: datetime,
                     end: datetime,
                     event_types: List[str] = None) -> List[Dict]:
        """
        Get timeline of events in a range.

        Args:
            start: Start of range
            end: End of range
            event_types: Optional filter by event type

        Returns:
            Chronological list of events
        """
        events = []

        # Get events from graph
        event_nodes = self.graph.get_nodes_by_type("Event")
        for event in event_nodes:
            event_date = event.get("date") or event.get("timestamp")
            if event_date and start <= event_date <= end:
                if event_types is None or event.get("event_type") in event_types:
                    events.append({
                        "timestamp": event_date,
                        "type": event.get("event_type"),
                        "description": event.get("description"),
                        "impact": event.get("impact"),
                        "entity_id": event.get("id")
                    })

        # Get meetings
        meetings = self.graph.get_nodes_by_type("Meeting")
        for meeting in meetings:
            meeting_date = meeting.get("date")
            if meeting_date and start <= meeting_date <= end:
                events.append({
                    "timestamp": meeting_date,
                    "type": f"Meeting_{meeting.get('meeting_type', 'General')}",
                    "description": f"{meeting.get('meeting_type')} meeting",
                    "impact": "Low",
                    "entity_id": meeting.get("id")
                })

        # Sort chronologically
        events.sort(key=lambda e: e["timestamp"])

        return events

    # =========================================================================
    # Relationship Queries
    # =========================================================================

    def get_related_entities(self,
                             entity_id: str,
                             relation_type: str = None,
                             timestamp: datetime = None) -> List[Dict]:
        """
        Get entities related to given entity.

        Args:
            entity_id: Source entity
            relation_type: Optional filter by relation
            timestamp: Optional point-in-time filter

        Returns:
            List of related entities
        """
        if timestamp:
            snapshot = self.snapshots.get_snapshot_at(timestamp)
            if not snapshot:
                return []
            g = snapshot.graph
        else:
            g = self.graph.graph

        if not g.has_node(entity_id):
            return []

        related = []

        # Outgoing edges
        for _, target, data in g.out_edges(entity_id, data=True):
            if relation_type is None or data.get('relation') == relation_type:
                related.append({
                    "entity_id": target,
                    "relation": data.get('relation'),
                    "direction": "outgoing",
                    "entity_data": dict(g.nodes[target]) if g.has_node(target) else {}
                })

        # Incoming edges
        for source, _, data in g.in_edges(entity_id, data=True):
            if relation_type is None or data.get('relation') == relation_type:
                related.append({
                    "entity_id": source,
                    "relation": data.get('relation'),
                    "direction": "incoming",
                    "entity_data": dict(g.nodes[source]) if g.has_node(source) else {}
                })

        return related

    def find_path(self,
                  from_entity: str,
                  to_entity: str,
                  max_depth: int = 5) -> Optional[List[Dict]]:
        """
        Find path between two entities.

        Args:
            from_entity: Start entity
            to_entity: End entity
            max_depth: Maximum path length

        Returns:
            List of entities in path or None
        """
        path = self.graph.find_path(from_entity, to_entity, max_depth)

        if not path:
            return None

        result = []
        for i, node_id in enumerate(path):
            node_data = self.graph.get_node(node_id)
            entry = {
                "position": i,
                "entity_id": node_id,
                "entity_type": node_data.get("entity_type") if node_data else None,
            }

            # Add edge info
            if i > 0:
                edge = self.graph.get_edge(path[i-1], node_id)
                entry["via_relation"] = edge.get("relation") if edge else None

            result.append(entry)

        return result

    # =========================================================================
    # Impact Analysis
    # =========================================================================

    def find_impact_chain(self,
                          event_entity_id: str,
                          max_depth: int = 3) -> Dict:
        """
        Find entities impacted by an event or change.

        Args:
            event_entity_id: Source event/change entity
            max_depth: Maximum chain depth

        Returns:
            Dict of impacted entities with paths
        """
        impacted = {}
        visited = set()

        def traverse(node_id: str, depth: int, path: List[Tuple]):
            if depth > max_depth or node_id in visited:
                return
            visited.add(node_id)

            for _, target, data in self.graph.graph.out_edges(node_id, data=True):
                relation = data.get('relation', 'UNKNOWN')

                if target not in impacted:
                    impacted[target] = {
                        "entity_data": self.graph.get_node(target),
                        "impact_path": path + [(node_id, relation, target)],
                        "depth": depth
                    }

                traverse(target, depth + 1, path + [(node_id, relation, target)])

        traverse(event_entity_id, 1, [])
        return impacted

    def analyze_event_impact(self,
                             event_entity_id: str,
                             metric_names: List[str] = None,
                             window_days: int = 7) -> Dict:
        """
        Analyze impact of an event on metrics.

        Args:
            event_entity_id: Event to analyze
            metric_names: Metrics to check (defaults to key metrics)
            window_days: Days before/after to compare

        Returns:
            Impact analysis results
        """
        event = self.graph.get_node(event_entity_id)
        if not event:
            return {"error": "Event not found"}

        event_date = event.get("date") or event.get("timestamp")
        if not event_date:
            return {"error": "Event has no date"}

        metric_names = metric_names or [
            "team_velocity", "quality_score", "engagement_score", "defect_density"
        ]

        before_start = event_date - timedelta(days=window_days)
        before_end = event_date - timedelta(days=1)
        after_start = event_date + timedelta(days=1)
        after_end = event_date + timedelta(days=window_days)

        impacts = {}
        for metric in metric_names:
            comparison = self.metrics.compare_periods(
                metric,
                (before_start, before_end),
                (after_start, after_end)
            )
            if comparison and "comparison" in comparison:
                impacts[metric] = comparison["comparison"]

        return {
            "event": event,
            "event_date": event_date,
            "window_days": window_days,
            "metric_impacts": impacts,
            "affected_entities": list(self.find_impact_chain(event_entity_id).keys())
        }

    # =========================================================================
    # Aggregation Queries
    # =========================================================================

    def count_entities(self,
                       entity_type: str,
                       timestamp: datetime = None,
                       filters: Dict = None) -> int:
        """
        Count entities of a type.

        Args:
            entity_type: Type to count
            timestamp: Optional point-in-time
            filters: Optional property filters

        Returns:
            Count
        """
        if timestamp:
            snapshot = self.snapshots.get_snapshot_at(timestamp)
            if not snapshot:
                return 0
            entities = snapshot.get_nodes_by_type(entity_type)
        else:
            entities = [e["id"] for e in self.graph.get_nodes_by_type(entity_type)]

        if filters:
            # Apply filters
            if timestamp:
                g = snapshot.graph
            else:
                g = self.graph.graph

            filtered = []
            for eid in entities:
                if g.has_node(eid):
                    node = dict(g.nodes[eid])
                    match = all(node.get(k) == v for k, v in filters.items())
                    if match:
                        filtered.append(eid)
            return len(filtered)

        return len(entities)

    def aggregate_metric(self,
                         metric_name: str,
                         aggregation: str = "mean",
                         start: datetime = None,
                         end: datetime = None) -> Optional[float]:
        """
        Aggregate a metric over time.

        Args:
            metric_name: Metric to aggregate
            aggregation: Type (mean, sum, min, max)
            start: Start of range
            end: End of range

        Returns:
            Aggregated value
        """
        series = self.metrics.get_series(metric_name)
        if not series:
            return None

        stats = series.get_statistics(start, end)

        if aggregation == "mean":
            return stats.get("mean")
        elif aggregation == "sum":
            return stats.get("mean", 0) * stats.get("count", 0)
        elif aggregation == "min":
            return stats.get("min")
        elif aggregation == "max":
            return stats.get("max")

        return None

    # =========================================================================
    # Helper Methods
    # =========================================================================

    def _get_active_team(self, graph: nx.DiGraph) -> List[Dict]:
        """Get active team members"""
        team = []
        for n, d in graph.nodes(data=True):
            if d.get('entity_type') == 'Person':
                status = d.get('status', 'Unknown')
                if status in ['Active', 'Present']:
                    team.append({
                        "id": n,
                        "name": d.get("name"),
                        "role": d.get("role"),
                        "stream": d.get("stream")
                    })
        return team

    def _get_stream_states(self, graph: nx.DiGraph) -> List[Dict]:
        """Get stream states"""
        streams = []
        for n, d in graph.nodes(data=True):
            if d.get('entity_type') == 'Stream':
                streams.append({
                    "id": n,
                    "name": d.get("name"),
                    "status": d.get("status"),
                    "completion_pct": d.get("completion_pct")
                })
        return streams

    def _get_open_risks(self, graph: nx.DiGraph) -> List[Dict]:
        """Get open risks"""
        risks = []
        for n, d in graph.nodes(data=True):
            if d.get('entity_type') == 'Risk':
                status = d.get('status', 'Unknown')
                if status in ['Open', 'Mitigating']:
                    risks.append({
                        "id": n,
                        "description": d.get("description"),
                        "probability": d.get("probability"),
                        "impact": d.get("impact"),
                        "status": status
                    })
        return risks

    def _get_open_defects(self, graph: nx.DiGraph) -> List[Dict]:
        """Get open defects"""
        defects = []
        for n, d in graph.nodes(data=True):
            if d.get('entity_type') == 'Defect':
                status = d.get('status', 'Unknown')
                if status not in ['Closed', 'Resolved']:
                    defects.append({
                        "id": n,
                        "description": d.get("description"),
                        "severity": d.get("severity"),
                        "status": status
                    })
        return defects

    def _get_change_requests(self, graph: nx.DiGraph) -> List[Dict]:
        """Get change requests"""
        crs = []
        for n, d in graph.nodes(data=True):
            if d.get('entity_type') == 'ChangeRequest':
                crs.append({
                    "id": n,
                    "description": d.get("description"),
                    "value": d.get("value"),
                    "status": d.get("status")
                })
        return crs
