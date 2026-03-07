"""
FastAPI Routes
Main API endpoints for the application.
"""

from fastapi import APIRouter, HTTPException, Depends, Request, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from typing import Dict, List, Optional, Any
from datetime import datetime
import logging

logger = logging.getLogger(__name__)

# Create routers for different endpoint groups
auth_router = APIRouter(prefix="/api/auth", tags=["Authentication"])
chat_router = APIRouter(prefix="/api/chat", tags=["Chat"])
graph_router = APIRouter(prefix="/api/graph", tags=["Knowledge Graph"])
metrics_router = APIRouter(prefix="/api/metrics", tags=["Metrics"])
simulation_router = APIRouter(prefix="/api/simulation", tags=["Simulation"])


# ============================================================================
# Request/Response Models
# ============================================================================

class LoginRequest(BaseModel):
    username: str
    password: str


class LoginResponse(BaseModel):
    success: bool
    session_id: Optional[str]
    user: Optional[Dict]
    message: str


class ChatRequest(BaseModel):
    message: str
    session_id: str


class ChatResponse(BaseModel):
    answer: str
    query_type: str
    data: Dict
    sources: List[Dict]
    follow_up_questions: List[str]
    confidence: float


class SimulationRequest(BaseModel):
    scenario_id: str
    parameters: Dict[str, Any]


class ForecastRequest(BaseModel):
    metric_name: Optional[str]
    horizon_days: int = 30
    reference_date: Optional[str]


# ============================================================================
# Dependency: Get Application State
# ============================================================================

def get_app_state(request: Request):
    """Get application state from request"""
    return request.app.state


def get_session(request: Request, session_id: str = None):
    """Get user session from request"""
    state = get_app_state(request)
    if not session_id:
        session_id = request.cookies.get("session_id")
    if not session_id:
        return None
    return state.role_manager.get_session(session_id)


# ============================================================================
# Authentication Endpoints
# ============================================================================

@auth_router.post("/login", response_model=LoginResponse)
async def login(request: Request, login_data: LoginRequest):
    """Authenticate user and create session"""
    state = get_app_state(request)

    session = state.role_manager.authenticate(
        login_data.username,
        login_data.password
    )

    if not session:
        return LoginResponse(
            success=False,
            session_id=None,
            user=None,
            message="Invalid username or password"
        )

    return LoginResponse(
        success=True,
        session_id=session.session_id,
        user=session.to_dict(),
        message="Login successful"
    )


@auth_router.post("/logout")
async def logout(request: Request, session_id: str):
    """End user session"""
    state = get_app_state(request)
    state.role_manager.logout(session_id)
    return {"success": True, "message": "Logged out"}


@auth_router.get("/session/{session_id}")
async def get_session_info(request: Request, session_id: str):
    """Get session information"""
    state = get_app_state(request)
    session = state.role_manager.get_session(session_id)

    if not session:
        raise HTTPException(status_code=401, detail="Invalid session")

    return session.to_dict()


@auth_router.get("/roles")
async def get_available_roles(request: Request):
    """Get available roles for login selection"""
    state = get_app_state(request)
    return state.role_manager.get_available_roles()


# ============================================================================
# Chat Endpoints
# ============================================================================

