"""
Role Definitions and User Session Management
"""

from dataclasses import dataclass, field
from typing import List, Dict, Set, Optional
from enum import Enum
from datetime import datetime
import hashlib
import secrets


class Permission(Enum):
    """Data access permissions"""
    # Meeting data
    VIEW_SCRUM = "view_scrum"
    VIEW_CLIENT_REVIEWS = "view_client_reviews"
    VIEW_QA_REVIEWS = "view_qa_reviews"
    VIEW_FINANCE_REVIEWS = "view_finance_reviews"
    VIEW_DELIVERY_REVIEWS = "view_delivery_reviews"

    # Entity data
    VIEW_TEAM = "view_team"
    VIEW_RISKS = "view_risks"
    VIEW_DEFECTS = "view_defects"
    VIEW_CHANGE_REQUESTS = "view_change_requests"
    VIEW_TASKS = "view_tasks"

    # Metrics data
    VIEW_QUALITY_METRICS = "view_quality_metrics"
    VIEW_PRODUCTIVITY_METRICS = "view_productivity_metrics"
    VIEW_FINANCIAL_METRICS = "view_financial_metrics"
    VIEW_ENGAGEMENT_METRICS = "view_engagement_metrics"

    # Analysis capabilities
    RUN_PREDICTIONS = "run_predictions"
    RUN_SIMULATIONS = "run_simulations"
    VIEW_FORECASTS = "view_forecasts"

    # Admin
    VIEW_ALL = "view_all"
    ADMIN = "admin"


@dataclass
class Role:
    """User role with permissions"""
    name: str
    display_name: str
    description: str
    permissions: Set[Permission]
    color: str = "#6c757d"  # For UI
    icon: str = "user"  # For UI


# Define standard roles
ROLES: Dict[str, Role] = {
    "qa_director": Role(
        name="qa_director",
        display_name="QA Director",
        description="Quality Assurance Director - Full access to all project data",
        permissions={
            Permission.VIEW_ALL,
            Permission.VIEW_SCRUM,
            Permission.VIEW_CLIENT_REVIEWS,
            Permission.VIEW_QA_REVIEWS,
            Permission.VIEW_FINANCE_REVIEWS,
            Permission.VIEW_DELIVERY_REVIEWS,
            Permission.VIEW_TEAM,
            Permission.VIEW_RISKS,
            Permission.VIEW_DEFECTS,
            Permission.VIEW_CHANGE_REQUESTS,
            Permission.VIEW_TASKS,
            Permission.VIEW_QUALITY_METRICS,
            Permission.VIEW_PRODUCTIVITY_METRICS,
            Permission.VIEW_FINANCIAL_METRICS,
            Permission.VIEW_ENGAGEMENT_METRICS,
            Permission.RUN_PREDICTIONS,
            Permission.RUN_SIMULATIONS,
            Permission.VIEW_FORECASTS,
        },
        color="#28a745",
        icon="shield-check"
    ),

    "delivery_lead": Role(
        name="delivery_lead",
        display_name="Delivery Lead",
        description="Project Delivery Lead - Full access to all project data",
        permissions={
            Permission.VIEW_ALL,
            Permission.VIEW_SCRUM,
            Permission.VIEW_CLIENT_REVIEWS,
            Permission.VIEW_QA_REVIEWS,
            Permission.VIEW_FINANCE_REVIEWS,
            Permission.VIEW_DELIVERY_REVIEWS,
            Permission.VIEW_TEAM,
            Permission.VIEW_RISKS,
            Permission.VIEW_DEFECTS,
            Permission.VIEW_CHANGE_REQUESTS,
            Permission.VIEW_TASKS,
            Permission.VIEW_QUALITY_METRICS,
            Permission.VIEW_PRODUCTIVITY_METRICS,
            Permission.VIEW_FINANCIAL_METRICS,
            Permission.VIEW_ENGAGEMENT_METRICS,
            Permission.RUN_PREDICTIONS,
            Permission.RUN_SIMULATIONS,
            Permission.VIEW_FORECASTS,
        },
        color="#007bff",
        icon="briefcase"
    ),

    "onsite_lead": Role(
        name="onsite_lead",
        display_name="Onsite Coordinator",
        description="Onsite Lead - Access to scrum, quality, productivity, and CRs",
        permissions={
            Permission.VIEW_SCRUM,
            Permission.VIEW_TEAM,
            Permission.VIEW_RISKS,
            Permission.VIEW_DEFECTS,
            Permission.VIEW_CHANGE_REQUESTS,
            Permission.VIEW_TASKS,
            Permission.VIEW_QUALITY_METRICS,
            Permission.VIEW_PRODUCTIVITY_METRICS,
            Permission.RUN_PREDICTIONS,
            Permission.VIEW_FORECASTS,
        },
        color="#17a2b8",
        icon="globe"
    ),

    "auditor": Role(
        name="auditor",
        display_name="Financial Auditor",
        description="Auditor - Access to financial data and reviews",
        permissions={
            Permission.VIEW_FINANCE_REVIEWS,
            Permission.VIEW_FINANCIAL_METRICS,
            Permission.VIEW_CHANGE_REQUESTS,  # CR values
            Permission.VIEW_FORECASTS,
        },
        color="#ffc107",
        icon="calculator"
    ),
}


