# Delivery Brain

A Knowledge Graph-based Project Intelligence System with Role-Based Access Control for the ABC Inc. SAP S/4HANA Migration project.

## Features

- **Temporal Knowledge Graph**: 349 nodes, 471 edges with 26 temporal snapshots for time-travel queries
- **Natural Language Chat**: Ask questions about project status, risks, team, and metrics
- **Lite RAG Engine**: TF-IDF based retrieval for ad-hoc queries (41 documents, 1055 chunks)
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
│   ├── rag/           # Lite RAG engine (TF-IDF retrieval)
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

### Quick Start

| Platform | Start | Stop | Status |
|----------|-------|------|--------|
| Windows | `scripts\start_server.bat` | `scripts\stop_server.bat` | `scripts\status.bat` |
| Unix/Mac | `./scripts/start_server.sh` | `./scripts/stop_server.sh` | `./scripts/status.sh` |

### Server Details

- **Default Port:** 8888
- **Host:** 127.0.0.1 (localhost only)
- **Startup Time:** ~30 seconds (initializes knowledge graph and RAG engine)

### Windows (Command Prompt)

```batch
cd project-kg-chatbot

REM Start server (default port 8888)
scripts\start_server.bat

REM Start on custom port
scripts\start_server.bat 9000

REM Check server status
scripts\status.bat

REM Stop server
scripts\stop_server.bat
```

### Unix/Mac (Terminal)

```bash
cd project-kg-chatbot

# Make executable (one time)
chmod +x scripts/*.sh

# Start server
./scripts/start_server.sh

# Start on custom port
./scripts/start_server.sh 9000

# Check server status
./scripts/status.sh

# Stop server
./scripts/stop_server.sh
```

### Manual Start (Any Platform)

```bash
cd project-kg-chatbot

# Start the FastAPI server
python -m uvicorn app:app --host 127.0.0.1 --port 8888

# Server will display:
# INFO:     Uvicorn running on http://127.0.0.1:8888

# Stop: Press Ctrl+C in the terminal
```

### Verify Server is Running

```bash
# Check if port 8888 is listening
# Windows:
netstat -ano | findstr :8888

# Unix/Mac:
lsof -i :8888
```

## Demo Accounts

| Role | Username | Password | Access Level |
|------|----------|----------|--------------|
| QA Director | roshan | Acc1234$$ | Full access to all data |
| Delivery Lead | krutika | Acc1234$$ | Full access to all data |
| Onsite Coordinator | tara | Acc1234$$ | Scrum, quality, productivity, CRs |
| Financial Auditor | rick | Acc1234$$ | Financial data only |

**Note:** On the login page, select a role from the dropdown and enter the password above.

## Pages

- `/login` - Authentication page
- `/chat` - Natural language chat interface
- `/graph` - Knowledge Graph visualization with time slider
- `/dashboard` - Project metrics and status
- `/simulation` - What-if scenario simulator

## Example Chat Queries

**Structured Queries (Knowledge Graph):**
- "What is the project status?"
- "What are the main risks?"
- "Who left the project?"
- "How is Stream 2 doing?"

**Ad-hoc Queries (RAG):**
- "How were Stream 2 risks mitigated?"
- "Why did Mousumi leave and what was the impact?"
- "What is the voice picking feature and who is working on it?"
- "Compare quality metrics between December and February"

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

## Troubleshooting

### Port Already in Use

```bash
# Windows - Find and kill process on port 8888
netstat -ano | findstr :8888
taskkill /F /PID <PID_NUMBER>

# Unix/Mac
lsof -i :8888
kill -9 <PID_NUMBER>

# Or use a different port
scripts\start_server.bat 9000
```

### Server Won't Start

1. Ensure Python 3.10+ is installed: `python --version`
2. Ensure dependencies are installed: `pip install -r requirements-minimal.txt`
3. Ensure you're in the project directory: `cd project-kg-chatbot`
4. Check for error messages in the terminal output

### Cannot Access Pages

1. Wait for server initialization (~30 seconds)
2. Look for "Application startup complete" in terminal
3. Ensure you're using `http://` not `https://`
4. Try `http://127.0.0.1:8888` instead of `localhost:8888`

## License

MIT License
