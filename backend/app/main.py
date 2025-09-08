from fastapi import FastAPI, Request
from contextlib import asynccontextmanager
from fastapi.middleware.cors import CORSMiddleware
from app.api import data_upload, alerts, dashboard
from app.api import auth
from app.core.database import init_database, get_db_connection
from app.core.config import settings
import structlog
from starlette.middleware.base import BaseHTTPMiddleware
import time

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

logger = structlog.get_logger()

app = FastAPI(
    title="ComplyLite API",
    description="Compliance surveillance co-pilot for brokers",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Startup handled by lifespan

app.include_router(data_upload.router, prefix="/api/v1/data", tags=["data"])
app.include_router(alerts.router, prefix="/api/v1/alerts", tags=["alerts"])
app.include_router(dashboard.router, prefix="/api/v1/dashboard", tags=["dashboard"])
app.include_router(auth.router, prefix="/api/v1/auth", tags=["auth"])

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

@app.middleware("http")
async def log_requests(request: Request, call_next):
    try:
        start = time.perf_counter()
        response = await call_next(request)
        duration_ms = int((time.perf_counter() - start) * 1000)
        logger.info(
            "request_completed",
            method=request.method,
            path=request.url.path,
            status_code=response.status_code,
            duration_ms=duration_ms,
        )
        return response
    except Exception as e:
        logger.exception("unhandled_exception", error=str(e))
        raise
