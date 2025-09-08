from fastapi import APIRouter, UploadFile, File, HTTPException, Form
import pandas as pd
import io
from app.core.database import get_db_connection
from app.services.detection_rules import ComplianceDetector

router = APIRouter()

@router.post("/upload/csv")
async def upload_csv_data(
    file: UploadFile = File(...),
    table_type: str = Form(...)
):
    try:
        # Read CSV file
        contents = await file.read()
        df = pd.read_csv(io.StringIO(contents.decode('utf-8')))
        
        # Validate table type
        if table_type not in ['orders', 'trades', 'clients']:
            raise HTTPException(status_code=400, detail="Invalid table type")
        
        # Validate columns based on table type
        if table_type == "orders":
            required_columns = ['order_id', 'client_id', 'symbol', 'side', 'quantity', 'price', 'timestamp']
        elif table_type == "trades":
            required_columns = ['trade_id', 'client_id', 'symbol', 'side', 'quantity', 'price', 'timestamp']
        elif table_type == "clients":
            required_columns = ['client_id', 'client_name']
        
        missing_columns = [col for col in required_columns if col not in df.columns]
        if missing_columns:
            raise HTTPException(
                status_code=400, 
                detail=f"Missing required columns: {missing_columns}"
            )
        
        # Connect to database and insert data
        conn = get_db_connection()
        
        # Clear existing data for demo purposes
        conn.execute(f"DELETE FROM {table_type}")
        
        # Insert new data
        conn.register("df_temp", df)
        conn.execute(f"INSERT INTO {table_type} SELECT * FROM df_temp")
        
        # If trades were uploaded, run detection algorithms
        new_alerts = []
        if table_type == "trades":
            detector = ComplianceDetector()
            new_alerts = detector.run_all_detectors()
        
        conn.close()
        
        return {
            "message": f"Successfully uploaded {len(df)} records to {table_type}",
            "records_uploaded": len(df),
            "table_type": table_type,
            "new_alerts_generated": len(new_alerts)
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Upload failed: {str(e)}")

@router.get("/tables/info")
async def get_table_info():
    """Get information about all tables"""
    conn = get_db_connection()
    
    tables_info = {}
    tables = ['orders', 'trades', 'clients', 'alerts']
    
    for table in tables:
        try:
            count_result = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()
            count = count_result[0] if count_result else 0
            tables_info[table] = {"record_count": count}
        except:
            tables_info[table] = {"record_count": 0}
    
    conn.close()
    return tables_info

@router.post("/run-detection")
async def run_detection_manually():
    """Manually trigger compliance detection"""
    try:
        detector = ComplianceDetector()
        alerts = detector.run_all_detectors()
        
        return {
            "message": "Detection completed successfully",
            "alerts_generated": len(alerts),
            "alerts": alerts[:5]  # Return first 5 alerts
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Detection failed: {str(e)}")
