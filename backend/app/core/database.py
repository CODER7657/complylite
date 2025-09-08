import duckdb
import os
from app.core.config import settings

def get_db_connection():
    """Get database connection"""
    return duckdb.connect(settings.database_url)

def init_database():
    """Initialize database with required tables"""
    conn = get_db_connection()
    
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
    
    conn.close()
    print("Database initialized successfully")