@chat_router.post("/message", response_model=ChatResponse)
async def send_message(request: Request, chat_data: ChatRequest):
    """Process chat message and return response"""
    state = get_app_state(request)

    # Verify session
    session = state.role_manager.get_session(chat_data.session_id)
    if not session:
        raise HTTPException(status_code=401, detail="Invalid session")

    # Set up RBAC filtering
    from ..auth.access_control import AccessController
    access_controller = AccessController()
    data_filter = access_controller.create_filter(session)
    allowed_doc_types = access_controller.get_allowed_document_types(session)

    # Process message with session context for RAG filtering
    response = state.chat_engine.chat(chat_data.message, allowed_doc_types=allowed_doc_types)

    # Filter response data based on user permissions
    filtered_data = data_filter.filter_project_state(response.data) if response.data else {}

    # Filter sources based on document type permissions
    filtered_sources = []
    for source in response.sources:
        doc_type = source.get('document_type', 'General')
        if doc_type in allowed_doc_types:
            filtered_sources.append(source)

    # Check if answer contains financial data that should be hidden
    answer = response.answer
    from ..auth.roles import Permission
    if Permission.VIEW_FINANCIAL_METRICS not in session.user.role.permissions and Permission.VIEW_ALL not in session.user.role.permissions:
        # Redact financial information from answer
        import re
        # Redact dollar amounts, percentages related to budget/cost/margin
        answer = re.sub(r'\$[\d,]+(?:\.\d{2})?', '[REDACTED]', answer)
        answer = re.sub(r'(?:budget|cost|margin|revenue|cpi)\s*[:\s]+[\d.,]+%?', '[FINANCIAL DATA RESTRICTED]', answer, flags=re.IGNORECASE)

    return ChatResponse(
        answer=answer,
        query_type=response.query_type,
        data=filtered_data,
        sources=filtered_sources,
        follow_up_questions=response.follow_up_questions,
        confidence=response.confidence
    )


@chat_router.get("/examples")
async def get_chat_examples(request: Request):
    """Get example chat queries"""
    state = get_app_state(request)
    return {"examples": state.chat_engine.get_examples()}


@chat_router.post("/clear/{session_id}")
async def clear_chat_context(request: Request, session_id: str):
    """Clear chat conversation context"""
    state = get_app_state(request)
    session = state.role_manager.get_session(session_id)

    if not session:
        raise HTTPException(status_code=401, detail="Invalid session")

    state.chat_engine.clear_context()
    return {"success": True, "message": "Context cleared"}


# ============================================================================
# Knowledge Graph Endpoints
# ============================================================================

@graph_router.get("/statistics")
async def get_graph_statistics(request: Request, session_id: str):
    """Get knowledge graph statistics"""
    state = get_app_state(request)
    session = state.role_manager.get_session(session_id)

    if not session:
        raise HTTPException(status_code=401, detail="Invalid session")

    stats = state.kg_builder.get_graph().get_statistics()
    return stats


@graph_router.get("/entities/{entity_type}")
async def get_entities_by_type(request: Request, entity_type: str, session_id: str):
    """Get entities of a specific type"""
    state = get_app_state(request)
    session = state.role_manager.get_session(session_id)

    if not session:
        raise HTTPException(status_code=401, detail="Invalid session")

    # Check permission
    from ..auth.access_control import DataFilter
    data_filter = DataFilter(session)

    if not data_filter.can_view_entity(entity_type):
        raise HTTPException(status_code=403, detail="Access denied to this entity type")

    entities = state.kg_builder.get_graph().get_nodes_by_type(entity_type)
    return {"entities": entities, "count": len(entities)}


@graph_router.get("/entity/{entity_id}")
async def get_entity(request: Request, entity_id: str, session_id: str):
    """Get specific entity details"""
    state = get_app_state(request)
    session = state.role_manager.get_session(session_id)

    if not session:
        raise HTTPException(status_code=401, detail="Invalid session")

    entity = state.kg_builder.get_entity(entity_id)
    if not entity:
        raise HTTPException(status_code=404, detail="Entity not found")

    return entity


@graph_router.get("/entity/{entity_id}/related")
async def get_related_entities(request: Request, entity_id: str, session_id: str):
    """Get entities related to a specific entity"""
    state = get_app_state(request)
    session = state.role_manager.get_session(session_id)

    if not session:
        raise HTTPException(status_code=401, detail="Invalid session")

    related = state.kg_builder.get_related_entities(entity_id)
    return {"entity_id": entity_id, "related": related}


