from fastapi import APIRouter, HTTPException, Depends
from typing import List, Optional
from app.core.database import get_db
from app.models.schemas import AlertResponse

router = APIRouter()

@router.get("/", response_model=List[AlertResponse])
async def get_alerts(
    limit: int = 50,
    offset: int = 0,
    severity: Optional[str] = None,
    status: Optional[str] = None,
    client_id: Optional[str] = None,
    rule_name: Optional[str] = None,
    conn = Depends(get_db),
):
    """Get alerts with optional filtering"""
    try:
        query = "SELECT * FROM alerts WHERE 1=1"
        params: list = []

        if severity:
            query += " AND severity = ?"
            params.append(severity.upper())

        if status:
            query += " AND status = ?"
            params.append(status.upper())

        if client_id:
            query += " AND client_id = ?"
            params.append(client_id)

        if rule_name:
            query += " AND rule_name = ?"
            params.append(rule_name)

        query += " ORDER BY created_at DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])

        results = conn.execute(query, params).fetchall()

        alerts = [
            {
                "alert_id": row[0],
                "rule_name": row[1],
                "severity": row[2],
                "description": row[3],
                "client_id": row[4],
                "symbol": row[5],
                "data_json": row[6],
                "status": row[7],
                "created_at": row[8],
            }
            for row in results
        ]
        return alerts
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/stats")
async def get_alert_stats(conn = Depends(get_db)):
    """Get alert statistics"""
    try:
        stats: dict = {}

        # Total alerts
        stats["total_alerts"] = conn.execute("SELECT COUNT(*) FROM alerts").fetchone()[0]

        # By severity
        for severity, count in conn.execute(
            "SELECT severity, COUNT(*) FROM alerts GROUP BY severity"
        ).fetchall():
            stats[f"{severity.lower()}_alerts"] = count

        # Today's alerts
        stats["alerts_today"] = conn.execute(
            "SELECT COUNT(*) FROM alerts WHERE created_at >= CURRENT_DATE"
        ).fetchone()[0]

        # By status
        for stat, count in conn.execute(
            "SELECT status, COUNT(*) FROM alerts GROUP BY status"
        ).fetchall():
            stats[f"{stat.lower()}_alerts"] = count

        return stats
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.put("/{alert_id}/status")
async def update_alert_status(alert_id: str, status: str, conn = Depends(get_db)):
    """Update alert status"""
    try:
        if status.upper() not in ["OPEN", "IN_REVIEW", "CLOSED", "FALSE_POSITIVE"]:
            raise HTTPException(status_code=400, detail="Invalid status")

        # Verify alert exists before updating (DuckDB doesn't provide reliable rowcount)
        exists = conn.execute(
            "SELECT COUNT(*) FROM alerts WHERE alert_id = ?",
            [alert_id],
        ).fetchone()[0]
        if exists == 0:
            raise HTTPException(status_code=404, detail="Alert not found")

        conn.execute(
            "UPDATE alerts SET status = ? WHERE alert_id = ?",
            [status.upper(), alert_id],
        )
        return {"message": f"Alert {alert_id} status updated to {status}"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.delete("/{alert_id}")
async def delete_alert(alert_id: str, conn = Depends(get_db)):
    """Delete a specific alert"""
    try:
        # Verify alert exists, then delete
        exists = conn.execute(
            "SELECT COUNT(*) FROM alerts WHERE alert_id = ?",
            [alert_id],
        ).fetchone()[0]
        if exists == 0:
            raise HTTPException(status_code=404, detail="Alert not found")
        conn.execute("DELETE FROM alerts WHERE alert_id = ?", [alert_id])
        return {"message": f"Alert {alert_id} deleted"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
