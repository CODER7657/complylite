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
                COUNT(CASE WHEN DATE(created_at) = CURRENT_DATE THEN 1 END) as today
            FROM alerts
        """).fetchone()
        
        # Get trade and client counts
        trade_count = conn.execute("SELECT COUNT(*) FROM trades").fetchone()[0]
        client_count = conn.execute("SELECT COUNT(*) FROM clients").fetchone()[0]
        
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
            WHERE timestamp >= CURRENT_TIMESTAMP - INTERVAL '24 hours'
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
        
        # Calculate compliance metrics
        total_trades = conn.execute("SELECT COUNT(*) FROM trades").fetchone()[0]
        total_alerts = conn.execute("SELECT COUNT(*) FROM alerts WHERE status = 'OPEN'").fetchone()[0]
        high_risk_alerts = conn.execute("SELECT COUNT(*) FROM alerts WHERE severity = 'HIGH' AND status = 'OPEN'").fetchone()[0]
        
        if total_trades == 0:
            compliance_score = 100
        else:
            # Simple scoring algorithm
            alert_ratio = total_alerts / total_trades
            high_risk_ratio = high_risk_alerts / total_trades
            
            # Score out of 100 (lower alerts = higher score)
            compliance_score = max(0, 100 - (alert_ratio * 1000) - (high_risk_ratio * 2000))
            compliance_score = min(100, compliance_score)
        
        conn.close()
        
        return {
            "compliance_score": round(compliance_score, 2),
            "total_trades": total_trades,
            "open_alerts": total_alerts,
            "high_risk_alerts": high_risk_alerts,
            "risk_level": "LOW" if compliance_score > 80 else "MEDIUM" if compliance_score > 60 else "HIGH"
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
