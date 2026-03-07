#!/bin/bash
# Start Project KG Chatbot Server
# Usage: ./start_server.sh [port]

PORT=${1:-8888}
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

echo "========================================"
echo "  Project KG Chatbot - Starting Server"
echo "========================================"
echo

cd "$PROJECT_DIR"

# Check if port is already in use
if lsof -i :$PORT >/dev/null 2>&1; then
    echo "ERROR: Port $PORT is already in use."
    echo "Run ./stop_server.sh first or use a different port."
    exit 1
fi

echo "Starting server on http://127.0.0.1:$PORT"
echo
echo "Demo Accounts:"
echo "  roshan / demo123   (QA Director)"
echo "  krutika / demo123  (Delivery Lead)"
echo "  tara / demo123     (Onsite Lead)"
echo "  rick / demo123     (Auditor)"
echo
echo "Press Ctrl+C to stop the server"
echo "========================================"
echo

python -m uvicorn app:app --host 127.0.0.1 --port $PORT