@graph_router.get("/snapshots")
async def get_snapshots(request: Request, session_id: str):
    """Get available temporal snapshots"""
    state = get_app_state(request)
    session = state.role_manager.get_session(session_id)

    if not session:
        raise HTTPException(status_code=401, detail="Invalid session")

    summary = state.kg_builder.get_snapshots().summary()
    return summary


@graph_router.get("/snapshot/{date}")
async def get_snapshot_at_date(request: Request, date: str, session_id: str):
    """Get snapshot at specific date"""
    state = get_app_state(request)
    session = state.role_manager.get_session(session_id)

    if not session:
        raise HTTPException(status_code=401, detail="Invalid session")

    try:
        timestamp = datetime.strptime(date, "%Y-%m-%d")
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid date format. Use YYYY-MM-DD")

    snapshot = state.kg_builder.get_snapshots().get_snapshot_at(timestamp)
    if not snapshot:
        raise HTTPException(status_code=404, detail="No snapshot found for this date")

    # Filter based on permissions
    from ..auth.access_control import DataFilter
    data_filter = DataFilter(session)

    summary = snapshot.summary()
    return summary


@graph_router.get("/timeline")
async def get_timeline(request: Request, session_id: str, start: str = None, end: str = None):
    """Get project timeline"""
    state = get_app_state(request)
    session = state.role_manager.get_session(session_id)

    if not session:
        raise HTTPException(status_code=401, detail="Invalid session")

    start_date = datetime.strptime(start, "%Y-%m-%d") if start else datetime(2025, 12, 1)
    end_date = datetime.strptime(end, "%Y-%m-%d") if end else datetime(2026, 3, 7)

    timeline = state.query_engine.get_timeline(start_date, end_date)
    return {"timeline": timeline}


@graph_router.get("/data")
async def get_graph_data(request: Request, session_id: str, snapshot_index: int = None):
    """Get full graph data for visualization"""
    state = get_app_state(request)
    session = state.role_manager.get_session(session_id)

    if not session:
        raise HTTPException(status_code=401, detail="Invalid session")

    # Get snapshots info
    snapshot_manager = state.kg_builder.get_snapshots()
    snapshot_manager._ensure_sorted()
    timeline = snapshot_manager.timeline

    # Build ordered snapshot list
    snapshot_list = []
    for i, ts in enumerate(timeline):
        key = ts.strftime("%Y-%m-%d")
        snap = snapshot_manager.snapshots.get(key)
        if snap:
            snapshot_list.append({
                'index': i,
                'label': snap.label,
                'timestamp': snap.timestamp.isoformat() if snap.timestamp else None
            })

    # If snapshot_index provided, get that snapshot's graph
    if snapshot_index is not None and 0 <= snapshot_index < len(timeline):
        ts = timeline[snapshot_index]
        key = ts.strftime("%Y-%m-%d")
        snapshot = snapshot_manager.snapshots.get(key)
        if snapshot:
            graph = snapshot.graph
            label = snapshot.label
        else:
            graph = state.kg_builder.get_graph().graph
            label = "Current State"
    else:
        # Use current graph
        graph = state.kg_builder.get_graph().graph
        label = "Current State"

    # Create data filter for RBAC
    from ..auth.access_control import DataFilter
    from ..auth.roles import Permission
    data_filter = DataFilter(session)

    # Financial attributes to hide from non-financial users
    financial_attrs = {'budget', 'cost', 'value', 'margin', 'revenue', 'cpi', 'actual_cost', 'planned_cost'}

    # Extract nodes and edges with RBAC filtering
    nodes = []
    visible_node_ids = set()

    for node_id in graph.nodes():
        node_data = dict(graph.nodes[node_id])
        node_type = node_data.get('entity_type', 'Unknown')

        # Check if user can view this entity type
        if not data_filter.can_view_entity(node_type, node_data):
            continue

        node_label = node_data.get('name', node_data.get('label', node_id))

        # Filter node attributes based on permissions
        filtered_data = {}
        for k, v in node_data.items():
            if k == 'entity_type':
                continue
            # Hide financial attributes if user doesn't have permission
            if k.lower() in financial_attrs and not data_filter.has_permission(Permission.VIEW_FINANCIAL_METRICS):
                continue
            filtered_data[k] = str(v) if v is not None else ''

        nodes.append({
            'id': node_id,
            'label': str(node_label)[:30],
            'type': node_type,
            'data': filtered_data
        })
        visible_node_ids.add(node_id)

    # Only include edges between visible nodes
    edges = []
    for source, target, data in graph.edges(data=True):
        if source in visible_node_ids and target in visible_node_ids:
            edges.append({
                'source': source,
                'target': target,
                'type': data.get('relation_type', 'RELATED')
            })

    return {
        'nodes': nodes,
        'edges': edges,
        'current_label': label,
        'snapshots': snapshot_list,
        'total_snapshots': len(timeline)
    }


