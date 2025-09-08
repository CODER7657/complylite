from fastapi import FastAPI
from contextlib import asynccontextmanager
from fastapi.middleware.cors import CORSMiddleware
from app.api import data_upload, alerts, dashboard
from app.core.database import init_database, get_db_connection

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: create a single DuckDB connection for the app
    app.state.db = get_db_connection()
    try:
        init_database(app.state.db)
        print("✅ Database initialized successfully")
    except Exception as e:
        print(f"❌ Database initialization failed: {e}")
    yield
    # Shutdown: close the DuckDB connection
    try:
        app.state.db.close()
    except Exception:
        pass

app = FastAPI(
    title="ComplyLite API",
    description="Compliance surveillance co-pilot for brokers",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:3001"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Startup handled by lifespan

app.include_router(data_upload.router, prefix="/api/v1/data", tags=["data"])
app.include_router(alerts.router, prefix="/api/v1/alerts", tags=["alerts"])
app.include_router(dashboard.router, prefix="/api/v1/dashboard", tags=["dashboard"])

@app.get("/")
async def root():
    return {
        "message": "ComplyLite API is running",
        "version": "1.0.0",
        "docs": "/docs"
    }

@app.get("/health")
async def health_check():
    return {"status": "healthy", "service": "ComplyLite"}
