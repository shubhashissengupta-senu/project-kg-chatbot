#!/bin/bash
# Delivery Brain - Start Server Script (Unix/Mac)
# Usage: ./start_server.sh [port]
# Default port: 8888

PORT=${1:-8888}

echo "========================================"
echo "  Delivery Brain Server"
echo "========================================"
echo ""
echo "Starting server on port $PORT..."
echo ""

cd "$(dirname "$0")/.."

# Check if port is in use
if lsof -i :$PORT > /dev/null 2>&1; then
    echo "ERROR: Port $PORT is already in use!"
    echo "Run ./stop_server.sh first or use a different port."
    exit 1
fi

# Start the server
echo "Server starting... (this takes ~30 seconds for initialization)"
echo ""
python -m uvicorn app:app --host 127.0.0.1 --port $PORT
