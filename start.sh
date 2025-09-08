#!/bin/bash
# ComplyLite Quick Start Script

echo "🚀 Starting ComplyLite Compliance Surveillance System..."

# Start backend
echo "📊 Starting Backend API..."
cd backend
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000 &
BACKEND_PID=$!

# Wait for backend to start
sleep 5

# Start frontend
echo "🎨 Starting Frontend..."
cd ../frontend
npm start &
FRONTEND_PID=$!

echo "✅ System Started Successfully!"
echo "📊 Backend API: http://localhost:8000"
echo "🎨 Frontend App: http://localhost:3000"
echo "📚 API Documentation: http://localhost:8000/docs"

# Keep running until interrupted
wait $BACKEND_PID $FRONTEND_PID
