"""
Snapshot Manager
Manages temporal snapshots of the knowledge graph.
"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Set
import networkx as nx
import copy


@dataclass
class TemporalGraphSnapshot:
    """
    Represents the knowledge graph state at a specific point in time.
    Includes the graph structure and associated metrics.
    """
    timestamp: datetime
    graph: nx.DiGraph = field(default_factory=nx.DiGraph)
    metrics: Dict[str, float] = field(default_factory=dict)
    label: str = ""

    def node_count(self) -> int:
        """Get number of nodes"""
        return self.graph.number_of_nodes()

    def edge_count(self) -> int:
        """Get number of edges"""
        return self.graph.number_of_edges()

    def get_nodes_by_type(self, entity_type: str) -> List[str]:
        """Get all node IDs of a specific type"""
        return [
            n for n, d in self.graph.nodes(data=True)
            if d.get('entity_type') == entity_type
        ]

    def get_node(self, node_id: str) -> Optional[Dict]:
        """Get node data by ID"""
        if self.graph.has_node(node_id):
            return dict(self.graph.nodes[node_id])
        return None

    def summary(self) -> Dict[str, Any]:
        """Get snapshot summary"""
        entity_types = {}
        for _, data in self.graph.nodes(data=True):
            etype = data.get('entity_type', 'Unknown')
            entity_types[etype] = entity_types.get(etype, 0) + 1

        return {
            "timestamp": self.timestamp,
            "label": self.label,
            "node_count": self.node_count(),
            "edge_count": self.edge_count(),
            "entity_types": entity_types,
            "metrics": self.metrics
        }


class SnapshotManager:
    """
    Manages temporal snapshots of the knowledge graph.
    Enables point-in-time queries and trajectory analysis.
    """

    def __init__(self):
        self.snapshots: Dict[str, TemporalGraphSnapshot] = {}
        self.timeline: List[datetime] = []
        self._sorted = True

    def create_snapshot(self,
                        timestamp: datetime,
                        graph: nx.DiGraph,
                        metrics: Dict[str, float] = None,
                        label: str = "") -> TemporalGraphSnapshot:
        """
        Create a new snapshot at the given timestamp.

        Args:
            timestamp: When this snapshot represents
            graph: The full graph to filter
            metrics: Optional metrics at this time
            label: Optional label (e.g., "Week 5", "Sprint 3")

        Returns:
            The created snapshot
        """
        # Filter graph to only include valid entities at this time
        filtered_graph = self._filter_graph_at_time(graph, timestamp)

        snapshot = TemporalGraphSnapshot(
            timestamp=timestamp,
            graph=filtered_graph,
            metrics=metrics or {},
            label=label
        )

        key = self._timestamp_key(timestamp)
        self.snapshots[key] = snapshot
        self.timeline.append(timestamp)
        self._sorted = False

        return snapshot

    def get_snapshot_at(self, timestamp: datetime) -> Optional[TemporalGraphSnapshot]:
        """
        Get snapshot at or closest before the given timestamp.

        Args:
            timestamp: Time to query

        Returns:
            Matching snapshot or None
        """
        key = self._timestamp_key(timestamp)

        # Exact match
        if key in self.snapshots:
            return self.snapshots[key]

        # Find closest previous
        self._ensure_sorted()
        for ts in reversed(self.timeline):
            if ts <= timestamp:
                return self.snapshots[self._timestamp_key(ts)]

        return None

    def get_snapshots_between(self,
                              start: datetime,
                              end: datetime) -> List[TemporalGraphSnapshot]:
        """
        Get all snapshots in a time range.

        Args:
            start: Start of range
            end: End of range

        Returns:
            List of snapshots in range
        """
        self._ensure_sorted()
        result = []

        for ts in self.timeline:
            if start <= ts <= end:
                result.append(self.snapshots[self._timestamp_key(ts)])

        return result

    def get_entity_trajectory(self,
                              entity_id: str,
                              start: datetime,
                              end: datetime) -> List[Dict]:
        """
        Get an entity's state changes over a time range.

        Args:
            entity_id: Entity to track
            start: Start of range
            end: End of range

        Returns:
            List of state records with timestamps
        """
        trajectory = []
        previous_state = None

        for snapshot in self.get_snapshots_between(start, end):
            if snapshot.graph.has_node(entity_id):
                current_state = dict(snapshot.graph.nodes[entity_id])

                # Only record if state changed
                if current_state != previous_state:
                    trajectory.append({
                        "timestamp": snapshot.timestamp,
                        "label": snapshot.label,
                        "state": current_state
                    })
                    previous_state = current_state

        return trajectory

    def get_new_entities_between(self,
                                 start: datetime,
                                 end: datetime) -> List[Dict]:
        """
        Get entities that appeared in the time range.

        Args:
            start: Start of range
            end: End of range

        Returns:
            List of new entities with their appearance time
        """
        start_snapshot = self.get_snapshot_at(start)
        end_snapshot = self.get_snapshot_at(end)

        if not start_snapshot or not end_snapshot:
            return []

        start_nodes = set(start_snapshot.graph.nodes())
        end_nodes = set(end_snapshot.graph.nodes())

        new_nodes = end_nodes - start_nodes
        result = []

        for node_id in new_nodes:
            node_data = end_snapshot.graph.nodes[node_id]
            result.append({
                "entity_id": node_id,
                "entity_type": node_data.get('entity_type'),
                "first_seen": end_snapshot.timestamp,
                "properties": dict(node_data)
            })

        return result

    def get_departed_entities_between(self,
                                      start: datetime,
                                      end: datetime) -> List[Dict]:
        """
        Get entities that disappeared in the time range.

        Args:
            start: Start of range
            end: End of range

        Returns:
            List of departed entities
        """
        start_snapshot = self.get_snapshot_at(start)
        end_snapshot = self.get_snapshot_at(end)

        if not start_snapshot or not end_snapshot:
            return []

        start_nodes = set(start_snapshot.graph.nodes())
        end_nodes = set(end_snapshot.graph.nodes())

        departed_nodes = start_nodes - end_nodes
        result = []

        for node_id in departed_nodes:
            node_data = start_snapshot.graph.nodes[node_id]
            result.append({
                "entity_id": node_id,
                "entity_type": node_data.get('entity_type'),
                "last_seen": start_snapshot.timestamp,
                "properties": dict(node_data)
            })

        return result

    def compare_snapshots(self,
                          timestamp1: datetime,
                          timestamp2: datetime) -> Dict:
        """
        Compare two snapshots and return differences.

        Args:
            timestamp1: First timestamp
            timestamp2: Second timestamp

        Returns:
            Dict with added, removed, and modified entities
        """
        snap1 = self.get_snapshot_at(timestamp1)
        snap2 = self.get_snapshot_at(timestamp2)

        if not snap1 or not snap2:
            return {"error": "Snapshot not found"}

        nodes1 = set(snap1.graph.nodes())
        nodes2 = set(snap2.graph.nodes())

        added = nodes2 - nodes1
        removed = nodes1 - nodes2
        common = nodes1 & nodes2

        modified = []
        for node_id in common:
            state1 = dict(snap1.graph.nodes[node_id])
            state2 = dict(snap2.graph.nodes[node_id])

            # Find changed properties
            changes = {}
            all_keys = set(state1.keys()) | set(state2.keys())
            for key in all_keys:
                if state1.get(key) != state2.get(key):
                    changes[key] = {
                        "from": state1.get(key),
                        "to": state2.get(key)
                    }

            if changes:
                modified.append({
                    "entity_id": node_id,
                    "changes": changes
                })

        return {
            "timestamp1": timestamp1,
            "timestamp2": timestamp2,
            "added": [{"id": n, "data": dict(snap2.graph.nodes[n])} for n in added],
            "removed": [{"id": n, "data": dict(snap1.graph.nodes[n])} for n in removed],
            "modified": modified,
            "metrics_change": {
                k: snap2.metrics.get(k, 0) - snap1.metrics.get(k, 0)
                for k in set(snap1.metrics.keys()) | set(snap2.metrics.keys())
            }
        }

    def get_metric_series(self, metric_name: str) -> List[Dict]:
        """
        Get time series for a specific metric.

        Args:
            metric_name: Name of the metric

        Returns:
            List of {timestamp, value} records
        """
        self._ensure_sorted()
        series = []

        for ts in self.timeline:
            snapshot = self.snapshots[self._timestamp_key(ts)]
            if metric_name in snapshot.metrics:
                series.append({
                    "timestamp": ts,
                    "value": snapshot.metrics[metric_name],
                    "label": snapshot.label
                })

        return series

    def _filter_graph_at_time(self, graph: nx.DiGraph, timestamp: datetime) -> nx.DiGraph:
        """Filter graph to valid state at timestamp"""
        filtered = nx.DiGraph()

        # Copy nodes that are valid at this time
        for node, attrs in graph.nodes(data=True):
            if self._is_node_valid_at(attrs, timestamp):
                # Get attributes valid at this time
                valid_attrs = self._get_attrs_at(attrs, timestamp)
                filtered.add_node(node, **valid_attrs)

        # Copy edges between valid nodes
        for u, v, attrs in graph.edges(data=True):
            if filtered.has_node(u) and filtered.has_node(v):
                if self._is_edge_valid_at(attrs, timestamp):
                    valid_attrs = self._get_attrs_at(attrs, timestamp)
                    filtered.add_edge(u, v, **valid_attrs)

        return filtered

    def _is_node_valid_at(self, attrs: Dict, timestamp: datetime) -> bool:
        """Check if node is valid at timestamp"""
        # Check created_at
        created = attrs.get('created_at') or attrs.get('first_seen')
        if created and created > timestamp:
            return False

        # Check deleted_at or departed
        deleted = attrs.get('deleted_at') or attrs.get('departure_date')
        if deleted and deleted < timestamp:
            return False

        # Check status for persons
        if attrs.get('entity_type') == 'Person':
            status = attrs.get('status', 'Active')
            if status == 'Departed':
                departure = attrs.get('departure_date')
                if departure and departure < timestamp:
                    return False

        return True

    def _is_edge_valid_at(self, attrs: Dict, timestamp: datetime) -> bool:
        """Check if edge is valid at timestamp"""
        valid_from = attrs.get('valid_from') or attrs.get('start_date')
        valid_to = attrs.get('valid_to') or attrs.get('end_date')

        if valid_from and valid_from > timestamp:
            return False
        if valid_to and valid_to < timestamp:
            return False

        return True

    def _get_attrs_at(self, attrs: Dict, timestamp: datetime) -> Dict:
        """Get attribute values valid at timestamp"""
        # For now, return attrs as-is
        # Future: resolve temporal attribute values
        return dict(attrs)

    def _timestamp_key(self, timestamp: datetime) -> str:
        """Generate key from timestamp"""
        return timestamp.strftime("%Y-%m-%d")

    def _ensure_sorted(self):
        """Ensure timeline is sorted"""
        if not self._sorted:
            self.timeline.sort()
            self._sorted = True

    def summary(self) -> Dict:
        """Get summary of all snapshots"""
        self._ensure_sorted()
        return {
            "snapshot_count": len(self.snapshots),
            "timeline_start": self.timeline[0] if self.timeline else None,
            "timeline_end": self.timeline[-1] if self.timeline else None,
            "snapshots": [
                self.snapshots[self._timestamp_key(ts)].summary()
                for ts in self.timeline
            ]
        }
