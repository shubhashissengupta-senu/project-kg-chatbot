#!/bin/bash
# Check Project KG Chatbot Server Status
# Usage: ./status.sh [port]

PORT=${1:-8888}

echo "========================================"
echo "  Project KG Chatbot - Server Status"
echo "========================================"
echo

# Check if port is listening
PID=$(lsof -ti :$PORT 2>/dev/null)

if [ -n "$PID" ]; then
    echo "Status: RUNNING"
    echo
    echo "Server Details:"
    echo "  Port: $PORT"
    echo "  PID: $PID"
    echo
    echo "Testing endpoint..."
    HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:$PORT/login 2>/dev/null)
    echo "  HTTP Response: $HTTP_CODE"
    echo
    echo "Open in browser: http://127.0.0.1:$PORT/login"
else
    echo "Status: STOPPED"
    echo
    echo "Run ./start_server.sh to start the server."
fi

echo
echo "========================================"
