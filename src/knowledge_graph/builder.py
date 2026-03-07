"""
Knowledge Graph Builder
Constructs temporal knowledge graph from parsed documents.
"""

from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional
import logging

from ..ingestion.parsers.base_parser import ParsedDocument, ParsedEntity, ParsedRelationship
from .storage.networkx_adapter import NetworkXGraphAdapter
from .storage.snapshot_manager import SnapshotManager
from .schema.temporal_types import TemporalEntity, TemporalProperty

logger = logging.getLogger(__name__)


class KnowledgeGraphBuilder:
    """
    Builds a temporal knowledge graph from parsed documents.
    Maintains entity history and creates temporal snapshots.
    """

    def __init__(self):
        self.graph = NetworkXGraphAdapter()
        self.snapshot_manager = SnapshotManager()
        self.entity_registry: Dict[str, TemporalEntity] = {}
        self.timeline: List[datetime] = []

        # Initialize core entities
        self._initialize_project()

    def _initialize_project(self):
        """Initialize the core project entity"""
        self.graph.add_node(
            "PROJECT_ABC_INC",
            "Project",
            {
                "name": "ABC Inc. SAP S/4HANA Migration",
                "client": "ABC Inc.",
                "vendor": "Accenture",
                "contract_type": "FixedPrice",
                "start_date": datetime(2025, 12, 1),
                "budget": 1850000,
                "status": "Green"
            }
        )

        # Initialize streams
        self.graph.add_node(
            "STREAM_SD",
            "Stream",
            {
                "name": "Sales & Distribution",
                "module": "SD",
                "status": "Green",
                "completion_pct": 0
            }
        )

        self.graph.add_node(
            "STREAM_EWM",
            "Stream",
            {
                "name": "Extended Warehouse Management",
                "module": "EWM",
                "status": "Green",
                "completion_pct": 0
            }
        )

        # Link streams to project
        self.graph.add_edge("PROJECT_ABC_INC", "STREAM_SD", "CONTAINS")
        self.graph.add_edge("PROJECT_ABC_INC", "STREAM_EWM", "CONTAINS")

    def build_from_documents(self, documents: List[ParsedDocument]):
        """
        Build the knowledge graph from a list of parsed documents.

        Args:
            documents: List of parsed documents, should be chronologically sorted
        """
        # Sort by timestamp
        sorted_docs = sorted(documents, key=lambda d: d.timestamp or datetime.min)

        for doc in sorted_docs:
            self._process_document(doc)

            # Create snapshot after each document
            if doc.timestamp:
                self._create_snapshot(doc.timestamp, doc)

        logger.info(f"Built graph with {self.graph.graph.number_of_nodes()} nodes "
                   f"and {self.graph.graph.number_of_edges()} edges")
        logger.info(f"Created {len(self.snapshot_manager.snapshots)} temporal snapshots")

    def _process_document(self, doc: ParsedDocument):
        """Process a single document and update the graph"""
        timestamp = doc.timestamp or datetime.now()

        # Process entities
        for entity in doc.entities:
            self._upsert_entity(entity, timestamp, doc.source_file)

        # Process relationships
        for rel in doc.relationships:
            self._upsert_relationship(rel, timestamp)

        # Process metrics
        if doc.metrics:
            self._store_metrics(doc.metrics, timestamp, doc.source_file)

        # Track timeline
        if timestamp not in self.timeline:
            self.timeline.append(timestamp)
            self.timeline.sort()

    def _upsert_entity(self, entity: ParsedEntity, timestamp: datetime, source: str):
        """Create or update an entity"""
        node_id = entity.entity_id

        if not self.graph.graph.has_node(node_id):
            # Create new entity
            properties = {
                **entity.properties,
                "created_at": timestamp,
                "first_seen": timestamp,
                "source": source
            }

            self.graph.add_node(node_id, entity.entity_type, properties)

            # Create temporal entity for tracking
            self.entity_registry[node_id] = TemporalEntity(
                entity_id=node_id,
                entity_type=entity.entity_type,
                static_properties={"source": source},
                temporal_properties={},
                created_at=timestamp
            )

            # Initialize temporal properties
            for key, value in entity.properties.items():
                if self._is_temporal_property(key):
                    self.entity_registry[node_id].set_property(key, value, timestamp, source)

            logger.debug(f"Created entity {node_id} of type {entity.entity_type}")

        else:
            # Update existing entity
            existing = self.graph.get_node(node_id)

            # Track property changes
            changes = {}
            for key, value in entity.properties.items():
                if existing.get(key) != value:
                    changes[key] = {"from": existing.get(key), "to": value}

                    # Update temporal tracking
                    if node_id in self.entity_registry and self._is_temporal_property(key):
                        self.entity_registry[node_id].set_property(key, value, timestamp, source)

            if changes:
                self.graph.update_node(node_id, entity.properties, timestamp)
                self.graph.update_node(node_id, {"last_seen": timestamp})
                logger.debug(f"Updated entity {node_id}: {list(changes.keys())}")

            else:
                # Just update last_seen
                self.graph.update_node(node_id, {"last_seen": timestamp})

    def _upsert_relationship(self, rel: ParsedRelationship, timestamp: datetime):
        """Create or update a relationship"""
        from_id = rel.from_entity
        to_id = rel.to_entity

        # Ensure both nodes exist
        if not self.graph.graph.has_node(from_id):
            logger.warning(f"Source node {from_id} not found for relationship")
            return

        if not self.graph.graph.has_node(to_id):
            logger.warning(f"Target node {to_id} not found for relationship")
            return

        # Add edge with properties
        properties = {
            **rel.properties,
            "created_at": timestamp
        }

        self.graph.add_edge(from_id, to_id, rel.relation_type, properties)

    def _store_metrics(self, metrics: Dict[str, Any], timestamp: datetime, source: str):
        """Store metrics as metric snapshot entities"""
        for metric_name, value in metrics.items():
            if value is None:
                continue

            metric_id = f"METRIC_{metric_name}_{timestamp.strftime('%Y%m%d')}"

            # Create metric snapshot entity
            self.graph.add_node(
                metric_id,
                "MetricSnapshot",
                {
                    "metric_name": metric_name,
                    "value": value,
                    "timestamp": timestamp,
                    "source": source
                }
            )

    def _create_snapshot(self, timestamp: datetime, doc: ParsedDocument):
        """Create a temporal snapshot"""
        # Collect metrics for this snapshot
        metrics = {}

        # Count entities by type
        stats = self.graph.get_statistics()
        for entity_type, count in stats.get("entity_types", {}).items():
            metrics[f"{entity_type.lower()}_count"] = count

        # Add document-specific metrics
        metrics.update(doc.metrics)

        # Determine label
        label = self._get_snapshot_label(timestamp, doc)

        self.snapshot_manager.create_snapshot(
            timestamp=timestamp,
            graph=self.graph.graph,
            metrics=metrics,
            label=label
        )

    def _get_snapshot_label(self, timestamp: datetime, doc: ParsedDocument) -> str:
        """Generate label for snapshot"""
        if doc.document_type == "ScrumMeeting":
            week = doc.metadata.get("week")
            sprint = doc.metadata.get("sprint")
            if week:
                return f"Week {week}"
            if sprint:
                return f"Sprint {sprint}"

        return timestamp.strftime("%b %d, %Y")

    def _is_temporal_property(self, prop_name: str) -> bool:
        """Check if a property should be tracked temporally"""
        temporal_props = {
            "status", "completion_pct", "probability", "impact",
            "engagement", "velocity", "quality_score", "allocation_pct"
        }
        return prop_name in temporal_props

    # Query Methods

    def get_entity(self, entity_id: str) -> Optional[Dict]:
        """Get current entity state"""
        return self.graph.get_node(entity_id)

    def get_entity_at(self, entity_id: str, timestamp: datetime) -> Optional[Dict]:
        """Get entity state at specific time"""
        if entity_id in self.entity_registry:
            return self.entity_registry[entity_id].get_state_at(timestamp)

        snapshot = self.snapshot_manager.get_snapshot_at(timestamp)
        if snapshot:
            return snapshot.get_node(entity_id)

        return None

    def get_entity_history(self, entity_id: str) -> List[Dict]:
        """Get full history of entity changes"""
        if entity_id not in self.entity_registry:
            return []

        entity = self.entity_registry[entity_id]
        return entity.get_changes_between(
            entity.created_at or datetime.min,
            datetime.max
        )

    def get_related_entities(self,
                             entity_id: str,
                             relation_type: str = None,
                             direction: str = "both") -> List[Dict]:
        """Get entities related to given entity"""
        return self.graph.get_neighbors(entity_id, direction, relation_type)

    def get_entities_by_type(self, entity_type: str) -> List[Dict]:
        """Get all entities of a specific type"""
        return self.graph.get_nodes_by_type(entity_type)

    def get_project_state(self, timestamp: datetime = None) -> Dict:
        """Get overall project state"""
        if timestamp:
            snapshot = self.snapshot_manager.get_snapshot_at(timestamp)
            if not snapshot:
                return {}

            return {
                "timestamp": timestamp,
                "snapshot_label": snapshot.label,
                "team_size": len(snapshot.get_nodes_by_type("Person")),
                "open_risks": len([
                    n for n in snapshot.get_nodes_by_type("Risk")
                    if snapshot.get_node(n).get("status") in ["Open", "Mitigating"]
                ]),
                "metrics": snapshot.metrics
            }

        # Current state
        return {
            "timestamp": datetime.now(),
            "statistics": self.graph.get_statistics(),
            "snapshots": len(self.snapshot_manager.snapshots)
        }

    def export(self) -> Dict:
        """Export graph and snapshots"""
        return {
            "graph": self.graph.to_dict(),
            "snapshot_summary": self.snapshot_manager.summary(),
            "entity_count": self.graph.graph.number_of_nodes(),
            "relationship_count": self.graph.graph.number_of_edges()
        }

    def get_graph(self) -> NetworkXGraphAdapter:
        """Get the underlying graph adapter"""
        return self.graph

    def get_snapshots(self) -> SnapshotManager:
        """Get the snapshot manager"""
        return self.snapshot_manager
