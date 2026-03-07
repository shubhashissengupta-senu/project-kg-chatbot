"""
Access Control and Data Filtering
Filters data based on user permissions.
"""

from typing import Dict, List, Any, Optional, Set
from datetime import datetime

from .roles import Permission, UserSession, Role


class DataFilter:
    """Filters data based on user permissions"""

    # Map entity types to required permissions
    ENTITY_PERMISSIONS = {
        "Meeting": {
            "Scrum": Permission.VIEW_SCRUM,
            "ClientReview": Permission.VIEW_CLIENT_REVIEWS,
            "QAReview": Permission.VIEW_QA_REVIEWS,
            "FinanceReview": Permission.VIEW_FINANCE_REVIEWS,
            "DeliveryReview": Permission.VIEW_DELIVERY_REVIEWS,
        },
        "Person": Permission.VIEW_TEAM,
        "Risk": Permission.VIEW_RISKS,
        "Defect": Permission.VIEW_DEFECTS,
        "ChangeRequest": Permission.VIEW_CHANGE_REQUESTS,
        "Task": Permission.VIEW_TASKS,
        "MetricSnapshot": None,  # Filtered by metric type
    }

    METRIC_PERMISSIONS = {
        "quality": Permission.VIEW_QUALITY_METRICS,
        "productivity": Permission.VIEW_PRODUCTIVITY_METRICS,
        "financial": Permission.VIEW_FINANCIAL_METRICS,
        "engagement": Permission.VIEW_ENGAGEMENT_METRICS,
        "velocity": Permission.VIEW_PRODUCTIVITY_METRICS,
        "test": Permission.VIEW_QUALITY_METRICS,
        "defect": Permission.VIEW_QUALITY_METRICS,
        "budget": Permission.VIEW_FINANCIAL_METRICS,
        "cost": Permission.VIEW_FINANCIAL_METRICS,
        "margin": Permission.VIEW_FINANCIAL_METRICS,
        "cpi": Permission.VIEW_FINANCIAL_METRICS,
        "revenue": Permission.VIEW_FINANCIAL_METRICS,
    }

    def __init__(self, session: UserSession):
        self.session = session
        self.permissions = session.user.role.permissions

    def has_permission(self, permission: Permission) -> bool:
        """Check if user has specific permission"""
        return Permission.VIEW_ALL in self.permissions or permission in self.permissions

    def can_view_entity(self, entity_type: str, entity_data: Dict = None) -> bool:
        """Check if user can view this entity type"""
        if Permission.VIEW_ALL in self.permissions:
            return True

        perm = self.ENTITY_PERMISSIONS.get(entity_type)

        if perm is None:
            return True  # No restriction

        if isinstance(perm, dict):
            # Sub-type based permission (e.g., Meeting types)
            if entity_data:
                sub_type = entity_data.get("meeting_type") or entity_data.get("type")
                if sub_type and sub_type in perm:
                    return perm[sub_type] in self.permissions
            # Check if any of the sub-permissions are granted
            return any(p in self.permissions for p in perm.values())

        return perm in self.permissions

    def can_view_metric(self, metric_name: str) -> bool:
        """Check if user can view this metric"""
        if Permission.VIEW_ALL in self.permissions:
            return True

        metric_lower = metric_name.lower()

        for keyword, perm in self.METRIC_PERMISSIONS.items():
            if keyword in metric_lower:
                return perm in self.permissions

        # Default allow if no specific restriction
        return True

    def filter_entities(self, entities: List[Dict]) -> List[Dict]:
        """Filter list of entities based on permissions"""
        return [
            e for e in entities
            if self.can_view_entity(e.get("entity_type", ""), e)
        ]

    def filter_metrics(self, metrics: Dict[str, Any]) -> Dict[str, Any]:
        """Filter metrics based on permissions"""
        return {
            k: v for k, v in metrics.items()
            if self.can_view_metric(k)
        }

    def filter_project_state(self, state: Dict) -> Dict:
        """Filter complete project state based on permissions"""
        filtered = {}

        # Always include timestamp and basic info
        if "timestamp" in state:
            filtered["timestamp"] = state["timestamp"]
        if "snapshot_label" in state:
            filtered["snapshot_label"] = state["snapshot_label"]

        # Filter team data
        if "team" in state and self.has_permission(Permission.VIEW_TEAM):
            filtered["team"] = state["team"]

        # Filter streams (always visible for context)
        if "streams" in state:
            filtered["streams"] = state["streams"]

        # Filter risks
        if "open_risks" in state and self.has_permission(Permission.VIEW_RISKS):
            filtered["open_risks"] = state["open_risks"]

        # Filter defects
        if "open_defects" in state and self.has_permission(Permission.VIEW_DEFECTS):
            filtered["open_defects"] = state["open_defects"]

        # Filter change requests
        if "change_requests" in state and self.has_permission(Permission.VIEW_CHANGE_REQUESTS):
            # For auditors, include CR values
            if self.has_permission(Permission.VIEW_FINANCIAL_METRICS):
                filtered["change_requests"] = state["change_requests"]
            else:
                # Remove financial details
                filtered["change_requests"] = [
                    {k: v for k, v in cr.items() if k not in ["value", "margin", "cost"]}
                    for cr in state["change_requests"]
                ]

        # Filter metrics
        if "metrics" in state:
            filtered["metrics"] = self.filter_metrics(state["metrics"])

        # Filter entity counts
        if "entity_counts" in state:
            filtered["entity_counts"] = {
                k: v for k, v in state["entity_counts"].items()
                if self.can_view_entity(k)
            }

        return filtered


