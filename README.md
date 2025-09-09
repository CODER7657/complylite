# ComplyLite: Compliance Surveillance Co-pilot

**ComplyLite** is a lightweight, explainable compliance surveillance system for brokers—integrating rule-based and ML-based detection, CSV/SFTP ingestion, and instant audit-ready reporting.

---

## 🏗️ System Architecture

**Tech Stack:**
- **Frontend:** React 18, Ant Design, Recharts (dashboard and analytics)
- **Backend:** FastAPI (Python), DuckDB for high-performance analytics, Pandas for processing
- **Detection Engine:** Hybrid (rules + ML), easily configurable
- **Security:** JWT authentication, audit logs, field-level masking
- **Deployment:** Docker-based, cross-platform scripts (`run.sh`, `start.bat`)

---

## 🔧 Comprehensive Tech Stack Overview

### Frontend Stack
- **React 18** - Modern component-based UI framework
- **Ant Design** - Enterprise-class UI components for professional dashboards
- **Recharts** - Composable charting library for analytics visualizations
- **Axios** - HTTP client for API communications
- **React Router** - Client-side routing for single-page application navigation

### Backend Stack
- **FastAPI** - High-performance Python web framework with automatic API documentation
- **DuckDB** - Embedded analytical database optimized for OLAP queries
- **Pandas** - Data manipulation and analysis library for CSV processing
- **Pydantic** - Data validation using Python type annotations
- **SQLAlchemy** - Python SQL toolkit and Object-Relational Mapping
- **JWT (PyJWT)** - JSON Web Token implementation for secure authentication

### DevOps & CI Stack
- **Docker & Docker Compose** - Containerization and orchestration
- **GitHub Actions** - Continuous integration and deployment
- **pytest** - Python testing framework for backend unit tests
- **ESLint** - JavaScript/React code quality and consistency
- **Cross-platform scripts** - `run.sh` (Unix/Linux), `start.bat` (Windows)

### Key Technology Benefits
- **FastAPI**: Automatic OpenAPI/Swagger documentation, high performance with async support, type safety
- **DuckDB**: In-process analytical queries, excellent CSV ingestion, minimal setup overhead
- **Ant Design**: Enterprise-ready components, consistent design language, accessibility support
- **Docker**: Environment consistency, easy deployment, scalability across platforms

### Specialized Features
- **ML Compliance Engine**: Hybrid rule-based and machine learning detection algorithms
- **Real-time Alerts**: Instant notification system for compliance violations
- **CSV Processing Pipeline**: Robust data validation and ingestion workflows
- **JWT Security Layer**: Secure API access with token-based authentication
- **Comprehensive Audit Trail**: Full tracking and investigation history for regulatory compliance
- **Risk Scoring System**: Dynamic severity-ranked alerts (HIGH, MEDIUM, LOW)

### Scalability & Audit-Readiness
This technology stack is specifically designed to support **enterprise scalability** through DuckDB's analytical performance, Docker's container orchestration, and FastAPI's async capabilities. The architecture ensures **audit-readiness** with comprehensive logging, JWT-secured access controls, complete data lineage tracking, and immutable audit trails that meet regulatory compliance requirements for financial surveillance systems.

---

## 📂 Repo Structure

| Directory/File         | Purpose                                                            |
|-----------------------|--------------------------------------------------------------------|
| `.github/workflows`   | GitHub Actions CI config                                           |
| `backend/`            | FastAPI app, detection logic, DB models, API endpoints             |
|   • `app/`  | Main FastAPI components: api (routes), data, models, etc.          |
| `frontend/`           | React app: pages, dashboard, alerting UI                           |
| `sample_data/`        | Example CSVs (clients, trades, orders)                             |
| `scripts/`            | Utility scripts (sample data gen, DB setup)                        |
| `run.sh`, `start.bat` | Cross-platform launchers                                           |
| `docker-compose.yml`  | All-in-one stack: backend + frontend                               |
| `README.md`           | Quick usage and intro                                              |
| `SYSTEM_GUIDE.md`     | Deep-dive system/algorithm/usage documentation                     |

---

## 🚀 Quick Start

**Windows (PowerShell):**
```bash
git clone https://github.com/CODER7657/complylite.git
cd complylite
py -3 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r backend/requirements.txt
start.bat
```

**macOS/Linux:**
```bash
git clone https://github.com/CODER7657/complylite.git
cd complylite
chmod +x run.sh
./run.sh
```

> **Access:**
  - Frontend: [http://localhost:3000](http://localhost:3000/)
  - Backend/API: [http://localhost:8000](http://localhost:8000/)
  - API Docs: [http://localhost:8000/docs](http://localhost:8000/docs)

---

## 🧩 Core Features

- **CSV Data Upload**: Orders, trades, clients (validate & ingest via UI or API)
- **Real-Time Alerts**: Detect self-trades, wash trades, and high-frequency patterns
- **Dynamic Risk Scoring**: Severity-ranked alerts (HIGH, MEDIUM, LOW)
- **Audit-Ready Reports**: Complete tracking and investigation history
- **Role-Based Dashboard**: Compliance scores, alert breakdowns, trends

---

## 👁️ System Workflow

### 1. Data Ingestion
- Upload client, order, trade data via UI or `/api/v1/data/upload/csv`.
- Validates format, schema, and stores in DuckDB.

### 2. Compliance Detection
- Engine applies both rule-based and ML logic on data:
  - Self-trade detection: Flags clients trading against themselves
  - Wash trade detection: Detects artificial volume inflation
  - High-frequency: Flags rapid trades

### 3. Alert Generation & Management
- Violations trigger risk-scored alerts.
- Alerts are visible in the dashboard for review and audit.

### 4. Dashboard & Analytics
- View compliance scores, system health, trends, and alerts in real time.

---

## 📦 Sample Data

- `sample_data/clients.csv`: Example clients (varied types/risk)
- `sample_data/trades.csv`: Trades, including self-trade scenarios
- `sample_data/orders.csv`: Linked orders for audit tracing

_Try uploading these to see instant results!_

---

## 🔧 Algorithm & API Details

- API Endpoints:
  - `GET /api/v1/dashboard/stats`: system metrics
  - `GET /api/v1/alerts`: alerts (with filters)
  - `POST /api/v1/data/upload/csv`: data upload
  - `POST /api/v1/data/run-detection`: manual detection
  - `PUT /api/v1/alerts/{id}/status`: alert status
- Detection Parameters:
  - Self-trade (4+ matching trades, 24hr window, >70% offset)
  - Wash trade (7-day window, at least 6 cycles, near-zero net)
  - High-frequency (50+ trades/hr, 100+/hr = HIGH)

---

## 🏢 Value for Users

- **Compliance Officers**: Automation, saves audit/prep time, audit trails included
- **Trading Ops**: Real-time alerts, regulator trust, big/complex order handling
- **Management**: Quantified risk, trends, fast reporting

---

## 🛡️ Security & Reliability

- JWT for API access
- Full audit trails
- Configurable settings/rules

---

## 🔄 Continuous Operation

- New trades trigger instant re-analysis
- Scalable analytics (DuckDB)
- Easily adaptable as compliance rules evolve

---

> See `SYSTEM_GUIDE.md` for details on architecture, algorithms, and navigation.

---

*MIT Licensed. Contributions welcome!*
