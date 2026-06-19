#!/usr/bin/env bash
set -e

ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"

echo "=============================="
echo "  HealthBridge Platform"
echo "  Starting services..."
echo "=============================="
echo ""

# Start backend
echo "[1/2] Starting FastAPI backend (port 8080)..."
cd "$ROOT_DIR/backend" && ./venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8080 --reload &
BACKEND_PID=$!

# Give backend a moment
sleep 3

# Start frontend
echo "[2/2] Starting React frontend (port 3001)..."
cd "$ROOT_DIR/frontend" && npm run dev &
FRONTEND_PID=$!

sleep 2

echo ""
echo "=============================="
echo "  ✔ Backend:  http://localhost:8080"
echo "  ✔ Frontend: http://localhost:3001"
echo "  ✔ Swagger:  http://localhost:3001/docs"
echo "=============================="
echo "  Press Ctrl+C to stop all services"
echo "=============================="

cleanup() {
    echo ""
    echo "Shutting down..."
    kill $BACKEND_PID $FRONTEND_PID 2>/dev/null
    wait $BACKEND_PID $FRONTEND_PID 2>/dev/null
    echo "All services stopped."
    exit 0
}

trap cleanup SIGINT SIGTERM
wait