# ============================================================================
# Metrics Endpoints
# ============================================================================

@metrics_router.get("/list")
async def list_metrics(request: Request, session_id: str):
    """Get list of available metrics"""
    state = get_app_state(request)
    session = state.role_manager.get_session(session_id)

    if not session:
        raise HTTPException(status_code=401, detail="Invalid session")

    all_metrics = state.metrics_store.get_all_metrics()

    # Filter based on permissions
    from ..auth.access_control import DataFilter
    data_filter = DataFilter(session)

    allowed_metrics = [m for m in all_metrics if data_filter.can_view_metric(m)]
    return {"metrics": allowed_metrics}


@metrics_router.get("/series/{metric_name}")
async def get_metric_series(request: Request, metric_name: str, session_id: str):
    """Get time series for a metric"""
    state = get_app_state(request)
    session = state.role_manager.get_session(session_id)

    if not session:
        raise HTTPException(status_code=401, detail="Invalid session")

    # Check permission
    from ..auth.access_control import DataFilter
    data_filter = DataFilter(session)

    if not data_filter.can_view_metric(metric_name):
        raise HTTPException(status_code=403, detail="Access denied to this metric")

    series = state.metrics_store.get_series(metric_name)
    if not series:
        raise HTTPException(status_code=404, detail="Metric not found")

    return {
        "metric_name": metric_name,
        "data_points": [dp.to_dict() for dp in series.data_points],
        "statistics": series.get_statistics()
    }


@metrics_router.get("/trends/{metric_name}")
async def get_metric_trends(request: Request, metric_name: str, session_id: str):
    """Get trend analysis for a metric"""
    state = get_app_state(request)
    session = state.role_manager.get_session(session_id)

    if not session:
        raise HTTPException(status_code=401, detail="Invalid session")

    from ..auth.access_control import DataFilter
    data_filter = DataFilter(session)

    if not data_filter.can_view_metric(metric_name):
        raise HTTPException(status_code=403, detail="Access denied to this metric")

    trend = state.trend_analyzer.analyze_trend(metric_name)
    if not trend:
        raise HTTPException(status_code=404, detail="Not enough data for trend analysis")

    return {
        "metric_name": metric_name,
        "direction": trend.direction.value,
        "slope": trend.slope,
        "confidence": trend.confidence,
        "change_pct": trend.change_pct,
        "forecast_next": trend.forecast_next
    }


# ============================================================================
# Simulation Endpoints
# ============================================================================

@simulation_router.get("/scenarios")
async def list_scenarios(request: Request, session_id: str):
    """Get available simulation scenarios"""
    state = get_app_state(request)
    session = state.role_manager.get_session(session_id)

    if not session:
        raise HTTPException(status_code=401, detail="Invalid session")

    from ..auth.roles import Permission
    if Permission.RUN_SIMULATIONS not in session.user.role.permissions and \
       Permission.VIEW_ALL not in session.user.role.permissions:
        raise HTTPException(status_code=403, detail="No permission to run simulations")

    scenarios = state.simulator.get_available_scenarios()
    return {"scenarios": scenarios}


