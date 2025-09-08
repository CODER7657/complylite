from fastapi import APIRouter, HTTPException
from app.core.database import get_db_connection
from app.models.schemas import DashboardStats

router = APIRouter()

@router.get("/stats", response_model=DashboardStats)
async def get_dashboard_stats():
    """Get comprehensive dashboard statistics"""
    try:
        conn = get_db_connection()
        
        # Get alert counts by severity
        alert_stats = conn.execute("""
            SELECT 
                COUNT(*) as total,
                COUNT(CASE WHEN severity = 'HIGH' THEN 1 END) as high,
                COUNT(CASE WHEN severity = 'MEDIUM' THEN 1 END) as medium,
                COUNT(CASE WHEN severity = 'LOW' THEN 1 END) as low,
                COUNT(CASE WHEN created_at >= CURRENT_DATE THEN 1 END) as today
            FROM alerts
        """).fetchone()
        
        # Get trade and client counts
        trade_count = conn.execute("SELECT COUNT(*) FROM trades").fetchone()[0]
        client_count = conn.execute("SELECT COUNT(*) FROM clients").fetchone()[0]
        # If no client master data, approximate active clients by distinct IDs in trades
        if client_count == 0:
            client_count = conn.execute("SELECT COUNT(DISTINCT client_id) FROM trades").fetchone()[0]
        
        conn.close()
        
        return {
            "total_alerts": alert_stats[0],
            "high_risk_alerts": alert_stats[1],
            "medium_risk_alerts": alert_stats[2],
            "low_risk_alerts": alert_stats[3],
            "alerts_today": alert_stats[4],
            "total_trades": trade_count,
            "total_clients": client_count
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/recent-activity")
async def get_recent_activity():
    """Get recent system activity"""
    try:
        conn = get_db_connection()
        
        # Recent alerts
        recent_alerts = conn.execute("""
            SELECT alert_id, rule_name, severity, description, created_at
            FROM alerts 
            ORDER BY created_at DESC 
            LIMIT 10
        """).fetchall()
        
        # Recent trades by symbol
        symbol_activity = conn.execute("""
            SELECT symbol, COUNT(*) as trade_count, MAX(timestamp) as last_trade
            FROM trades 
            WHERE timestamp >= NOW() - INTERVAL 1 DAY
            GROUP BY symbol
            ORDER BY trade_count DESC
            LIMIT 5
        """).fetchall()
        
        conn.close()
        
        return {
            "recent_alerts": [
                {
                    "alert_id": alert[0],
                    "rule_name": alert[1],
                    "severity": alert[2],
                    "description": alert[3],
                    "created_at": alert[4]
                }
                for alert in recent_alerts
            ],
            "active_symbols": [
                {
                    "symbol": symbol[0],
                    "trade_count": symbol[1],
                    "last_trade": symbol[2]
                }
                for symbol in symbol_activity
            ]
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/compliance-score")
async def get_compliance_score():
    """Calculate overall compliance score"""
    try:
        conn = get_db_connection()
        
        # Calculate compliance metrics (demo-friendly)
        total_trades = conn.execute("SELECT COUNT(*) FROM trades").fetchone()[0]
        low_open = conn.execute("SELECT COUNT(*) FROM alerts WHERE severity = 'LOW' AND status = 'OPEN'").fetchone()[0]
        med_open = conn.execute("SELECT COUNT(*) FROM alerts WHERE severity = 'MEDIUM' AND status = 'OPEN'").fetchone()[0]
        high_open = conn.execute("SELECT COUNT(*) FROM alerts WHERE severity = 'HIGH' AND status = 'OPEN'").fetchone()[0]

        if total_trades == 0:
            compliance_score = 0.0
        else:
            # Per request: score = (low + medium) / total_trades * 100 (demo purpose)
            compliance_score = ((low_open + med_open) / total_trades) * 100
            # Clamp 0-100
            compliance_score = max(0.0, min(100.0, compliance_score))
        
        conn.close()
        
        return {
            "compliance_score": round(compliance_score, 2),
            "total_trades": total_trades,
            "open_alerts": low_open + med_open + high_open,
            "high_risk_alerts": high_open,
            "risk_level": "LOW" if compliance_score >= 80 else ("MEDIUM" if compliance_score >= 50 else "HIGH")
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
