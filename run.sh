#!/bin/bash
echo "Setting up ComplyLite..."

# Install backend dependencies  
cd backend
pip install -r requirements.txt
cd ..

# Install frontend dependencies
cd frontend  
npm install
cd ..

# Generate sample data
python scripts/generate_sample_data.py

# Setup database
python scripts/setup_database.py

echo "Starting services..."

# Start backend
cd backend
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload &
BACKEND_PID=$!
cd ..

# Start frontend
cd frontend
npm start &
FRONTEND_PID=$!
cd ..

echo "ComplyLite is running!"
echo "Frontend: http://localhost:3000"
echo "Backend: http://localhost:8000" 
echo "Press Ctrl+C to stop all services"

# Wait for Ctrl+C
trap "kill $BACKEND_PID $FRONTEND_PID; exit" INT
wait
