import duckdb
import json
import uuid
from datetime import datetime
from app.core.database import get_db_connection

class ComplianceDetector:
    def __init__(self):
        self.conn = get_db_connection()
    
    def detect_self_trades(self):
        """Detect potential self-trading patterns"""
        query = """
        WITH self_trade_analysis AS (
            SELECT 
                t1.client_id,
                t1.symbol,
                COUNT(*) as trade_pairs,
                SUM(CASE WHEN t1.side != t2.side THEN 1 ELSE 0 END) as offsetting_trades,
                AVG(ABS(t1.price - t2.price)) as avg_price_diff
            FROM trades t1
            JOIN trades t2 ON t1.client_id = t2.client_id 
                          AND t1.symbol = t2.symbol
                          AND t1.trade_id != t2.trade_id
                          AND ABS(EXTRACT(EPOCH FROM (t1.timestamp - t2.timestamp))/3600) <= 24
            GROUP BY t1.client_id, t1.symbol
        )
        SELECT client_id, symbol, trade_pairs, offsetting_trades, avg_price_diff
        FROM self_trade_analysis 
        WHERE offsetting_trades >= 2 AND trade_pairs >= 4
        """
        
        results = self.conn.execute(query).fetchall()
        alerts = []
        
        for row in results:
            client_id, symbol, pairs, offsetting, price_diff = row
            
            alert_data = {
                "client_id": client_id,
                "symbol": symbol,
                "trade_pairs": pairs,
                "offsetting_trades": offsetting,
                "avg_price_difference": price_diff,
                "risk_score": min(100, (offsetting / pairs) * 100)
            }
            
            severity = "HIGH" if offsetting / pairs > 0.7 else "MEDIUM"
            
            alert_id = str(uuid.uuid4())
            description = f"Client {client_id} executed {offsetting} offsetting trades in {symbol} within 24 hours"
            
            # Insert alert
            self.conn.execute("""
                INSERT INTO alerts (alert_id, rule_name, severity, description, client_id, symbol, data_json)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, [alert_id, "SELF_TRADE_DETECTION", severity, description, client_id, symbol, json.dumps(alert_data)])
            
            alerts.append({
                "alert_id": alert_id,
                "rule_name": "SELF_TRADE_DETECTION",
                "severity": severity,
                "description": description,
                "data": alert_data
            })
        
        return alerts