class AccessController:
    """
    Controls access to system resources based on user roles.
    """

    def __init__(self):
        pass

    def create_filter(self, session: UserSession) -> DataFilter:
        """Create a data filter for the user session"""
        return DataFilter(session)

    def check_query_permission(self, session: UserSession, query_type: str, query_params: Dict) -> bool:
        """Check if user can execute this type of query"""
        permissions = session.user.role.permissions

        if Permission.VIEW_ALL in permissions:
            return True

        # Check predictions/simulations
        if query_type == "predictive":
            return Permission.RUN_PREDICTIONS in permissions

        if query_type == "simulation":
            return Permission.RUN_SIMULATIONS in permissions

        # Check entity-specific queries
        if "entity_type" in query_params:
            entity_type = query_params["entity_type"]
            filter = DataFilter(session)
            return filter.can_view_entity(entity_type)

        return True

    def get_restricted_message(self, session: UserSession) -> str:
        """Get message explaining what data the user can access"""
        role = session.user.role

        messages = {
            "qa_director": "You have full access to all project data.",
            "delivery_lead": "You have full access to all project data.",
            "onsite_lead": "You can access scrum reports, quality metrics, productivity data, and change requests.",
            "auditor": "You can access financial data and reviews."
        }

        return messages.get(role.name, "Limited access based on your role.")

    def get_allowed_document_types(self, session: UserSession) -> List[str]:
        """Get list of document types the user can access"""
        permissions = session.user.role.permissions

        if Permission.VIEW_ALL in permissions:
            return ["Scrum", "ClientReview", "QAReview", "FinanceReview", "DeliveryReview", "DeveloperMetrics", "General"]

        allowed = ["General"]  # General documents always accessible

        if Permission.VIEW_SCRUM in permissions:
            allowed.append("Scrum")
        if Permission.VIEW_CLIENT_REVIEWS in permissions:
            allowed.append("ClientReview")
        if Permission.VIEW_QA_REVIEWS in permissions:
            allowed.append("QAReview")
        if Permission.VIEW_FINANCE_REVIEWS in permissions:
            allowed.append("FinanceReview")
        if Permission.VIEW_DELIVERY_REVIEWS in permissions:
            allowed.append("DeliveryReview")
        if Permission.VIEW_PRODUCTIVITY_METRICS in permissions:
            allowed.append("DeveloperMetrics")

        return allowed

    def filter_rag_chunks(self, session: UserSession, chunks: List[Any]) -> List[Any]:
        """Filter RAG chunks based on user document access permissions"""
        allowed_types = self.get_allowed_document_types(session)

        return [
            chunk for chunk in chunks
            if chunk.chunk.metadata.get('document_type', 'General') in allowed_types
        ]
