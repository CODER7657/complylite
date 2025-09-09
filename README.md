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

## 📂 Repo Structure

| Directory/File         | Purpose                                                            |
|-----------------------|--------------------------------------------------------------------|
| `.github/workflows`   | GitHub Actions CI config                                           |
| `backend/`            | FastAPI app, detection logic, DB models, API endpoints             |
| &nbsp;&nbsp;• `app/`  | Main FastAPI components: api (routes), data, models, etc.          |
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

- **CSV Data Upload:** Orders, trades, clients (validate & ingest via UI or API)
- **Real-Time Alerts:** Detect self-trades, wash trades, and high-frequency patterns
- **Dynamic Risk Scoring:** Severity-ranked alerts (HIGH, MEDIUM, LOW)
- **Audit-Ready Reports:** Complete tracking and investigation history
- **Role-Based Dashboard:** Compliance scores, alert breakdowns, trends

---

## 👁️ System Workflow

### 1. **Data Ingestion**
- Upload client, order, trade data via UI or `/api/v1/data/upload/csv`.
- Validates format, schema, and stores in DuckDB.

### 2. **Compliance Detection**
- Engine applies both rule-based and ML logic on data:
  - *Self-trade detection*: Flags clients trading against themselves
  - *Wash trade detection*: Detects artificial volume inflation
  - *High-frequency*: Flags rapid trades

### 3. **Alert Generation & Management**
- Violations trigger risk-scored alerts.
- Alerts are visible in the dashboard for review and audit.

### 4. **Dashboard & Analytics**
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
