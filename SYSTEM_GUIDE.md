# ComplyLite - Compliance Surveillance System

## 🎯 System Overview

ComplyLite is a comprehensive compliance surveillance system designed for financial brokers to detect and monitor suspicious trading patterns. The system combines real-time data processing with advanced detection algorithms to identify potential compliance violations.

## 🏗️ System Architecture

### Backend (FastAPI + DuckDB)
- **Framework**: FastAPI for high-performance REST API
- **Database**: DuckDB for fast analytical queries
- **Detection Engine**: Custom algorithms for compliance monitoring
- **Data Processing**: Pandas for data manipulation and analysis

### Frontend (React + Ant Design)
- **Framework**: React 18 with modern hooks
- **UI Library**: Ant Design for professional interface
- **Navigation**: React Router for multi-page navigation
- **Charts**: Recharts for data visualization

## 📊 Core Features

### 1. Data Management
- **CSV Upload**: Support for clients, orders, and trades data
- **Real-time Processing**: Automatic validation and ingestion
- **Data Integrity**: Schema validation and error handling

### 2. Compliance Detection Rules
- **Self-Trade Detection**: Identifies when clients trade against themselves
- **Wash Trade Analysis**: Detects artificial trading to create false volume
- **High-Frequency Patterns**: Flags suspicious rapid trading patterns

### 3. Alert Management
- **Real-time Alerts**: Automatic generation based on detection rules
- **Risk Scoring**: Dynamic severity classification (HIGH/MEDIUM/LOW)
- **Status Tracking**: Workflow for alert investigation and resolution

### 4. Dashboard & Analytics
- **Compliance Score**: Overall system health indicator
- **Risk Metrics**: Real-time statistics and trends
- **Activity Monitoring**: Recent alerts and trading patterns

## 🔧 How to Use the System

### Step 1: Start the Application
Both servers should be running:
- Backend: `http://localhost:8000`
- Frontend: `http://localhost:3000`

### Step 2: Upload Sample Data
1. Navigate to **Data Upload** page
2. Select data type (clients, trades, or orders)
3. Upload the CSV files from `/sample_data/` folder
4. System will automatically validate and process the data

### Step 3: Monitor Compliance
1. Visit **Dashboard** for overview metrics
2. Check **Alerts** page for detailed compliance violations
3. Use **Rule Settings** to configure detection parameters

## 📁 Sample Data Provided

### Client Data (`clients.csv`)
- 8 sample clients with different risk profiles
- Includes institutional, retail, and hedge fund types
- Risk ratings: HIGH, MEDIUM, LOW

### Trade Data (`trades.csv`)
- 25 sample trades across multiple symbols (AAPL, MSFT, GOOGL, etc.)
- Includes potential self-trading patterns by CLIENT_001 and CLIENT_003
- Timestamped for pattern analysis

### Order Data (`orders.csv`)
- 10 sample orders with trader assignments
- Links to corresponding trades for audit trail

## 🎯 Detection Algorithm Details

### Self-Trade Detection
**Purpose**: Identifies clients trading against themselves
**Parameters**:
- Time Window: 24 hours (configurable)
- Minimum Trade Pairs: 4 trades
- Offsetting Threshold: 70% of trades must be offsetting

**Example Pattern**: 
```
CLIENT_001: BUY 100 AAPL @ 150.25
CLIENT_001: SELL 100 AAPL @ 150.30 (5 minutes later)
```

### Wash Trade Detection
**Purpose**: Detects artificial trading to inflate volume
**Parameters**:
- Analysis Window: 7 days
- Minimum Trades: 6 transactions
- Net Position: Must be near zero (< 10% of average quantity)

**Example Pattern**:
Multiple buy/sell cycles resulting in minimal net position changes

### High-Frequency Pattern Detection
**Purpose**: Flags suspicious rapid trading
**Parameters**:
- Threshold: 50+ trades per hour
- Alert Level: 100+ trades per hour (HIGH severity)