@dataclass
class User:
    """User account"""
    username: str
    display_name: str
    role_name: str
    password_hash: str
    email: str = ""
    created_at: datetime = field(default_factory=datetime.now)

    @property
    def role(self) -> Role:
        return ROLES.get(self.role_name, ROLES["onsite_lead"])

    def has_permission(self, permission: Permission) -> bool:
        return permission in self.role.permissions or Permission.VIEW_ALL in self.role.permissions

    def verify_password(self, password: str) -> bool:
        return self.password_hash == self._hash_password(password)

    @staticmethod
    def _hash_password(password: str) -> str:
        return hashlib.sha256(password.encode()).hexdigest()

    @classmethod
    def create(cls, username: str, display_name: str, role_name: str, password: str, email: str = ""):
        return cls(
            username=username,
            display_name=display_name,
            role_name=role_name,
            password_hash=cls._hash_password(password),
            email=email
        )


@dataclass
class UserSession:
    """Active user session"""
    session_id: str
    user: User
    created_at: datetime = field(default_factory=datetime.now)
    last_activity: datetime = field(default_factory=datetime.now)

    def update_activity(self):
        self.last_activity = datetime.now()

    def to_dict(self) -> Dict:
        return {
            "session_id": self.session_id,
            "username": self.user.username,
            "display_name": self.user.display_name,
            "role": self.user.role_name,
            "role_display": self.user.role.display_name,
            "permissions": [p.value for p in self.user.role.permissions],
            "color": self.user.role.color,
            "icon": self.user.role.icon
        }


class RoleManager:
    """Manages users and sessions"""

    def __init__(self):
        self.users: Dict[str, User] = {}
        self.sessions: Dict[str, UserSession] = {}
        self._initialize_demo_users()

    def _initialize_demo_users(self):
        """Create demo users for each role"""
        demo_users = [
            ("roshan", "Roshan Arora", "qa_director", "demo123", "roshan@accenture.com"),
            ("krutika", "Krutika Sharma", "delivery_lead", "demo123", "krutika@accenture.com"),
            ("tara", "Tara Minsky", "onsite_lead", "demo123", "tara@accenture.com"),
            ("rick", "Rick Stratford", "auditor", "demo123", "rick@accenture.com"),
        ]

        for username, display_name, role, password, email in demo_users:
            self.users[username] = User.create(username, display_name, role, password, email)

    def authenticate(self, username: str, password: str) -> Optional[UserSession]:
        """Authenticate user and create session"""
        user = self.users.get(username)
        if not user or not user.verify_password(password):
            return None

        # Create session
        session_id = secrets.token_urlsafe(32)
        session = UserSession(session_id=session_id, user=user)
        self.sessions[session_id] = session

        return session

    def get_session(self, session_id: str) -> Optional[UserSession]:
        """Get active session"""
        session = self.sessions.get(session_id)
        if session:
            session.update_activity()
        return session

    def logout(self, session_id: str):
        """End session"""
        if session_id in self.sessions:
            del self.sessions[session_id]

    def get_available_roles(self) -> List[Dict]:
        """Get list of available roles for login UI"""
        return [
            {
                "name": role.name,
                "display_name": role.display_name,
                "description": role.description,
                "color": role.color,
                "icon": role.icon,
                "demo_user": username
            }
            for username, user in self.users.items()
            for role_name, role in ROLES.items()
            if user.role_name == role_name
        ]