@simulation_router.get("/scenario/{scenario_id}/parameters")
async def get_scenario_parameters(request: Request, scenario_id: str, session_id: str):
    """Get parameters for a simulation scenario"""
    state = get_app_state(request)
    session = state.role_manager.get_session(session_id)

    if not session:
        raise HTTPException(status_code=401, detail="Invalid session")

    params = state.simulator.get_scenario_parameters(scenario_id)
    if not params:
        raise HTTPException(status_code=404, detail="Scenario not found")

    return {"scenario_id": scenario_id, "parameters": params}


@simulation_router.post("/run")
async def run_simulation(request: Request, sim_data: SimulationRequest, session_id: str):
    """Run a simulation scenario"""
    state = get_app_state(request)
    session = state.role_manager.get_session(session_id)

    if not session:
        raise HTTPException(status_code=401, detail="Invalid session")

    from ..auth.roles import Permission
    if Permission.RUN_SIMULATIONS not in session.user.role.permissions and \
       Permission.VIEW_ALL not in session.user.role.permissions:
        raise HTTPException(status_code=403, detail="No permission to run simulations")

    try:
        result = state.simulator.run_simulation(
            sim_data.scenario_id,
            sim_data.parameters
        )
        return {
            "scenario_name": result.scenario_name,
            "parameters": result.parameters,
            "outcomes": result.outcomes,
            "probability": result.probability,
            "impact_assessment": result.impact_assessment,
            "recommendations": result.recommendations
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@simulation_router.post("/forecast")
async def generate_forecast(request: Request, forecast_data: ForecastRequest, session_id: str):
    """Generate project forecast"""
    state = get_app_state(request)
    session = state.role_manager.get_session(session_id)

    if not session:
        raise HTTPException(status_code=401, detail="Invalid session")

    from ..auth.roles import Permission
    if Permission.VIEW_FORECASTS not in session.user.role.permissions and \
       Permission.VIEW_ALL not in session.user.role.permissions:
        raise HTTPException(status_code=403, detail="No permission to view forecasts")

    ref_date = None
    if forecast_data.reference_date:
        try:
            ref_date = datetime.strptime(forecast_data.reference_date, "%Y-%m-%d")
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid date format")

    forecast = state.forecaster.generate_forecast(
        reference_date=ref_date,
        horizon_days=forecast_data.horizon_days
    )

    return {
        "generated_at": forecast.generated_at.isoformat(),
        "horizon_days": forecast.horizon_days,
        "milestone_forecasts": [
            {
                "name": m.milestone_name,
                "target_date": m.target_date.isoformat(),
                "predicted_date": m.predicted_date.isoformat(),
                "probability_on_time": m.probability_on_time,
                "risk_factors": m.risk_factors
            }
            for m in forecast.milestone_forecasts
        ],
        "risk_outlook": forecast.risk_outlook,
        "summary": forecast.summary
    }


@simulation_router.get("/risks")
async def get_risk_predictions(request: Request, session_id: str):
    """Get current risk predictions"""
    state = get_app_state(request)
    session = state.role_manager.get_session(session_id)

    if not session:
        raise HTTPException(status_code=401, detail="Invalid session")

    from ..auth.roles import Permission
    if Permission.RUN_PREDICTIONS not in session.user.role.permissions and \
       Permission.VIEW_ALL not in session.user.role.permissions:
        raise HTTPException(status_code=403, detail="No permission to view predictions")

    predictions = state.risk_predictor.predict_risks()

    return {
        "predictions": [
            {
                "risk_id": p.risk_id,
                "risk_type": p.risk_type,
                "description": p.description,
                "probability": p.probability,
                "severity": p.severity,
                "factors": p.contributing_factors,
                "actions": p.recommended_actions
            }
            for p in predictions
        ]
    }
