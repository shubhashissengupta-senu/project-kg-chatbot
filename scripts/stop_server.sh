#!/bin/bash
# Delivery Brain - Stop Server Script (Unix/Mac)
# Usage: ./stop_server.sh [port]
# Default port: 8888

PORT=${1:-8888}

echo "========================================"
echo "  Delivery Brain - Stop Server"
echo "========================================"
echo ""

# Find and kill process on the port
PID=$(lsof -t -i :$PORT 2>/dev/null)

if [ -n "$PID" ]; then
    echo "Stopping process $PID on port $PORT..."
    kill -9 $PID 2>/dev/null
    if [ $? -eq 0 ]; then
        echo "Server stopped successfully."
    else
        echo "Failed to stop process $PID"
    fi
else
    echo "No server found running on port $PORT."
fi