## 🚀 Testing the System

### Quick Test Workflow:
1. **Upload Clients**: Start with `clients.csv` to establish client database
2. **Upload Trades**: Load `trades.csv` - this will trigger automatic detection
3. **View Results**: Check Dashboard for new alerts and compliance score
4. **Investigate Alerts**: Use Alerts page to review detected violations
5. **Adjust Rules**: Use Rule Settings to modify detection parameters

### Expected Results:
After uploading the sample data, you should see:
- **Self-Trade Alerts**: CLIENT_001 and CLIENT_003 will trigger alerts
- **Compliance Score**: Should be around 60-70 due to detected violations
- **Dashboard Metrics**: 8 clients, 25 trades, 3+ alerts generated

## 🔍 Navigation Guide

### Dashboard Page
- **Compliance Score**: Central circular progress indicator
- **System Overview**: Total trades and active clients
- **Alert Statistics**: Breakdown by severity levels
- **Recent Activity**: Latest alerts and trading symbols

### Alerts Page
- **Alert Table**: Sortable list with filtering options
- **Alert Details**: Click eye icon for full investigation details
- **Status Updates**: Change alert status (OPEN → IN_REVIEW → CLOSED)
- **Bulk Actions**: Run detection manually or refresh data

### Data Upload Page
- **File Upload**: Drag-and-drop CSV interface
- **Data Validation**: Real-time format checking
- **Progress Tracking**: Upload status and results
- **Detection Trigger**: Automatic rule execution for trades

### Rule Settings Page
- **Algorithm Configuration**: Adjust detection parameters
- **Enable/Disable Rules**: Toggle individual detection algorithms
- **Threshold Management**: Fine-tune sensitivity levels
- **Real-time Updates**: Changes apply immediately to new data

## 🛠️ Technical Implementation

### Backend API Endpoints
```
GET  /health                           # System health check
GET  /api/v1/dashboard/stats          # Dashboard metrics
GET  /api/v1/alerts                   # List alerts with filters
POST /api/v1/data/upload/csv          # Upload CSV data
POST /api/v1/data/run-detection       # Manual detection trigger
PUT  /api/v1/alerts/{id}/status       # Update alert status
```

### Database Schema
```sql
-- Core tables for compliance data
alerts (alert_id, rule_name, severity, description, status, created_at)
clients (client_id, client_name, client_type, risk_rating)
trades (trade_id, client_id, symbol, side, quantity, price, timestamp)
orders (order_id, client_id, symbol, side, quantity, price, timestamp)
```

### Detection Engine Flow
1. **Data Ingestion**: CSV upload validates and stores data
2. **Pattern Analysis**: Algorithms scan for suspicious patterns
3. **Alert Generation**: Violations create alerts with severity scoring
4. **Real-time Updates**: Dashboard reflects new compliance status

## 🎯 Business Value

### Compliance Officers
- **Automated Monitoring**: Reduces manual surveillance workload
- **Risk Prioritization**: Focus on HIGH severity alerts first
- **Audit Trail**: Complete investigation history and documentation

### Trading Operations
- **Real-time Alerts**: Immediate notification of potential violations
- **Pattern Recognition**: Identifies complex multi-trade schemes
- **Regulatory Reporting**: Structured data for compliance reporting

### Management
- **Compliance Dashboard**: Executive view of organizational risk
- **Trend Analysis**: Historical pattern identification
- **Risk Metrics**: Quantified compliance scoring system

## 🔄 Continuous Operation

The system is designed for continuous operation:
- **Real-time Processing**: New trades trigger immediate analysis
- **Scalable Architecture**: DuckDB handles large datasets efficiently
- **Configurable Rules**: Adapt detection parameters as regulations change
- **Audit Logging**: Complete trail of all system activities

This comprehensive surveillance system provides the foundation for robust compliance monitoring in financial trading operations.
