"""
Main FastAPI Application
Project Knowledge Graph Chatbot with Role-Based Access
"""

import sys
import logging
from pathlib import Path
from datetime import datetime
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.middleware.cors import CORSMiddleware

# Load environment variables from .env file
from dotenv import load_dotenv
load_dotenv()

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Import routes
from src.api.routes import (
    auth_router, chat_router, graph_router,
    metrics_router, simulation_router, delivery_brain_router, admin_router
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize application state on startup"""
    logger.info("Initializing application...")

    # Import components
    from src.ingestion.pipeline import create_default_pipeline
    from src.ingestion.parsers.qa_review_parser import QAReviewParser
    from src.ingestion.parsers.finance_parser import FinanceReviewParser
    from src.knowledge_graph.builder import KnowledgeGraphBuilder
    from src.time_series.metrics_store import TimeSeriesMetricsStore
    from src.time_series.trend_analyzer import TrendAnalyzer
    from src.inference.query_engine import TemporalQueryEngine
    from src.inference.risk_predictor import RiskPredictor
    from src.chatbot.chat_engine import ChatEngine
    from src.simulation.forecaster import ProjectForecaster
    from src.simulation.scenario_simulator import ScenarioSimulator
    from src.auth.roles import RoleManager
    from src.rag.rag_engine import RAGEngine
    from src.llm.llm_service import LLMService, LLMConfig

    # Create role manager
    app.state.role_manager = RoleManager()
    logger.info("Role manager initialized with demo users")

    # Create ingestion pipeline with additional parsers
    pipeline = create_default_pipeline()
    pipeline.add_parser(QAReviewParser())
    pipeline.add_parser(FinanceReviewParser())

    # Find and ingest data
    possible_paths = [
        Path("../ABC Inc. Simulacra"),
        Path("./ABC Inc. Simulacra"),
        Path("C:/Users/shubhashis.sengupta/TestClaude/ABC Inc. Simulacra"),
    ]

    data_dir = None
    for path in possible_paths:
        if path.exists():
            data_dir = path
            break

    documents = []
    if data_dir:
        logger.info(f"Ingesting data from {data_dir}")
        documents = pipeline.ingest_directory(data_dir)
        logger.info(f"Ingested {len(documents)} documents")

    # Build knowledge graph
    kg_builder = KnowledgeGraphBuilder()
    if documents:
        kg_builder.build_from_documents(documents)
        logger.info(f"Built graph with {kg_builder.graph.graph.number_of_nodes()} nodes")

    # Initialize metrics store
    metrics_store = TimeSeriesMetricsStore()
    for doc in documents:
        if doc.metrics:
            for metric_name, value in doc.metrics.items():
                if value is not None and isinstance(value, (int, float)):
                    metrics_store.add_metric(metric_name, doc.timestamp, float(value))

    # Create query engine
    query_engine = TemporalQueryEngine(
        kg_builder.get_graph(),
        kg_builder.get_snapshots(),
        metrics_store
    )

    # Create analyzers and predictors
    trend_analyzer = TrendAnalyzer(metrics_store)
    risk_predictor = RiskPredictor(query_engine, metrics_store)
    forecaster = ProjectForecaster(metrics_store, query_engine)
    simulator = ScenarioSimulator(query_engine, metrics_store)

    # Initialize LLM service (Azure OpenAI as default, fallback to TF-IDF)
    llm_config = LLMConfig()
    llm_service = LLMService(llm_config)
    if llm_service.is_available():
        logger.info(f"LLM service initialized with provider: {llm_service.get_provider()}")
    else:
        logger.warning("LLM service not available - using template-based responses")

    # Create RAG engine with vector store and LLM support
    rag_engine = RAGEngine(llm_service=llm_service, use_vector_store=True)
    if data_dir:
        chunk_count = rag_engine.initialize(data_dir)
        logger.info(f"RAG engine initialized with {rag_engine.store.stats()['total_documents']} documents, {chunk_count} chunks")
        if rag_engine.vector_store and rag_engine.vector_store.is_initialized:
            logger.info(f"Vector store: {rag_engine.vector_store.get_stats()['document_count']} embeddings indexed")

    # Create chat engine with RAG and LLM support
    chat_engine = ChatEngine(query_engine, risk_predictor, metrics_store, rag_engine=rag_engine, llm_client=llm_service)

    # Store in app state
    app.state.pipeline = pipeline
    app.state.kg_builder = kg_builder
    app.state.metrics_store = metrics_store
    app.state.query_engine = query_engine
    app.state.trend_analyzer = trend_analyzer
    app.state.risk_predictor = risk_predictor
    app.state.forecaster = forecaster
    app.state.simulator = simulator
    app.state.chat_engine = chat_engine

    logger.info("Application initialization complete!")

    yield

    # Cleanup
    logger.info("Shutting down application...")


# Create FastAPI application
app = FastAPI(
    title="Project KG Chatbot",
    description="Knowledge Graph based Project Intelligence with Role-Based Access",
    version="1.0.0",
    lifespan=lifespan
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount static files
static_path = Path(__file__).parent / "ui" / "static"
if static_path.exists():
    app.mount("/static", StaticFiles(directory=str(static_path)), name="static")

# Setup templates
templates_path = Path(__file__).parent / "ui" / "templates"
templates = Jinja2Templates(directory=str(templates_path)) if templates_path.exists() else None

# Include API routers
app.include_router(auth_router)
app.include_router(chat_router)
app.include_router(graph_router)
app.include_router(metrics_router)
app.include_router(simulation_router)
app.include_router(delivery_brain_router, prefix="/api")
app.include_router(admin_router, prefix="/api")


# ============================================================================
# UI Routes
# ============================================================================

@app.get("/", response_class=HTMLResponse)
async def root(request: Request):
    """Home page - redirect to login"""
    return RedirectResponse(url="/login")


@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    """Login page"""
    if templates:
        return templates.TemplateResponse("login.html", {"request": request})
    return HTMLResponse(content=get_login_html(), status_code=200)


@app.get("/chat", response_class=HTMLResponse)
async def chat_page(request: Request):
    """Chat interface"""
    if templates:
        return templates.TemplateResponse("chat.html", {"request": request})
    return HTMLResponse(content=get_chat_html(), status_code=200)


@app.get("/graph", response_class=HTMLResponse)
async def graph_page(request: Request):
    """Knowledge Graph visualization"""
    if templates:
        return templates.TemplateResponse("graph.html", {"request": request})
    return HTMLResponse(content=get_graph_html(), status_code=200)


@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard_page(request: Request):
    """Dashboard view"""
    if templates:
        return templates.TemplateResponse("dashboard.html", {"request": request})
    return HTMLResponse(content=get_dashboard_html(), status_code=200)


@app.get("/simulation", response_class=HTMLResponse)
async def simulation_page(request: Request):
    """Simulation interface"""
    if templates:
        return templates.TemplateResponse("simulation.html", {"request": request})
    return HTMLResponse(content=get_simulation_html(), status_code=200)


# ============================================================================
# Inline HTML Templates (fallback if templates directory doesn't exist)
# ============================================================================

def get_base_html(title: str, content: str) -> str:
    """Base HTML template"""
    return f'''
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{title} - Project KG Chatbot</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.2/dist/css/bootstrap.min.css" rel="stylesheet">
    <link href="https://cdn.jsdelivr.net/npm/bootstrap-icons@1.11.1/font/bootstrap-icons.css" rel="stylesheet">
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    <script src="https://cdn.plot.ly/plotly-2.27.0.min.js"></script>
    <script src="https://d3js.org/d3.v7.min.js"></script>
    <style>
        :root {{
            --primary-color: #4f46e5;
            --secondary-color: #6366f1;
            --bg-dark: #1e1e2e;
            --bg-card: #2d2d3f;
            --text-primary: #e4e4e7;
            --text-secondary: #a1a1aa;
        }}
        body {{
            background-color: var(--bg-dark);
            color: var(--text-primary);
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
        }}
        .sidebar {{
            background-color: var(--bg-card);
            min-height: 100vh;
            padding: 20px;
        }}
        .card {{
            background-color: var(--bg-card);
            border: 1px solid #3d3d4f;
            border-radius: 12px;
        }}
        .btn-primary {{
            background-color: var(--primary-color);
            border-color: var(--primary-color);
        }}
        .btn-primary:hover {{
            background-color: var(--secondary-color);
            border-color: var(--secondary-color);
        }}
        .nav-link {{
            color: var(--text-secondary);
        }}
        .nav-link:hover, .nav-link.active {{
            color: var(--text-primary);
            background-color: rgba(79, 70, 229, 0.2);
            border-radius: 8px;
        }}
        .chat-container {{
            height: calc(100vh - 220px);
            overflow-y: auto;
            padding: 20px;
            scroll-behavior: smooth;
        }}
        .message {{
            padding: 16px 20px;
            border-radius: 16px;
            margin-bottom: 16px;
            max-width: 85%;
            line-height: 1.6;
            animation: fadeIn 0.3s ease-in;
        }}
        @keyframes fadeIn {{
            from {{ opacity: 0; transform: translateY(10px); }}
            to {{ opacity: 1; transform: translateY(0); }}
        }}
        .message-user {{
            background: linear-gradient(135deg, var(--primary-color), var(--secondary-color));
            margin-left: auto;
            color: white;
            box-shadow: 0 4px 15px rgba(79, 70, 229, 0.3);
        }}
        .message-assistant {{
            background-color: #2a2a3d;
            border: 1px solid #404055;
            box-shadow: 0 2px 10px rgba(0, 0, 0, 0.2);
        }}
        .message-assistant ul {{
            margin-bottom: 0;
            padding-left: 20px;
        }}
        .message-assistant li {{
            margin-bottom: 6px;
        }}
        .message-assistant strong {{
            color: #a78bfa;
        }}
        .message-header {{
            font-size: 0.75rem;
            text-transform: uppercase;
            letter-spacing: 0.5px;
            margin-bottom: 8px;
            opacity: 0.7;
        }}
        .user-panel {{
            background: linear-gradient(180deg, rgba(79, 70, 229, 0.1) 0%, transparent 100%);
            border-radius: 12px;
            padding: 16px;
            margin-bottom: 16px;
        }}
        .user-avatar {{
            width: 48px;
            height: 48px;
            border-radius: 50%;
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 1.25rem;
            margin-right: 12px;
        }}
        .user-name {{
            font-weight: 600;
            font-size: 1rem;
            margin-bottom: 2px;
        }}
        .user-role {{
            font-size: 0.8rem;
            opacity: 0.8;
        }}
        .role-badge {{
            display: inline-flex;
            align-items: center;
            padding: 8px 14px;
            border-radius: 12px;
            font-size: 0.875rem;
        }}
        .chat-input-container {{
            background-color: #2a2a3d;
            border-radius: 12px;
            padding: 4px;
        }}
        .chat-input {{
            background-color: transparent !important;
            border: none !important;
            color: var(--text-primary) !important;
        }}
        .chat-input:focus {{
            box-shadow: none !important;
        }}
        .suggestion-btn {{
            background-color: rgba(79, 70, 229, 0.2);
            border: 1px solid rgba(79, 70, 229, 0.3);
            color: #a78bfa;
            transition: all 0.2s;
        }}
        .suggestion-btn:hover {{
            background-color: rgba(79, 70, 229, 0.4);
            color: white;
        }}
        #graph-container {{
            height: 600px;
            background-color: var(--bg-card);
            border-radius: 12px;
        }}
    </style>
</head>
<body>
    {content}
    <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.2/dist/js/bootstrap.bundle.min.js"></script>
</body>
</html>
'''


def get_login_html() -> str:
    """Login page HTML"""
    content = '''
    <div class="container">
        <div class="row justify-content-center align-items-center min-vh-100">
            <div class="col-md-6 col-lg-4">
                <div class="card p-4">
                    <div class="text-center mb-4">
                        <i class="bi bi-diagram-3 text-primary" style="font-size: 3rem;"></i>
                        <h2 class="mt-3">Project KG Chatbot</h2>
                        <p class="text-secondary">ABC Inc. SAP S/4HANA Migration</p>
                    </div>

                    <div id="login-form">
                        <div class="mb-3">
                            <label class="form-label">Select Role</label>
                            <div id="role-buttons" class="d-grid gap-2">
                                <!-- Roles will be loaded here -->
                            </div>
                        </div>

                        <div class="mb-3">
                            <label class="form-label">Password</label>
                            <input type="password" id="password" class="form-control bg-dark text-light border-secondary" value="demo123">
                            <small class="text-secondary">Demo password: demo123</small>
                        </div>

                        <div id="error-message" class="alert alert-danger d-none"></div>

                        <button id="login-btn" class="btn btn-primary w-100" disabled>
                            <i class="bi bi-box-arrow-in-right me-2"></i>Login
                        </button>

                        <hr class="my-3">
                        <button type="button" class="btn btn-outline-info w-100" data-bs-toggle="modal" data-bs-target="#dataAdminModal">
                            <i class="bi bi-database-gear me-2"></i>Data Admin
                        </button>
                    </div>
                </div>
            </div>
        </div>
    </div>

    <!-- Data Admin Modal -->
    <div class="modal fade" id="dataAdminModal" tabindex="-1" aria-labelledby="dataAdminModalLabel" aria-hidden="true">
        <div class="modal-dialog modal-lg modal-dialog-centered">
            <div class="modal-content bg-dark text-light">
                <div class="modal-header border-secondary">
                    <h5 class="modal-title" id="dataAdminModalLabel">
                        <i class="bi bi-database-gear me-2"></i>Data Ingestion Pipeline
                    </h5>
                    <button type="button" class="btn-close btn-close-white" data-bs-dismiss="modal" aria-label="Close"></button>
                </div>
                <div class="modal-body">
                    <!-- Tabs -->
                    <ul class="nav nav-tabs mb-3" id="adminTabs" role="tablist">
                        <li class="nav-item" role="presentation">
                            <button class="nav-link active" id="ingest-tab" data-bs-toggle="tab" data-bs-target="#ingest-panel" type="button">
                                <i class="bi bi-upload me-1"></i>Ingest Data
                            </button>
                        </li>
                        <li class="nav-item" role="presentation">
                            <button class="nav-link" id="stats-tab" data-bs-toggle="tab" data-bs-target="#stats-panel" type="button">
                                <i class="bi bi-bar-chart me-1"></i>Statistics
                            </button>
                        </li>
                        <li class="nav-item" role="presentation">
                            <button class="nav-link" id="history-tab" data-bs-toggle="tab" data-bs-target="#history-panel" type="button">
                                <i class="bi bi-clock-history me-1"></i>History
                            </button>
                        </li>
                    </ul>

                    <div class="tab-content">
                        <!-- Ingest Tab -->
                        <div class="tab-pane fade show active" id="ingest-panel" role="tabpanel">
                            <div class="mb-3">
                                <label class="form-label">Folder Path</label>
                                <div class="input-group">
                                    <span class="input-group-text bg-secondary border-secondary"><i class="bi bi-folder"></i></span>
                                    <input type="text" id="folder-path" class="form-control bg-dark text-light border-secondary"
                                           placeholder="C:\\path\\to\\documents or /path/to/documents">
                                </div>
                                <small class="text-secondary">Enter the full path to the folder containing files to ingest</small>
                            </div>

                            <div class="row mb-3">
                                <div class="col-md-6">
                                    <div class="form-check">
                                        <input class="form-check-input" type="checkbox" id="recursive-check" checked>
                                        <label class="form-check-label" for="recursive-check">
                                            Include subfolders (recursive)
                                        </label>
                                    </div>
                                </div>
                                <div class="col-md-6">
                                    <div class="form-check">
                                        <input class="form-check-input" type="checkbox" id="update-kg-check" checked>
                                        <label class="form-check-label" for="update-kg-check">
                                            Update Knowledge Graph
                                        </label>
                                    </div>
                                </div>
                            </div>

                            <div class="card bg-secondary mb-3">
                                <div class="card-body py-2">
                                    <h6 class="card-title mb-2"><i class="bi bi-info-circle me-1"></i>Pipeline Steps</h6>
                                    <div class="row small">
                                        <div class="col-6">
                                            <i class="bi bi-check-circle text-success me-1"></i>NoSQL DB (TinyDB/MongoDB)<br>
                                            <i class="bi bi-check-circle text-success me-1"></i>TF-IDF Indexing
                                        </div>
                                        <div class="col-6">
                                            <i class="bi bi-check-circle text-success me-1"></i>Vector DB (ChromaDB)<br>
                                            <i class="bi bi-check-circle text-success me-1"></i>Knowledge Graph Update
                                        </div>
                                    </div>
                                </div>
                            </div>

                            <div id="supported-formats" class="mb-3 small">
                                <strong>Supported formats:</strong> <span id="formats-list">Loading...</span>
                            </div>

                            <!-- Progress Section -->
                            <div id="ingestion-progress" class="d-none">
                                <div class="progress mb-2" style="height: 25px;">
                                    <div id="progress-bar" class="progress-bar progress-bar-striped progress-bar-animated"
                                         role="progressbar" style="width: 0%">0%</div>
                                </div>
                                <div id="progress-status" class="text-center text-secondary mb-2">Initializing...</div>
                            </div>

                            <!-- Results Section -->
                            <div id="ingestion-results" class="d-none">
                                <div class="alert alert-success">
                                    <h6><i class="bi bi-check-circle me-1"></i>Ingestion Complete</h6>
                                    <div class="row mt-2">
                                        <div class="col-md-3 text-center">
                                            <div class="h4 mb-0" id="result-files">0</div>
                                            <small>Files Processed</small>
                                        </div>
                                        <div class="col-md-3 text-center">
                                            <div class="h4 mb-0" id="result-chunks">0</div>
                                            <small>Chunks Created</small>
                                        </div>
                                        <div class="col-md-3 text-center">
                                            <div class="h4 mb-0" id="result-vectors">0</div>
                                            <small>Vectors Stored</small>
                                        </div>
                                        <div class="col-md-3 text-center">
                                            <div class="h4 mb-0" id="result-kg-nodes">0</div>
                                            <small>KG Nodes</small>
                                        </div>
                                    </div>
                                </div>
                            </div>

                            <div id="ingestion-error" class="alert alert-danger d-none"></div>
                        </div>

                        <!-- Statistics Tab -->
                        <div class="tab-pane fade" id="stats-panel" role="tabpanel">
                            <div id="stats-content">
                                <div class="text-center py-4">
                                    <div class="spinner-border text-primary" role="status"></div>
                                    <p class="mt-2">Loading statistics...</p>
                                </div>
                            </div>
                        </div>

                        <!-- History Tab -->
                        <div class="tab-pane fade" id="history-panel" role="tabpanel">
                            <div id="history-content">
                                <div class="text-center py-4">
                                    <div class="spinner-border text-primary" role="status"></div>
                                    <p class="mt-2">Loading history...</p>
                                </div>
                            </div>
                        </div>
                    </div>
                </div>
                <div class="modal-footer border-secondary">
                    <button type="button" class="btn btn-secondary" data-bs-dismiss="modal">Close</button>
                    <button type="button" class="btn btn-primary" id="start-ingestion-btn">
                        <i class="bi bi-play-fill me-1"></i>Start Ingestion
                    </button>
                </div>
            </div>
        </div>
    </div>

    <script>
        let selectedUser = null;
        let adminSessionId = null;

        // Load available roles
        fetch('/api/auth/roles')
            .then(r => r.json())
            .then(roles => {
                const container = document.getElementById('role-buttons');
                roles.forEach(role => {
                    const btn = document.createElement('button');
                    btn.className = 'btn btn-outline-secondary text-start';
                    btn.innerHTML = `
                        <div class="d-flex align-items-center">
                            <i class="bi bi-${role.icon} me-3" style="font-size: 1.5rem; color: ${role.color}"></i>
                            <div>
                                <strong>${role.display_name}</strong>
                                <br><small class="text-secondary">${role.description}</small>
                            </div>
                        </div>
                    `;
                    btn.onclick = () => selectRole(role, btn);
                    container.appendChild(btn);
                });
            });

        function selectRole(role, btn) {
            document.querySelectorAll('#role-buttons button').forEach(b => {
                b.classList.remove('btn-primary');
                b.classList.add('btn-outline-secondary');
            });
            btn.classList.remove('btn-outline-secondary');
            btn.classList.add('btn-primary');
            selectedUser = role.demo_user;
            document.getElementById('login-btn').disabled = false;
        }

        document.getElementById('login-btn').onclick = async () => {
            const password = document.getElementById('password').value;

            const response = await fetch('/api/auth/login', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({username: selectedUser, password: password})
            });

            const data = await response.json();

            if (data.success) {
                localStorage.setItem('session_id', data.session_id);
                localStorage.setItem('user', JSON.stringify(data.user));
                window.location.href = '/chat';
            } else {
                document.getElementById('error-message').textContent = data.message;
                document.getElementById('error-message').classList.remove('d-none');
            }
        };

        // Data Admin Modal Functions
        async function getAdminSession() {
            if (adminSessionId) return adminSessionId;
            // Login as admin for data operations
            const response = await fetch('/api/auth/login', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({username: 'roshan', password: 'Acc1234$$'})
            });
            const data = await response.json();
            if (data.success) {
                adminSessionId = data.session_id;
                return adminSessionId;
            }
            throw new Error('Failed to get admin session');
        }

        // Load supported formats when modal opens
        document.getElementById('dataAdminModal').addEventListener('show.bs.modal', async () => {
            try {
                const response = await fetch('/api/delivery-brain/supported-formats');
                const formats = await response.json();
                const allFormats = formats.all_formats.join(', ');
                document.getElementById('formats-list').textContent = allFormats;
            } catch (e) {
                document.getElementById('formats-list').textContent = 'Failed to load';
            }
        });

        // Load statistics when tab clicked
        document.getElementById('stats-tab').addEventListener('click', async () => {
            try {
                const sessionId = await getAdminSession();
                const response = await fetch(`/api/delivery-brain/statistics?session_id=${sessionId}`);
                const stats = await response.json();

                document.getElementById('stats-content').innerHTML = `
                    <div class="row g-3">
                        <div class="col-md-4">
                            <div class="card bg-secondary">
                                <div class="card-body text-center">
                                    <i class="bi bi-database h2 text-primary"></i>
                                    <h4>${stats.nosql?.document_count || 0}</h4>
                                    <small>Documents in NoSQL</small>
                                </div>
                            </div>
                        </div>
                        <div class="col-md-4">
                            <div class="card bg-secondary">
                                <div class="card-body text-center">
                                    <i class="bi bi-boxes h2 text-success"></i>
                                    <h4>${stats.vector?.total_chunks || 0}</h4>
                                    <small>Vectors in ChromaDB</small>
                                </div>
                            </div>
                        </div>
                        <div class="col-md-4">
                            <div class="card bg-secondary">
                                <div class="card-body text-center">
                                    <i class="bi bi-hdd h2 text-info"></i>
                                    <h4>${stats.nosql?.total_chunks || 0}</h4>
                                    <small>Total Chunks</small>
                                </div>
                            </div>
                        </div>
                    </div>
                    <div class="mt-3">
                        <h6>File Types Processed:</h6>
                        <div class="row">
                            ${Object.entries(stats.nosql?.file_types || {}).map(([type, count]) => `
                                <div class="col-md-3 mb-2">
                                    <span class="badge bg-primary me-1">${count}</span> ${type}
                                </div>
                            `).join('')}
                        </div>
                    </div>
                `;
            } catch (e) {
                document.getElementById('stats-content').innerHTML = `
                    <div class="alert alert-warning">Failed to load statistics: ${e.message}</div>
                `;
            }
        });

        // Load history when tab clicked
        document.getElementById('history-tab').addEventListener('click', async () => {
            try {
                const sessionId = await getAdminSession();
                const response = await fetch(`/api/delivery-brain/history?session_id=${sessionId}&limit=10`);
                const data = await response.json();

                if (data.history && data.history.length > 0) {
                    document.getElementById('history-content').innerHTML = `
                        <div class="table-responsive">
                            <table class="table table-dark table-sm">
                                <thead>
                                    <tr>
                                        <th>Timestamp</th>
                                        <th>Directory</th>
                                        <th>Files</th>
                                        <th>Chunks</th>
                                        <th>Duration</th>
                                    </tr>
                                </thead>
                                <tbody>
                                    ${data.history.map(h => `
                                        <tr>
                                            <td><small>${new Date(h.timestamp).toLocaleString()}</small></td>
                                            <td><small>${h.directory || 'N/A'}</small></td>
                                            <td>${h.processed_files || 0}/${h.total_files || 0}</td>
                                            <td>${h.total_chunks || 0}</td>
                                            <td>${(h.duration_seconds || 0).toFixed(1)}s</td>
                                        </tr>
                                    `).join('')}
                                </tbody>
                            </table>
                        </div>
                    `;
                } else {
                    document.getElementById('history-content').innerHTML = `
                        <div class="text-center text-secondary py-4">No ingestion history available</div>
                    `;
                }
            } catch (e) {
                document.getElementById('history-content').innerHTML = `
                    <div class="alert alert-warning">Failed to load history: ${e.message}</div>
                `;
            }
        });

        // Start Ingestion
        document.getElementById('start-ingestion-btn').onclick = async () => {
            const folderPath = document.getElementById('folder-path').value.trim();
            if (!folderPath) {
                alert('Please enter a folder path');
                return;
            }

            const recursive = document.getElementById('recursive-check').checked;
            const updateKG = document.getElementById('update-kg-check').checked;

            // Show progress, hide results/error
            document.getElementById('ingestion-progress').classList.remove('d-none');
            document.getElementById('ingestion-results').classList.add('d-none');
            document.getElementById('ingestion-error').classList.add('d-none');
            document.getElementById('start-ingestion-btn').disabled = true;

            const progressBar = document.getElementById('progress-bar');
            const progressStatus = document.getElementById('progress-status');

            try {
                const sessionId = await getAdminSession();

                // Step 1: Ingest to NoSQL and Vector DB (30%)
                progressBar.style.width = '10%';
                progressBar.textContent = '10%';
                progressStatus.textContent = 'Step 1/4: Ingesting files to NoSQL and Vector DB...';

                const ingestResponse = await fetch(`/api/delivery-brain/ingest?session_id=${sessionId}&directory=${encodeURIComponent(folderPath)}&recursive=${recursive}`, {
                    method: 'POST'
                });
                const ingestResult = await ingestResponse.json();

                if (!ingestResult.success && ingestResult.processed_files === 0) {
                    throw new Error(ingestResult.detail || 'Ingestion failed');
                }

                progressBar.style.width = '40%';
                progressBar.textContent = '40%';
                progressStatus.textContent = 'Step 2/4: Updating TF-IDF index...';

                // Step 2: TF-IDF is already handled by RAG engine, just simulate
                await new Promise(r => setTimeout(r, 500));

                progressBar.style.width = '60%';
                progressBar.textContent = '60%';
                progressStatus.textContent = 'Step 3/4: Updating Vector embeddings...';

                // Step 3: Vector embeddings already done in ingest
                await new Promise(r => setTimeout(r, 500));

                let kgNodes = 0;
                if (updateKG) {
                    progressBar.style.width = '80%';
                    progressBar.textContent = '80%';
                    progressStatus.textContent = 'Step 4/4: Updating Knowledge Graph...';

                    // Step 4: Update KG
                    const kgResponse = await fetch(`/api/admin/rebuild-kg?session_id=${sessionId}&directory=${encodeURIComponent(folderPath)}`, {
                        method: 'POST'
                    });
                    const kgResult = await kgResponse.json();
                    kgNodes = kgResult.node_count || 0;
                }

                progressBar.style.width = '100%';
                progressBar.textContent = '100%';
                progressBar.classList.remove('progress-bar-animated');
                progressStatus.textContent = 'Complete!';

                // Show results
                document.getElementById('result-files').textContent = ingestResult.processed_files || 0;
                document.getElementById('result-chunks').textContent = ingestResult.total_chunks || 0;
                document.getElementById('result-vectors').textContent = ingestResult.total_chunks || 0;
                document.getElementById('result-kg-nodes').textContent = kgNodes;
                document.getElementById('ingestion-results').classList.remove('d-none');

            } catch (e) {
                document.getElementById('ingestion-error').textContent = `Error: ${e.message}`;
                document.getElementById('ingestion-error').classList.remove('d-none');
                progressBar.classList.add('bg-danger');
            } finally {
                document.getElementById('start-ingestion-btn').disabled = false;
                progressBar.classList.remove('progress-bar-animated');
            }
        };
    </script>
    '''
    return get_base_html("Login", content)


def get_chat_html() -> str:
    """Chat page HTML"""
    content = '''
    <div class="container-fluid">
        <div class="row">
            <!-- Sidebar -->
            <div class="col-md-3 col-lg-2 sidebar">
                <div class="d-flex align-items-center mb-4">
                    <i class="bi bi-diagram-3 text-primary me-2" style="font-size: 1.5rem;"></i>
                    <span class="h5 mb-0">Project KG</span>
                </div>

                <nav class="nav flex-column">
                    <a class="nav-link active" href="/chat">
                        <i class="bi bi-chat-dots me-2"></i>Chat
                    </a>
                    <a class="nav-link" href="/graph">
                        <i class="bi bi-diagram-2 me-2"></i>Knowledge Graph
                    </a>
                    <a class="nav-link" href="/dashboard">
                        <i class="bi bi-speedometer2 me-2"></i>Dashboard
                    </a>
                    <a class="nav-link" href="/simulation">
                        <i class="bi bi-lightning me-2"></i>Simulation
                    </a>
                </nav>

                <hr class="my-4">

                <div id="user-info" class="mb-3">
                    <!-- User info loaded dynamically -->
                </div>

                <button class="btn btn-outline-danger w-100" onclick="logout()">
                    <i class="bi bi-box-arrow-right me-2"></i>Logout
                </button>
            </div>

            <!-- Main Content -->
            <div class="col-md-9 col-lg-10 p-4">
                <div class="card h-100 d-flex flex-column">
                    <div class="card-header d-flex justify-content-between align-items-center py-3">
                        <div class="d-flex align-items-center">
                            <div class="bg-primary rounded-circle p-2 me-3">
                                <i class="bi bi-robot text-white" style="font-size: 1.25rem;"></i>
                            </div>
                            <div>
                                <h5 class="mb-0">Project Assistant</h5>
                                <small class="text-secondary">AI-powered project insights</small>
                            </div>
                        </div>
                        <button class="btn btn-outline-secondary btn-sm" onclick="clearChat()">
                            <i class="bi bi-arrow-counterclockwise me-1"></i>New Chat
                        </button>
                    </div>
                    <div class="card-body chat-container flex-grow-1" id="chat-messages">
                        <div class="message message-assistant">
                            <div class="message-header">
                                <i class="bi bi-robot me-1"></i> Assistant
                            </div>
                            <div>
                                Hello! I'm your AI assistant for the <strong>ABC Inc. SAP S/4HANA Migration</strong> project.
                                I can help you explore project data, analyze trends, and understand risks.
                            </div>
                            <div class="mt-3">
                                <strong>Try asking:</strong>
                                <ul class="mt-2">
                                    <li>What is the current project status?</li>
                                    <li>How has velocity changed over time?</li>
                                    <li>What risks should we watch for?</li>
                                    <li>Who left the project and why?</li>
                                </ul>
                            </div>
                        </div>
                    </div>
                    <div class="card-footer py-3">
                        <div class="chat-input-container d-flex align-items-center">
                            <input type="text" id="chat-input" class="form-control chat-input flex-grow-1"
                                   placeholder="Ask about the project..." onkeypress="handleKeyPress(event)">
                            <button class="btn btn-primary rounded-circle ms-2" onclick="sendMessage()" style="width: 44px; height: 44px;">
                                <i class="bi bi-send-fill"></i>
                            </button>
                        </div>
                        <div id="suggestions" class="mt-3">
                            <!-- Follow-up suggestions -->
                        </div>
                    </div>
                </div>
            </div>
        </div>
    </div>

    <script>
        const sessionId = localStorage.getItem('session_id');
        const user = JSON.parse(localStorage.getItem('user') || '{}');

        if (!sessionId) {
            window.location.href = '/login';
        }

        // Get user display info with fallbacks
        const userName = user.display_name || user.username || 'User';
        const userRole = user.role_display || user.role || 'Team Member';
        const userColor = user.color || '#6c757d';
        const userIcon = user.icon || 'person-circle';

        // Display user info with improved styling
        document.getElementById('user-info').innerHTML = `
            <div class="user-panel">
                <div class="d-flex align-items-center">
                    <div class="user-avatar" style="background-color: ${userColor}30; color: ${userColor}">
                        <i class="bi bi-${userIcon}"></i>
                    </div>
                    <div>
                        <div class="user-name">${userName}</div>
                        <div class="user-role" style="color: ${userColor}">${userRole}</div>
                    </div>
                </div>
            </div>
        `;

        function handleKeyPress(e) {
            if (e.key === 'Enter') sendMessage();
        }

        async function sendMessage() {
            const input = document.getElementById('chat-input');
            const message = input.value.trim();
            if (!message) return;

            // Add user message
            addMessage(message, 'user');
            input.value = '';

            // Send to API
            try {
                const response = await fetch('/api/chat/message', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({message: message, session_id: sessionId})
                });

                if (response.status === 401) {
                    window.location.href = '/login';
                    return;
                }

                const data = await response.json();
                addMessage(data.answer, 'assistant');

                // Show follow-up suggestions
                if (data.follow_up_questions && data.follow_up_questions.length > 0) {
                    const suggestions = document.getElementById('suggestions');
                    suggestions.innerHTML = '<small class="text-secondary me-2"><i class="bi bi-lightbulb me-1"></i>Suggested:</small>' +
                        data.follow_up_questions.map(q =>
                            `<button class="btn suggestion-btn btn-sm me-2 mb-1" onclick="askQuestion('${q.replace(/'/g, "\\'")}')">${q}</button>`
                        ).join('');
                } else {
                    document.getElementById('suggestions').innerHTML = '';
                }
            } catch (error) {
                addMessage('Error: ' + error.message, 'assistant');
            }
        }

        function addMessage(text, role) {
            const container = document.getElementById('chat-messages');
            const div = document.createElement('div');
            div.className = `message message-${role}`;

            const icon = role === 'user' ? 'person-fill' : 'robot';
            const label = role === 'user' ? 'You' : 'Assistant';

            div.innerHTML = `
                <div class="message-header">
                    <i class="bi bi-${icon} me-1"></i> ${label}
                </div>
                <div>${formatMessage(text)}</div>
            `;
            container.appendChild(div);
            container.scrollTop = container.scrollHeight;
        }

        function formatMessage(text) {
            if (!text) return '';

            // Convert markdown-like formatting
            let formatted = text
                // Bold text
                .replace(/\\*\\*(.+?)\\*\\*/g, '<strong>$1</strong>')
                // Headers
                .replace(/^### (.+)$/gm, '<h6 class="mt-3 mb-2">$1</h6>')
                .replace(/^## (.+)$/gm, '<h5 class="mt-3 mb-2">$1</h5>')
                // Newlines
                .replace(/\\n/g, '<br>')
                .replace(/\\n/g, '<br>')
                // Lists - wrap in ul
                .replace(/(<br>)?- (.+?)(<br>|$)/g, '<li>$2</li>');

            // Wrap consecutive list items in ul
            formatted = formatted.replace(/(<li>.*<\\/li>)+/g, '<ul class="mb-2">$&</ul>');

            return formatted;
        }

        function askQuestion(q) {
            document.getElementById('chat-input').value = q;
            sendMessage();
        }

        async function clearChat() {
            await fetch(`/api/chat/clear/${sessionId}`, {method: 'POST'});
            const container = document.getElementById('chat-messages');
            container.innerHTML = `
                <div class="message message-assistant">
                    <div class="message-header">
                        <i class="bi bi-robot me-1"></i> Assistant
                    </div>
                    <div>Chat cleared. How can I help you with the project?</div>
                </div>
            `;
        }

        function logout() {
            fetch(`/api/auth/logout?session_id=${sessionId}`, {method: 'POST'});
            localStorage.clear();
            window.location.href = '/login';
        }
    </script>
    '''
    return get_base_html("Chat", content)


def get_graph_html() -> str:
    """Knowledge Graph visualization page"""
    content = '''
    <div class="container-fluid">
        <div class="row">
            <!-- Sidebar (same as chat) -->
            <div class="col-md-3 col-lg-2 sidebar">
                <div class="d-flex align-items-center mb-4">
                    <i class="bi bi-diagram-3 text-primary me-2" style="font-size: 1.5rem;"></i>
                    <span class="h5 mb-0">Project KG</span>
                </div>
                <nav class="nav flex-column">
                    <a class="nav-link" href="/chat"><i class="bi bi-chat-dots me-2"></i>Chat</a>
                    <a class="nav-link active" href="/graph"><i class="bi bi-diagram-2 me-2"></i>Knowledge Graph</a>
                    <a class="nav-link" href="/dashboard"><i class="bi bi-speedometer2 me-2"></i>Dashboard</a>
                    <a class="nav-link" href="/simulation"><i class="bi bi-lightning me-2"></i>Simulation</a>
                </nav>
                <hr class="my-4">
                <div id="user-info"></div>
                <button class="btn btn-outline-danger w-100 mt-3" onclick="logout()">
                    <i class="bi bi-box-arrow-right me-2"></i>Logout
                </button>
            </div>

            <!-- Main Content -->
            <div class="col-md-9 col-lg-10 p-4">
                <div class="row mb-4">
                    <div class="col-md-4">
                        <div class="card p-3">
                            <h6><i class="bi bi-calendar3 me-2"></i>Time Navigation</h6>
                            <input type="range" id="time-slider" class="form-range" min="0" max="12" value="12">
                            <div class="d-flex justify-content-between">
                                <small>Dec 2025</small>
                                <span id="current-date" class="badge bg-primary">Mar 2026</span>
                                <small>Apr 2026</small>
                            </div>
                        </div>
                    </div>
                    <div class="col-md-4">
                        <div class="card p-3">
                            <h6><i class="bi bi-funnel me-2"></i>Filter Entities</h6>
                            <select id="entity-filter" class="form-select bg-dark text-light border-secondary" multiple>
                                <option value="Person" selected>People</option>
                                <option value="Meeting" selected>Meetings</option>
                                <option value="Risk" selected>Risks</option>
                                <option value="ChangeRequest" selected>Change Requests</option>
                                <option value="Task">Tasks</option>
                            </select>
                        </div>
                    </div>
                    <div class="col-md-4">
                        <div class="card p-3">
                            <h6><i class="bi bi-graph-up me-2"></i>Statistics</h6>
                            <div id="stats-display">
                                <span class="badge bg-info me-1">Nodes: --</span>
                                <span class="badge bg-success me-1">Edges: --</span>
                            </div>
                        </div>
                    </div>
                </div>

                <div class="card">
                    <div class="card-header">
                        <h5 class="mb-0"><i class="bi bi-diagram-2 me-2"></i>Knowledge Graph Visualization</h5>
                    </div>
                    <div class="card-body">
                        <div id="graph-container"></div>
                    </div>
                </div>

                <div class="row mt-4">
                    <div class="col-md-6">
                        <div class="card p-3">
                            <h6><i class="bi bi-clock-history me-2"></i>Entity Timeline</h6>
                            <div id="timeline-chart" style="height: 200px;"></div>
                        </div>
                    </div>
                    <div class="col-md-6">
                        <div class="card p-3">
                            <h6><i class="bi bi-pie-chart me-2"></i>Entity Distribution</h6>
                            <div id="distribution-chart" style="height: 200px;"></div>
                        </div>
                    </div>
                </div>
            </div>
        </div>
    </div>

    <script>
        const sessionId = localStorage.getItem('session_id');
        const user = JSON.parse(localStorage.getItem('user') || '{}');

        if (!sessionId) window.location.href = '/login';

        // Get user display info with fallbacks
        const userName = user.display_name || user.username || 'User';
        const userRole = user.role_display || user.role || 'Team Member';
        const userColor = user.color || '#6c757d';
        const userIcon = user.icon || 'person-circle';

        document.getElementById('user-info').innerHTML = `
            <div class="user-panel">
                <div class="d-flex align-items-center">
                    <div class="user-avatar" style="background-color: ${userColor}30; color: ${userColor}">
                        <i class="bi bi-${userIcon}"></i>
                    </div>
                    <div>
                        <div class="user-name">${userName}</div>
                        <div class="user-role" style="color: ${userColor}">${userRole}</div>
                    </div>
                </div>
            </div>
        `;

        // Initialize graph
        let graphData = {nodes: [], links: []};
        const width = document.getElementById('graph-container').clientWidth;
        const height = 600;

        const svg = d3.select('#graph-container')
            .append('svg')
            .attr('width', width)
            .attr('height', height);

        const simulation = d3.forceSimulation()
            .force('link', d3.forceLink().id(d => d.id).distance(100))
            .force('charge', d3.forceManyBody().strength(-200))
            .force('center', d3.forceCenter(width / 2, height / 2));

        // Color scale for entity types
        const colorScale = d3.scaleOrdinal()
            .domain(['Person', 'Meeting', 'Risk', 'ChangeRequest', 'Task', 'Stream', 'Defect'])
            .range(['#4f46e5', '#22c55e', '#ef4444', '#f59e0b', '#06b6d4', '#8b5cf6', '#ec4899']);

        async function loadGraphData() {
            const response = await fetch(`/api/graph/statistics?session_id=${sessionId}`);
            const stats = await response.json();

            document.getElementById('stats-display').innerHTML = `
                <span class="badge bg-info me-1">Nodes: ${stats.node_count}</span>
                <span class="badge bg-success me-1">Edges: ${stats.edge_count}</span>
            `;

            // Load entities by type
            const selectedTypes = Array.from(document.getElementById('entity-filter').selectedOptions)
                .map(o => o.value);

            graphData.nodes = [];
            graphData.links = [];

            for (const type of selectedTypes) {
                try {
                    const resp = await fetch(`/api/graph/entities/${type}?session_id=${sessionId}`);
                    const data = await resp.json();

                    data.entities.forEach(e => {
                        graphData.nodes.push({
                            id: e.id,
                            name: e.name || e.id,
                            type: type,
                            ...e
                        });
                    });
                } catch (err) {
                    console.log(`Cannot access ${type}`);
                }
            }

            // Generate some links (simplified)
            graphData.nodes.forEach((node, i) => {
                if (i > 0 && Math.random() > 0.7) {
                    graphData.links.push({
                        source: graphData.nodes[Math.floor(Math.random() * i)].id,
                        target: node.id
                    });
                }
            });

            updateGraph();
            updateCharts(stats);
        }

        function updateGraph() {
            svg.selectAll('*').remove();

            const link = svg.append('g')
                .selectAll('line')
                .data(graphData.links)
                .join('line')
                .attr('stroke', '#666')
                .attr('stroke-opacity', 0.6);

            const node = svg.append('g')
                .selectAll('circle')
                .data(graphData.nodes)
                .join('circle')
                .attr('r', 10)
                .attr('fill', d => colorScale(d.type))
                .call(drag(simulation));

            const label = svg.append('g')
                .selectAll('text')
                .data(graphData.nodes)
                .join('text')
                .text(d => d.name || d.id.split('_').pop())
                .attr('font-size', 10)
                .attr('fill', '#fff')
                .attr('dx', 12);

            node.append('title')
                .text(d => `${d.type}: ${d.name || d.id}`);

            simulation.nodes(graphData.nodes)
                .on('tick', () => {
                    link
                        .attr('x1', d => d.source.x)
                        .attr('y1', d => d.source.y)
                        .attr('x2', d => d.target.x)
                        .attr('y2', d => d.target.y);
                    node
                        .attr('cx', d => d.x)
                        .attr('cy', d => d.y);
                    label
                        .attr('x', d => d.x)
                        .attr('y', d => d.y);
                });

            simulation.force('link').links(graphData.links);
            simulation.alpha(1).restart();
        }

        function drag(simulation) {
            return d3.drag()
                .on('start', (event, d) => {
                    if (!event.active) simulation.alphaTarget(0.3).restart();
                    d.fx = d.x;
                    d.fy = d.y;
                })
                .on('drag', (event, d) => {
                    d.fx = event.x;
                    d.fy = event.y;
                })
                .on('end', (event, d) => {
                    if (!event.active) simulation.alphaTarget(0);
                    d.fx = null;
                    d.fy = null;
                });
        }

        function updateCharts(stats) {
            // Distribution pie chart
            const entityTypes = stats.entity_types || {};
            Plotly.newPlot('distribution-chart', [{
                values: Object.values(entityTypes),
                labels: Object.keys(entityTypes),
                type: 'pie',
                marker: {colors: Object.keys(entityTypes).map(t => colorScale(t))}
            }], {
                paper_bgcolor: 'transparent',
                font: {color: '#e4e4e7'},
                margin: {t: 10, b: 10, l: 10, r: 10},
                showlegend: true,
                legend: {orientation: 'h', y: -0.1}
            });
        }

        // Event listeners
        document.getElementById('entity-filter').onchange = loadGraphData;
        document.getElementById('time-slider').oninput = function() {
            const weeks = ['Dec W1', 'Dec W2', 'Dec W3', 'Dec W4', 'Jan W1', 'Jan W2', 'Jan W3', 'Jan W4', 'Feb W1', 'Feb W2', 'Feb W3', 'Feb W4', 'Mar W1'];
            document.getElementById('current-date').textContent = weeks[this.value];
            loadGraphData();
        };

        function logout() {
            localStorage.clear();
            window.location.href = '/login';
        }

        // Initial load
        loadGraphData();
    </script>
    '''
    return get_base_html("Knowledge Graph", content)


def get_dashboard_html() -> str:
    """Dashboard page HTML"""
    content = '''
    <div class="container-fluid">
        <div class="row">
            <!-- Sidebar -->
            <div class="col-md-3 col-lg-2 sidebar">
                <div class="d-flex align-items-center mb-4">
                    <i class="bi bi-diagram-3 text-primary me-2" style="font-size: 1.5rem;"></i>
                    <span class="h5 mb-0">Project KG</span>
                </div>
                <nav class="nav flex-column">
                    <a class="nav-link" href="/chat"><i class="bi bi-chat-dots me-2"></i>Chat</a>
                    <a class="nav-link" href="/graph"><i class="bi bi-diagram-2 me-2"></i>Knowledge Graph</a>
                    <a class="nav-link active" href="/dashboard"><i class="bi bi-speedometer2 me-2"></i>Dashboard</a>
                    <a class="nav-link" href="/simulation"><i class="bi bi-lightning me-2"></i>Simulation</a>
                </nav>
                <hr class="my-4">
                <div id="user-info"></div>
                <button class="btn btn-outline-danger w-100 mt-3" onclick="logout()">Logout</button>
            </div>

            <!-- Main Content -->
            <div class="col-md-9 col-lg-10 p-4">
                <h4 class="mb-4"><i class="bi bi-speedometer2 me-2"></i>Project Dashboard</h4>

                <!-- KPI Cards -->
                <div class="row mb-4">
                    <div class="col-md-3">
                        <div class="card p-3 text-center">
                            <i class="bi bi-people text-primary" style="font-size: 2rem;"></i>
                            <h3 id="team-size">--</h3>
                            <small class="text-secondary">Team Size</small>
                        </div>
                    </div>
                    <div class="col-md-3">
                        <div class="card p-3 text-center">
                            <i class="bi bi-exclamation-triangle text-warning" style="font-size: 2rem;"></i>
                            <h3 id="open-risks">--</h3>
                            <small class="text-secondary">Open Risks</small>
                        </div>
                    </div>
                    <div class="col-md-3">
                        <div class="card p-3 text-center">
                            <i class="bi bi-bug text-danger" style="font-size: 2rem;"></i>
                            <h3 id="open-defects">--</h3>
                            <small class="text-secondary">Open Defects</small>
                        </div>
                    </div>
                    <div class="col-md-3">
                        <div class="card p-3 text-center">
                            <i class="bi bi-file-earmark-plus text-info" style="font-size: 2rem;"></i>
                            <h3 id="change-requests">--</h3>
                            <small class="text-secondary">Change Requests</small>
                        </div>
                    </div>
                </div>

                <!-- Charts Row -->
                <div class="row mb-4">
                    <div class="col-md-8">
                        <div class="card p-3">
                            <h6><i class="bi bi-graph-up me-2"></i>Velocity Trend</h6>
                            <div id="velocity-chart" style="height: 300px;"></div>
                        </div>
                    </div>
                    <div class="col-md-4">
                        <div class="card p-3">
                            <h6><i class="bi bi-bullseye me-2"></i>Stream Status</h6>
                            <div id="stream-status" class="mt-3">
                                <div class="mb-3">
                                    <div class="d-flex justify-content-between">
                                        <span>Stream 1 (SD)</span>
                                        <span class="badge bg-success" id="sd-status">Green</span>
                                    </div>
                                    <div class="progress mt-2" style="height: 10px;">
                                        <div class="progress-bar bg-success" id="sd-progress" style="width: 92%"></div>
                                    </div>
                                </div>
                                <div class="mb-3">
                                    <div class="d-flex justify-content-between">
                                        <span>Stream 2 (EWM)</span>
                                        <span class="badge bg-warning" id="ewm-status">Amber</span>
                                    </div>
                                    <div class="progress mt-2" style="height: 10px;">
                                        <div class="progress-bar bg-warning" id="ewm-progress" style="width: 68%"></div>
                                    </div>
                                </div>
                            </div>
                        </div>
                    </div>
                </div>

                <!-- Forecast Section -->
                <div class="row">
                    <div class="col-md-6">
                        <div class="card p-3">
                            <h6><i class="bi bi-calendar-check me-2"></i>Milestone Forecast</h6>
                            <div id="milestones">Loading...</div>
                        </div>
                    </div>
                    <div class="col-md-6">
                        <div class="card p-3">
                            <h6><i class="bi bi-shield-exclamation me-2"></i>Risk Outlook</h6>
                            <div id="risks">Loading...</div>
                        </div>
                    </div>
                </div>
            </div>
        </div>
    </div>

    <script>
        const sessionId = localStorage.getItem('session_id');
        const user = JSON.parse(localStorage.getItem('user') || '{}');

        if (!sessionId) window.location.href = '/login';

        // Get user display info with fallbacks
        const userName = user.display_name || user.username || 'User';
        const userRole = user.role_display || user.role || 'Team Member';
        const userColor = user.color || '#6c757d';
        const userIcon = user.icon || 'person-circle';

        document.getElementById('user-info').innerHTML = `
            <div class="user-panel">
                <div class="d-flex align-items-center">
                    <div class="user-avatar" style="background-color: ${userColor}30; color: ${userColor}">
                        <i class="bi bi-${userIcon}"></i>
                    </div>
                    <div>
                        <div class="user-name">${userName}</div>
                        <div class="user-role" style="color: ${userColor}">${userRole}</div>
                    </div>
                </div>
            </div>
        `;

        async function loadDashboard() {
            // Load forecast
            try {
                const forecast = await fetch(`/api/simulation/forecast?session_id=${sessionId}`, {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({horizon_days: 45})
                }).then(r => r.json());

                // Display milestones
                let milestonesHtml = '';
                forecast.milestone_forecasts?.forEach(m => {
                    const prob = Math.round(m.probability_on_time * 100);
                    const color = prob > 90 ? 'success' : prob > 70 ? 'warning' : 'danger';
                    milestonesHtml += `
                        <div class="d-flex justify-content-between align-items-center mb-2">
                            <span>${m.name}</span>
                            <span class="badge bg-${color}">${prob}%</span>
                        </div>
                    `;
                });
                document.getElementById('milestones').innerHTML = milestonesHtml || 'No data';

                // Display risks
                let risksHtml = '';
                Object.entries(forecast.risk_outlook || {}).forEach(([risk, prob]) => {
                    const pct = Math.round(prob * 100);
                    const color = pct > 20 ? 'danger' : pct > 10 ? 'warning' : 'success';
                    risksHtml += `
                        <div class="d-flex justify-content-between align-items-center mb-2">
                            <span>${risk.replace(/_/g, ' ')}</span>
                            <span class="badge bg-${color}">${pct}%</span>
                        </div>
                    `;
                });
                document.getElementById('risks').innerHTML = risksHtml || 'No data';

            } catch (e) {
                console.log('Forecast not available');
            }

            // Velocity chart (sample data)
            Plotly.newPlot('velocity-chart', [{
                x: ['Dec W1', 'Dec W2', 'Dec W3', 'Dec W4', 'Jan W1', 'Jan W2', 'Jan W3', 'Jan W4', 'Feb W1', 'Feb W2', 'Feb W3', 'Feb W4'],
                y: [168, 172, 175, 178, 172, 165, 170, 175, 185, 195, 205, 212],
                type: 'scatter',
                mode: 'lines+markers',
                line: {color: '#4f46e5', width: 3},
                marker: {size: 8}
            }], {
                paper_bgcolor: 'transparent',
                plot_bgcolor: 'transparent',
                font: {color: '#e4e4e7'},
                margin: {t: 10, r: 10, l: 40, b: 30},
                xaxis: {gridcolor: '#3d3d4f'},
                yaxis: {gridcolor: '#3d3d4f', title: 'Story Points'}
            });

            // Update KPIs (sample)
            document.getElementById('team-size').textContent = '10';
            document.getElementById('open-risks').textContent = '5';
            document.getElementById('open-defects').textContent = '4';
            document.getElementById('change-requests').textContent = '3';
        }

        function logout() {
            localStorage.clear();
            window.location.href = '/login';
        }

        loadDashboard();
    </script>
    '''
    return get_base_html("Dashboard", content)


def get_simulation_html() -> str:
    """Simulation page HTML"""
    content = '''
    <div class="container-fluid">
        <div class="row">
            <!-- Sidebar -->
            <div class="col-md-3 col-lg-2 sidebar">
                <div class="d-flex align-items-center mb-4">
                    <i class="bi bi-diagram-3 text-primary me-2" style="font-size: 1.5rem;"></i>
                    <span class="h5 mb-0">Project KG</span>
                </div>
                <nav class="nav flex-column">
                    <a class="nav-link" href="/chat"><i class="bi bi-chat-dots me-2"></i>Chat</a>
                    <a class="nav-link" href="/graph"><i class="bi bi-diagram-2 me-2"></i>Knowledge Graph</a>
                    <a class="nav-link" href="/dashboard"><i class="bi bi-speedometer2 me-2"></i>Dashboard</a>
                    <a class="nav-link active" href="/simulation"><i class="bi bi-lightning me-2"></i>Simulation</a>
                </nav>
                <hr class="my-4">
                <div id="user-info"></div>
                <button class="btn btn-outline-danger w-100 mt-3" onclick="logout()">Logout</button>
            </div>

            <!-- Main Content -->
            <div class="col-md-9 col-lg-10 p-4">
                <h4 class="mb-4"><i class="bi bi-lightning me-2"></i>What-If Simulation</h4>

                <div class="row">
                    <!-- Scenario Selection -->
                    <div class="col-md-4">
                        <div class="card p-3 mb-4">
                            <h6><i class="bi bi-list-check me-2"></i>Select Scenario</h6>
                            <div id="scenario-list" class="list-group list-group-flush">
                                <!-- Scenarios loaded dynamically -->
                            </div>
                        </div>
                    </div>

                    <!-- Parameters -->
                    <div class="col-md-4">
                        <div class="card p-3 mb-4">
                            <h6><i class="bi bi-sliders me-2"></i>Parameters</h6>
                            <div id="parameter-form">
                                <p class="text-secondary">Select a scenario to configure parameters</p>
                            </div>
                            <button class="btn btn-primary mt-3" id="run-btn" disabled onclick="runSimulation()">
                                <i class="bi bi-play-fill me-2"></i>Run Simulation
                            </button>
                        </div>
                    </div>

                    <!-- Results -->
                    <div class="col-md-4">
                        <div class="card p-3 mb-4">
                            <h6><i class="bi bi-graph-up-arrow me-2"></i>Results</h6>
                            <div id="results">
                                <p class="text-secondary">Run a simulation to see results</p>
                            </div>
                        </div>
                    </div>
                </div>

                <!-- Impact Visualization -->
                <div class="card p-3">
                    <h6><i class="bi bi-bar-chart me-2"></i>Impact Analysis</h6>
                    <div id="impact-chart" style="height: 300px;"></div>
                </div>
            </div>
        </div>
    </div>

    <script>
        const sessionId = localStorage.getItem('session_id');
        const user = JSON.parse(localStorage.getItem('user') || '{}');
        let selectedScenario = null;

        if (!sessionId) window.location.href = '/login';

        // Get user display info with fallbacks
        const userName = user.display_name || user.username || 'User';
        const userRole = user.role_display || user.role || 'Team Member';
        const userColor = user.color || '#6c757d';
        const userIcon = user.icon || 'person-circle';

        document.getElementById('user-info').innerHTML = `
            <div class="user-panel">
                <div class="d-flex align-items-center">
                    <div class="user-avatar" style="background-color: ${userColor}30; color: ${userColor}">
                        <i class="bi bi-${userIcon}"></i>
                    </div>
                    <div>
                        <div class="user-name">${userName}</div>
                        <div class="user-role" style="color: ${userColor}">${userRole}</div>
                    </div>
                </div>
            </div>
        `;

        async function loadScenarios() {
            try {
                const response = await fetch(`/api/simulation/scenarios?session_id=${sessionId}`);
                const data = await response.json();

                const list = document.getElementById('scenario-list');
                list.innerHTML = '';

                data.scenarios.forEach(s => {
                    const item = document.createElement('a');
                    item.href = '#';
                    item.className = 'list-group-item list-group-item-action bg-transparent text-light';
                    item.innerHTML = `
                        <strong>${s.name}</strong>
                        <br><small class="text-secondary">${s.description}</small>
                    `;
                    item.onclick = (e) => {
                        e.preventDefault();
                        selectScenario(s.id);
                        list.querySelectorAll('a').forEach(a => a.classList.remove('active'));
                        item.classList.add('active');
                    };
                    list.appendChild(item);
                });
            } catch (e) {
                document.getElementById('scenario-list').innerHTML =
                    '<p class="text-warning">Simulation not available for your role</p>';
            }
        }

        async function selectScenario(scenarioId) {
            selectedScenario = scenarioId;

            const response = await fetch(`/api/simulation/scenario/${scenarioId}/parameters?session_id=${sessionId}`);
            const data = await response.json();

            let formHtml = '';
            Object.entries(data.parameters).forEach(([name, config]) => {
                if (config.options) {
                    formHtml += `
                        <div class="mb-3">
                            <label class="form-label">${name}</label>
                            <select class="form-select bg-dark text-light border-secondary" id="param-${name}">
                                ${config.options.map(o => `<option value="${o}">${o}</option>`).join('')}
                            </select>
                        </div>
                    `;
                } else if (config.min !== undefined) {
                    formHtml += `
                        <div class="mb-3">
                            <label class="form-label">${name}: <span id="val-${name}">${config.default || config.min}</span></label>
                            <input type="range" class="form-range" id="param-${name}"
                                   min="${config.min}" max="${config.max}" value="${config.default || config.min}"
                                   oninput="document.getElementById('val-${name}').textContent = this.value">
                        </div>
                    `;
                }
            });

            document.getElementById('parameter-form').innerHTML = formHtml;
            document.getElementById('run-btn').disabled = false;
        }

        async function runSimulation() {
            const params = {};
            document.querySelectorAll('[id^="param-"]').forEach(el => {
                const name = el.id.replace('param-', '');
                params[name] = el.type === 'range' ? parseInt(el.value) : el.value;
            });

            try {
                const response = await fetch(`/api/simulation/run?session_id=${sessionId}`, {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({scenario_id: selectedScenario, parameters: params})
                });

                const result = await response.json();

                // Display results
                let resultsHtml = `
                    <div class="alert ${result.probability > 0.5 ? 'alert-warning' : 'alert-info'}">
                        <strong>Probability:</strong> ${Math.round(result.probability * 100)}%
                    </div>
                    <p><strong>Impact:</strong> ${result.impact_assessment}</p>
                    <hr>
                    <strong>Outcomes:</strong>
                    <ul class="mb-3">
                `;

                Object.entries(result.outcomes).forEach(([k, v]) => {
                    if (typeof v === 'number') {
                        resultsHtml += `<li>${k}: ${v.toLocaleString()}</li>`;
                    }
                });

                resultsHtml += `</ul><strong>Recommendations:</strong><ul>`;
                result.recommendations?.forEach(r => {
                    resultsHtml += `<li>${r}</li>`;
                });
                resultsHtml += `</ul>`;

                document.getElementById('results').innerHTML = resultsHtml;

                // Update chart
                const outcomes = result.outcomes;
                Plotly.newPlot('impact-chart', [{
                    x: Object.keys(outcomes).filter(k => typeof outcomes[k] === 'number'),
                    y: Object.values(outcomes).filter(v => typeof v === 'number'),
                    type: 'bar',
                    marker: {color: '#4f46e5'}
                }], {
                    paper_bgcolor: 'transparent',
                    plot_bgcolor: 'transparent',
                    font: {color: '#e4e4e7'},
                    margin: {t: 10, r: 10, l: 50, b: 80},
                    xaxis: {gridcolor: '#3d3d4f', tickangle: 45},
                    yaxis: {gridcolor: '#3d3d4f'}
                });

            } catch (e) {
                document.getElementById('results').innerHTML =
                    `<p class="text-danger">Error: ${e.message}</p>`;
            }
        }

        function logout() {
            localStorage.clear();
            window.location.href = '/login';
        }

        loadScenarios();
    </script>
    '''
    return get_base_html("Simulation", content)


# ============================================================================
# Main Entry Point
# ============================================================================

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8888)
