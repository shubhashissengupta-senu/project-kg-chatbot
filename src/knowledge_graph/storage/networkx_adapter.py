"""
NetworkX Graph Adapter
In-memory graph storage using NetworkX.
"""

from typing import Dict, List, Optional, Any, Tuple
from datetime import datetime
import networkx as nx
import json


class NetworkXGraphAdapter:
    """
    Adapter for NetworkX-based graph storage.
    Provides a consistent interface for graph operations.
    """

    def __init__(self):
        self.graph = nx.DiGraph()
        self._node_index: Dict[str, Dict[str, List[str]]] = {}  # type -> property -> [node_ids]

    def add_node(self,
                 node_id: str,
                 entity_type: str,
                 properties: Dict[str, Any] = None,
                 temporal_properties: Dict[str, Any] = None) -> str:
        """
        Add a node to the graph.

        Args:
            node_id: Unique identifier
            entity_type: Type of entity
            properties: Static properties
            temporal_properties: Time-varying properties

        Returns:
            Node ID
        """
        attrs = {
            "entity_type": entity_type,
            **(properties or {}),
            **(temporal_properties or {})
        }

        self.graph.add_node(node_id, **attrs)
        self._update_index(node_id, entity_type, attrs)

        return node_id

    def update_node(self,
                    node_id: str,
                    properties: Dict[str, Any],
                    timestamp: datetime = None):
        """
        Update node properties.

        Args:
            node_id: Node to update
            properties: Properties to set/update
            timestamp: Optional timestamp for temporal tracking
        """
        if not self.graph.has_node(node_id):
            raise ValueError(f"Node {node_id} not found")

        # Update properties
        for key, value in properties.items():
            self.graph.nodes[node_id][key] = value

        # Track modification time
        if timestamp:
            self.graph.nodes[node_id]['last_modified'] = timestamp

    def get_node(self, node_id: str) -> Optional[Dict]:
        """Get node by ID"""
        if self.graph.has_node(node_id):
            return dict(self.graph.nodes[node_id])
        return None

    def remove_node(self, node_id: str):
        """Remove a node and its edges"""
        if self.graph.has_node(node_id):
            self.graph.remove_node(node_id)

    def add_edge(self,
                 from_id: str,
                 to_id: str,
                 relation_type: str,
                 properties: Dict[str, Any] = None) -> Tuple[str, str]:
        """
        Add an edge between nodes.

        Args:
            from_id: Source node
            to_id: Target node
            relation_type: Type of relationship
            properties: Edge properties

        Returns:
            Tuple of (from_id, to_id)
        """
        attrs = {
            "relation": relation_type,
            **(properties or {})
        }

        self.graph.add_edge(from_id, to_id, **attrs)
        return (from_id, to_id)

    def get_edge(self, from_id: str, to_id: str) -> Optional[Dict]:
        """Get edge between two nodes"""
        if self.graph.has_edge(from_id, to_id):
            return dict(self.graph.edges[from_id, to_id])
        return None

    def remove_edge(self, from_id: str, to_id: str):
        """Remove an edge"""
        if self.graph.has_edge(from_id, to_id):
            self.graph.remove_edge(from_id, to_id)

    # Query Methods

    def get_nodes_by_type(self, entity_type: str) -> List[Dict]:
        """Get all nodes of a specific type"""
        return [
            {"id": n, **dict(d)}
            for n, d in self.graph.nodes(data=True)
            if d.get('entity_type') == entity_type
        ]

    def get_nodes_by_property(self,
                              property_name: str,
                              property_value: Any) -> List[Dict]:
        """Get nodes with a specific property value"""
        return [
            {"id": n, **dict(d)}
            for n, d in self.graph.nodes(data=True)
            if d.get(property_name) == property_value
        ]

    def get_neighbors(self,
                      node_id: str,
                      direction: str = "both",
                      relation_type: str = None) -> List[Dict]:
        """
        Get neighboring nodes.

        Args:
            node_id: Source node
            direction: "in", "out", or "both"
            relation_type: Optional filter by relation type

        Returns:
            List of neighbor dicts
        """
        if not self.graph.has_node(node_id):
            return []

        neighbors = []

        # Outgoing edges
        if direction in ["out", "both"]:
            for _, target, data in self.graph.out_edges(node_id, data=True):
                if relation_type is None or data.get('relation') == relation_type:
                    neighbors.append({
                        "id": target,
                        "direction": "outgoing",
                        "relation": data.get('relation'),
                        "edge_data": dict(data),
                        "node_data": dict(self.graph.nodes[target])
                    })

        # Incoming edges
        if direction in ["in", "both"]:
            for source, _, data in self.graph.in_edges(node_id, data=True):
                if relation_type is None or data.get('relation') == relation_type:
                    neighbors.append({
                        "id": source,
                        "direction": "incoming",
                        "relation": data.get('relation'),
                        "edge_data": dict(data),
                        "node_data": dict(self.graph.nodes[source])
                    })

        return neighbors

    def find_path(self,
                  from_id: str,
                  to_id: str,
                  max_depth: int = 5) -> Optional[List[str]]:
        """
        Find shortest path between two nodes.

        Args:
            from_id: Start node
            to_id: End node
            max_depth: Maximum path length

        Returns:
            List of node IDs in path, or None
        """
        try:
            path = nx.shortest_path(self.graph, from_id, to_id)
            if len(path) <= max_depth + 1:
                return path
            return None
        except nx.NetworkXNoPath:
            return None

    def get_subgraph(self,
                     node_ids: List[str],
                     include_edges: bool = True) -> 'NetworkXGraphAdapter':
        """
        Get subgraph containing specified nodes.

        Args:
            node_ids: Nodes to include
            include_edges: Whether to include edges between nodes

        Returns:
            New adapter with subgraph
        """
        subgraph = NetworkXGraphAdapter()

        for node_id in node_ids:
            if self.graph.has_node(node_id):
                data = dict(self.graph.nodes[node_id])
                subgraph.add_node(
                    node_id,
                    data.pop('entity_type', 'Unknown'),
                    data
                )

        if include_edges:
            for u, v, data in self.graph.edges(data=True):
                if u in node_ids and v in node_ids:
                    subgraph.add_edge(u, v, data.get('relation', 'RELATED'), dict(data))

        return subgraph

    # Analysis Methods

    def get_statistics(self) -> Dict:
        """Get graph statistics"""
        entity_counts = {}
        for _, data in self.graph.nodes(data=True):
            etype = data.get('entity_type', 'Unknown')
            entity_counts[etype] = entity_counts.get(etype, 0) + 1

        relation_counts = {}
        for _, _, data in self.graph.edges(data=True):
            rtype = data.get('relation', 'Unknown')
            relation_counts[rtype] = relation_counts.get(rtype, 0) + 1

        return {
            "node_count": self.graph.number_of_nodes(),
            "edge_count": self.graph.number_of_edges(),
            "entity_types": entity_counts,
            "relation_types": relation_counts,
            "density": nx.density(self.graph),
            "is_connected": nx.is_weakly_connected(self.graph) if self.graph.number_of_nodes() > 0 else True
        }

    def get_central_nodes(self, top_k: int = 10) -> List[Dict]:
        """Get most central nodes by degree"""
        if self.graph.number_of_nodes() == 0:
            return []

        centrality = nx.degree_centrality(self.graph)
        sorted_nodes = sorted(centrality.items(), key=lambda x: x[1], reverse=True)[:top_k]

        return [
            {
                "id": node_id,
                "centrality": score,
                "data": dict(self.graph.nodes[node_id])
            }
            for node_id, score in sorted_nodes
        ]

    # Persistence Methods

    def to_dict(self) -> Dict:
        """Export graph to dict"""
        return {
            "nodes": [
                {"id": n, **dict(d)}
                for n, d in self.graph.nodes(data=True)
            ],
            "edges": [
                {"from": u, "to": v, **dict(d)}
                for u, v, d in self.graph.edges(data=True)
            ]
        }

    def from_dict(self, data: Dict):
        """Import graph from dict"""
        self.graph.clear()
        self._node_index.clear()

        for node in data.get("nodes", []):
            node_id = node.pop("id")
            entity_type = node.pop("entity_type", "Unknown")
            self.add_node(node_id, entity_type, node)

        for edge in data.get("edges", []):
            from_id = edge.pop("from")
            to_id = edge.pop("to")
            relation = edge.pop("relation", "RELATED")
            self.add_edge(from_id, to_id, relation, edge)

    def save_json(self, filepath: str):
        """Save graph to JSON file"""
        with open(filepath, 'w') as f:
            json.dump(self.to_dict(), f, indent=2, default=str)

    def load_json(self, filepath: str):
        """Load graph from JSON file"""
        with open(filepath, 'r') as f:
            data = json.load(f)
            self.from_dict(data)

    # Helper Methods

    def _update_index(self, node_id: str, entity_type: str, attrs: Dict):
        """Update node index"""
        if entity_type not in self._node_index:
            self._node_index[entity_type] = {}

        for key, value in attrs.items():
            if isinstance(value, (str, int, float, bool)):
                if key not in self._node_index[entity_type]:
                    self._node_index[entity_type][key] = {}

                str_value = str(value)
                if str_value not in self._node_index[entity_type][key]:
                    self._node_index[entity_type][key][str_value] = []

                self._node_index[entity_type][key][str_value].append(node_id)
