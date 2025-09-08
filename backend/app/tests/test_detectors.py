import duckdb
from app.core.database import init_database
from app.services.detection_rules import ComplianceDetector


def seed_trades(conn: duckdb.DuckDBPyConnection) -> None:
    conn.execute("DELETE FROM trades")
    conn.execute("DELETE FROM alerts")
    conn.execute("""
        INSERT INTO trades (trade_id, order_id, client_id, symbol, side, quantity, price, timestamp)
        VALUES
        ('t1', NULL, 'C1', 'AAPL', 'BUY', 10, 100.0, CURRENT_TIMESTAMP),
        ('t2', NULL, 'C1', 'AAPL', 'SELL', 10, 100.1, CURRENT_TIMESTAMP),
        ('t3', NULL, 'C1', 'AAPL', 'BUY', 10, 100.0, CURRENT_TIMESTAMP),
        ('t4', NULL, 'C1', 'AAPL', 'SELL', 10, 100.2, CURRENT_TIMESTAMP)
    """)


def test_self_trade_detector_flags_pairs(tmp_path):
    conn = duckdb.connect(str(tmp_path / "test.db"))
    try:
        init_database(conn)
        seed_trades(conn)
        detector = ComplianceDetector(conn)
        alerts = detector.detect_self_trades()
        assert len(alerts) >= 1
        assert all(a["rule_name"] == "SELF_TRADE_DETECTION" for a in alerts)
    finally:
        conn.close()


