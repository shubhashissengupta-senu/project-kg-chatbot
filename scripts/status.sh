#!/bin/bash
# Delivery Brain - Server Status Script (Unix/Mac)
# Usage: ./status.sh [port]
# Default port: 8888

PORT=${1:-8888}

echo "========================================"
echo "  Delivery Brain - Server Status"
echo "========================================"
echo ""

# Check if server is running
if lsof -i :$PORT > /dev/null 2>&1; then
    echo "Status: RUNNING"
    echo ""
    echo "Server Details:"
    lsof -i :$PORT
    echo ""
    echo "Access URLs:"
    echo "  Login:      http://127.0.0.1:$PORT/login"
    echo "  Dashboard:  http://127.0.0.1:$PORT/dashboard"
    echo "  Chat:       http://127.0.0.1:$PORT/chat"
    echo "  Graph:      http://127.0.0.1:$PORT/graph"
    echo "  Simulation: http://127.0.0.1:$PORT/simulation"
else
    echo "Status: STOPPED"
    echo ""
    echo "Run ./start_server.sh to start the server."
fi

echo ""
