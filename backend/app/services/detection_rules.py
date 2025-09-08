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
        try:
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
                              AND ABS(EPOCH(t1.timestamp - t2.timestamp))/3600 <= 24
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
                    "avg_price_difference": float(price_diff) if price_diff else 0,
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
        except Exception as e:
            print(f"Error in detect_self_trades: {e}")
            return []
    
    def detect_wash_trades(self):
        """Detect wash trading patterns"""
        try:
            query = """
            WITH position_analysis AS (
                SELECT 
                    client_id,
                    symbol,
                    SUM(CASE WHEN side = 'BUY' THEN quantity ELSE -quantity END) as net_position,
                    COUNT(*) as trade_count,
                    AVG(quantity) as avg_quantity,
                    MIN(timestamp) as first_trade,
                    MAX(timestamp) as last_trade
                FROM trades 
                WHERE timestamp >= CURRENT_TIMESTAMP - INTERVAL 7 DAY
                GROUP BY client_id, symbol
            )
            SELECT client_id, symbol, net_position, trade_count, avg_quantity
            FROM position_analysis 
            WHERE ABS(net_position) <= (avg_quantity * 0.1)
            AND trade_count >= 6
            """
            
            results = self.conn.execute(query).fetchall()
            alerts = []
            
            for row in results:
                client_id, symbol, net_pos, trade_count, avg_qty = row
                
                alert_data = {
                    "client_id": client_id,
                    "symbol": symbol,
                    "net_position": float(net_pos),
                    "trade_count": trade_count,
                    "avg_quantity": float(avg_qty),
                    "risk_score": min(100, trade_count * 10)
                }
                
                severity = "HIGH" if trade_count > 10 else "MEDIUM"
                
                alert_id = str(uuid.uuid4())
                description = f"Client {client_id} executed {trade_count} trades in {symbol} with near-zero net position"
                
                self.conn.execute("""
                    INSERT INTO alerts (alert_id, rule_name, severity, description, client_id, symbol, data_json)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """, [alert_id, "WASH_TRADE_DETECTION", severity, description, client_id, symbol, json.dumps(alert_data)])
                
                alerts.append({
                    "alert_id": alert_id,
                    "rule_name": "WASH_TRADE_DETECTION", 
                    "severity": severity,
                    "description": description,
                    "data": alert_data
                })
            
            return alerts
        except Exception as e:
            print(f"Error in detect_wash_trades: {e}")
            return []
    
    def detect_high_frequency_patterns(self):
        """Detect suspicious high-frequency trading patterns"""
        try:
            query = """
            WITH hourly_trading AS (
                SELECT 
                    client_id,
                    symbol,
                    DATE_TRUNC('hour', timestamp) as trading_hour,
                    COUNT(*) as trades_per_hour
                FROM trades
                WHERE timestamp >= CURRENT_TIMESTAMP - INTERVAL 1 DAY
                GROUP BY client_id, symbol, DATE_TRUNC('hour', timestamp)
            )
            SELECT client_id, symbol, MAX(trades_per_hour) as max_hourly_trades
            FROM hourly_trading
            GROUP BY client_id, symbol
            HAVING MAX(trades_per_hour) > 10
            """
            
            results = self.conn.execute(query).fetchall()
            alerts = []
            
            for row in results:
                client_id, symbol, max_trades = row
                
                alert_data = {
                    "client_id": client_id,
                    "symbol": symbol,
                    "max_hourly_trades": max_trades,
                    "risk_score": min(100, max_trades)
                }
                
                severity = "HIGH" if max_trades > 50 else "MEDIUM"
                
                alert_id = str(uuid.uuid4())
                description = f"Client {client_id} executed {max_trades} trades per hour in {symbol}"
                
                self.conn.execute("""
                    INSERT INTO alerts (alert_id, rule_name, severity, description, client_id, symbol, data_json)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """, [alert_id, "HIGH_FREQUENCY_PATTERN", severity, description, client_id, symbol, json.dumps(alert_data)])
                
                alerts.append({
                    "alert_id": alert_id,
                    "rule_name": "HIGH_FREQUENCY_PATTERN",
                    "severity": severity,
                    "description": description,
                    "data": alert_data
                })
            
            return alerts
        except Exception as e:
            print(f"Error in detect_high_frequency_patterns: {e}")
            return []
    
    def run_all_detectors(self):
        """Run all detection algorithms"""
        try:
            all_alerts = []
            
            print("Running self-trade detection...")
            self_trade_alerts = self.detect_self_trades()
            all_alerts.extend(self_trade_alerts)
            print(f"Generated {len(self_trade_alerts)} self-trade alerts")
            
            print("Running wash trade detection...")
            wash_trade_alerts = self.detect_wash_trades()
            all_alerts.extend(wash_trade_alerts)
            print(f"Generated {len(wash_trade_alerts)} wash trade alerts")
            
            print("Running high frequency pattern detection...")
            hf_alerts = self.detect_high_frequency_patterns()
            all_alerts.extend(hf_alerts)
            print(f"Generated {len(hf_alerts)} high frequency alerts")
            
            print(f"Total alerts generated: {len(all_alerts)}")
            return all_alerts
            
        except Exception as e:
            print(f"Error in run_all_detectors: {e}")
            return []
