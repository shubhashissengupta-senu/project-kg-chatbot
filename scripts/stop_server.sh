#!/bin/bash
# Stop Project KG Chatbot Server
# Usage: ./stop_server.sh [port]

PORT=${1:-8888}

echo "========================================"
echo "  Project KG Chatbot - Stopping Server"
echo "========================================"
echo

# Find and kill process on the specified port
PID=$(lsof -ti :$PORT 2>/dev/null)

if [ -n "$PID" ]; then
    echo "Found server process: PID $PID"
    kill -9 $PID 2>/dev/null
    if [ $? -eq 0 ]; then
        echo "Server stopped successfully."
    else
        echo "Failed to stop process $PID"
    fi
else
    echo "No server found running on port $PORT."
fi

echo
