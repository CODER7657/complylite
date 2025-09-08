# ComplyLite - Compliance Surveillance Co-pilot

## Quick Start
```bash
# Clone and run the project
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
Sample CSV files are provided in the `data/` directory for testing.

## Technology Stack
- **Frontend**: React + Ant Design, Recharts
- **Backend**: FastAPI (Python), DuckDB
- **Detection**: Hybrid rule-based + ML algorithms
- **Security**: JWT auth, audit logs, field masking
