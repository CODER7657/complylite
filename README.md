# ComplyLite - Compliance Surveillance Co-pilot

## Quick Start

### Windows (PowerShell)
```powershell
# Clone and run the project
git clone https://github.com/CODER7657/complylite.git
cd complylite

# Create & activate venv (first time only)
py -3 -m venv .venv
.\.venv\Scripts\Activate.ps1

# Install backend deps
pip install -r backend/requirements.txt

# Start both backend and frontend
start.bat
```

### macOS/Linux
```bash
git clone https://github.com/CODER7657/complylite.git
cd complylite
chmod +x run.sh
./run.sh
```

## Access
- Frontend: http://localhost:3000
- Backend API: http://localhost:8000
- API Docs: http://localhost:8000/docs

## Features
- CSV data upload (orders, trades, clients)
- Real-time compliance alert generation
- Self-trade and wash-trade detection
- Audit-ready reporting
- Role-based dashboard

## Demo Data
Sample CSV files are provided in the `sample_data/` directory for testing.

Upload via UI (Data Upload page) or API:
```bash
# Trades
curl -F "table_type=trades" -F "file=@sample_data/trades.csv" http://localhost:8000/api/v1/data/upload/csv
# Clients
curl -F "table_type=clients" -F "file=@sample_data/clients.csv" http://localhost:8000/api/v1/data/upload/csv
# Orders
curl -F "table_type=orders" -F "file=@sample_data/orders.csv" http://localhost:8000/api/v1/data/upload/csv
```

## Technology Stack
- **Frontend**: React + Ant Design, Recharts
- **Backend**: FastAPI (Python), DuckDB
- **Detection**: Hybrid rule-based + ML algorithms
- **Security**: JWT auth, audit logs, field masking

## Manual Run (advanced)
In one terminal (backend):
```powershell
.\.venv\Scripts\Activate.ps1; uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 8000 --reload
```
In another terminal (frontend):
```powershell
cd frontend; npm install; npm start
```
