import duckdb
from fastapi import Request
from app.core.config import settings

def get_db_connection():
    """Create a new database connection (fallback). Prefer using the FastAPI dependency get_db for requests."""
    return duckdb.connect(settings.database_url)

def get_db(request: Request):
    """FastAPI dependency: return the application-scoped DuckDB connection."""
    return request.app.state.db

def init_database(conn: duckdb.DuckDBPyConnection | None = None):
    """Initialize database with required tables.

    If a connection is provided, it will be used and not closed here.
    Otherwise, a temporary connection will be created and closed.
    """
    own_conn = False
    if conn is None:
        conn = get_db_connection()
        own_conn = True
    
    # Create orders table
    conn.execute("""
        CREATE TABLE IF NOT EXISTS orders (
            order_id VARCHAR PRIMARY KEY,
            client_id VARCHAR,
            trader_id VARCHAR,
            symbol VARCHAR,
            side VARCHAR,
            quantity INTEGER,
            price DECIMAL(10,4),
            timestamp TIMESTAMP,
            order_type VARCHAR
        )
    """)
    
    # Create trades table
    conn.execute("""
        CREATE TABLE IF NOT EXISTS trades (
            trade_id VARCHAR PRIMARY KEY,
            order_id VARCHAR,
            client_id VARCHAR,
            symbol VARCHAR,
            side VARCHAR,
            quantity INTEGER,
            price DECIMAL(10,4),
            timestamp TIMESTAMP
        )
    """)
    
    # Create clients table
    conn.execute("""
        CREATE TABLE IF NOT EXISTS clients (
            client_id VARCHAR PRIMARY KEY,
            client_name VARCHAR,
            client_type VARCHAR,
            risk_rating VARCHAR,
            account_status VARCHAR,
            created_date DATE
        )
    """)
    
    # Create alerts table
    conn.execute("""
        CREATE TABLE IF NOT EXISTS alerts (
            alert_id VARCHAR PRIMARY KEY,
            rule_name VARCHAR,
            severity VARCHAR,
            description TEXT,
            client_id VARCHAR,
            symbol VARCHAR,
            data_json TEXT,
            status VARCHAR DEFAULT 'OPEN',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # Helpful indexes for faster filtering
    conn.execute("CREATE INDEX IF NOT EXISTS idx_alerts_created_at ON alerts(created_at)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_alerts_severity ON alerts(severity)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_alerts_status ON alerts(status)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_alerts_client ON alerts(client_id)")
    
    if own_conn:
        conn.close()
    print("Database initialized successfully")
