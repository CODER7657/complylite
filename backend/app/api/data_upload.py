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
        # Basic validation
        if not file or not file.filename.lower().endswith('.csv'):
            raise HTTPException(status_code=400, detail="Please upload a CSV file")

        # Read CSV file
        contents = await file.read()
        if not contents:
            raise HTTPException(status_code=400, detail="Uploaded file is empty")

        df = pd.read_csv(io.StringIO(contents.decode('utf-8')))

        # Normalize column names (strip spaces)
        df.columns = [c.strip() for c in df.columns]
        
        # Validate table type
        if table_type not in ['orders', 'trades', 'clients']:
            raise HTTPException(status_code=400, detail="Invalid table type")

        # Target schemas (as in DuckDB)
        target_columns_map = {
            "orders": [
                'order_id', 'client_id', 'trader_id', 'symbol', 'side', 'quantity', 'price', 'timestamp', 'order_type'
            ],
            "trades": [
                'trade_id', 'order_id', 'client_id', 'symbol', 'side', 'quantity', 'price', 'timestamp'
            ],
            "clients": [
                'client_id', 'client_name', 'client_type', 'risk_rating', 'account_status', 'created_date'
            ]
        }

        required_min_cols = {
            "orders": ['order_id', 'client_id', 'symbol', 'side', 'quantity', 'price', 'timestamp'],
            "trades": ['trade_id', 'client_id', 'symbol', 'side', 'quantity', 'price', 'timestamp'],
            "clients": ['client_id', 'client_name']
        }

        required_columns = required_min_cols[table_type]
        missing_required = [c for c in required_columns if c not in df.columns]
        if missing_required:
            raise HTTPException(status_code=400, detail=f"Missing required columns: {missing_required}")

        # Add any missing optional columns with None
        target_cols = target_columns_map[table_type]
        for col in target_cols:
            if col not in df.columns:
                df[col] = None

        # Reorder columns to match the table schema
        df = df[target_cols]

        # Connect to database and insert data with explicit casts
        conn = get_db_connection()
        try:
            # Clear existing data for demo purposes
            conn.execute(f"DELETE FROM {table_type}")

            conn.register("df_temp", df)

            # Build SELECT with casts for key columns
            select_exprs = []
            for col in target_cols:
                if col == "timestamp":
                    select_exprs.append("CAST(timestamp AS TIMESTAMP) AS timestamp")
                elif col == "created_date":
                    select_exprs.append("CAST(created_date AS DATE) AS created_date")
                elif col == "quantity":
                    select_exprs.append("CAST(quantity AS INTEGER) AS quantity")
                elif col == "price":
                    select_exprs.append("CAST(price AS DECIMAL(10,4)) AS price")
                else:
                    select_exprs.append(col)

            select_sql = ", ".join(select_exprs)
            insert_sql = f"INSERT INTO {table_type} ({', '.join(target_cols)}) SELECT {select_sql} FROM df_temp"
            conn.execute(insert_sql)
        finally:
            try:
                conn.unregister("df_temp")
            except Exception:
                pass
            conn.close()

        # If trades were uploaded, run detection algorithms
        new_alerts = []
        if table_type == "trades":
            try:
                detector = ComplianceDetector()
                new_alerts = detector.run_all_detectors()
                print(f"Generated {len(new_alerts)} alerts for uploaded trades")
            except Exception as detection_error:
                print(f"Detection failed but upload successful: {detection_error}")
                # Don't fail the upload if detection fails

        return {
            "message": f"Successfully uploaded {len(df)} records to {table_type}",
            "records_uploaded": len(df),
            "table_type": table_type,
            "new_alerts_generated": len(new_alerts)
        }

    except HTTPException:
        raise
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
