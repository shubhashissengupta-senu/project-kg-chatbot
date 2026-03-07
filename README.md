# Project KG Chatbot

A Knowledge Graph-based Project Intelligence Chatbot with Role-Based Access Control for the ABC Inc. SAP S/4HANA Migration project.

## Features

- **Temporal Knowledge Graph**: 349 nodes, 471 edges with 26 temporal snapshots for time-travel queries
- **Natural Language Chat**: Ask questions about project status, risks, team, and metrics
- **Role-Based Access Control**: Four user roles with different permission levels
- **Interactive Visualizations**:
  - Knowledge Graph with D3.js (supports time travel)
  - Dashboard with Plotly charts
- **What-If Simulations**: Simulate scenarios like team departures, scope changes, budget pressure
- **Project Metrics**: 59 tracked metrics with trend analysis

## Architecture

```
project-kg-chatbot/
├── src/
│   ├── api/           # FastAPI routes
│   ├── auth/          # Role-based access control
│   ├── chatbot/       # Chat engine & query planner
│   ├── inference/     # Query engine & risk predictor
│   ├── ingestion/     # Document parsers
│   ├── knowledge_graph/  # Graph builder & storage
│   ├── simulation/    # Forecaster & scenario simulator
│   └── time_series/   # Metrics store & trend analyzer
├── ui/templates/      # HTML templates (Jinja2)
├── scripts/           # Server management scripts
├── config/            # Settings & ontology
└── tests/             # Unit tests
```

## Installation

```bash
# Clone the repository
git clone https://github.com/shubhashissengupta-senu/project-kg-chatbot.git
cd project-kg-chatbot

# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements-minimal.txt
```

## Running the Application

### Using Scripts (Recommended)

**Windows (Command Prompt):**
```batch
# Start server (default port 8888)
scripts\start_server.bat

# Start on custom port
scripts\start_server.bat 9000

# Check server status
scripts\status.bat

# Stop server
scripts\stop_server.bat
```

**Unix/Mac (Terminal):**
```bash
# Make executable (one time)
chmod +x scripts/*.sh

# Start server
./scripts/start_server.sh

# Check server status
./scripts/status.sh

# Stop server
./scripts/stop_server.sh
```

### Manual Start

```bash
# Start the FastAPI server
python -m uvicorn app:app --host 127.0.0.1 --port 8888

# Open in browser
# http://127.0.0.1:8888/login
```

## Demo Accounts

| Role | Username | Password | Access Level |
|------|----------|----------|--------------|
| QA Director | roshan | demo123 | Full access to all data |
| Delivery Lead | krutika | demo123 | Full access to all data |
| Onsite Lead | tara | demo123 | Scrum, quality, productivity, CRs |
| Auditor | rick | demo123 | Financial data only |

## Pages

- `/login` - Authentication page
- `/chat` - Natural language chat interface
- `/graph` - Knowledge Graph visualization with time slider
- `/dashboard` - Project metrics and status
- `/simulation` - What-if scenario simulator

## Example Chat Queries

- "What is the project status?"
- "What are the main risks?"
- "Who left the project?"
- "How is Stream 2 doing?"
- "What is the budget status?"
- "Compare quality metrics between December and February"
- "What happened when Mousumi left?"

## API Endpoints

### Authentication
- `POST /api/auth/login` - User login
- `POST /api/auth/logout` - User logout
- `GET /api/auth/roles` - Get available roles

### Chat
- `POST /api/chat/message` - Send chat message
- `GET /api/chat/examples` - Get example queries

### Knowledge Graph
- `GET /api/graph/data` - Get graph nodes and edges
- `GET /api/graph/statistics` - Get graph statistics
- `GET /api/graph/snapshots` - Get temporal snapshots

### Metrics
- `GET /api/metrics/list` - List available metrics
- `GET /api/metrics/series/{name}` - Get metric time series

### Simulation
- `POST /api/simulation/run` - Run what-if scenario
- `GET /api/simulation/scenarios` - List available scenarios

## Tech Stack

- **Backend**: FastAPI, Python 3.10+
- **Knowledge Graph**: NetworkX
- **Frontend**: Jinja2 templates, D3.js, Plotly
- **Data Processing**: Pandas, NumPy

## Data Source

The system ingests project data from markdown files including:
- Scrum meeting minutes (12 files)
- Client review meetings (3 files)
- QA review meetings (3 files)
- Finance reviews (3 files)
- Developer metrics (5 files)

## License

MIT License
