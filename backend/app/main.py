from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.api import data_upload, alerts, dashboard
from app.core.database import init_database

app = FastAPI(
    title="ComplyLite API",
    description="Compliance surveillance co-pilot for brokers",
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:3001"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.on_event("startup")
async def startup_event():
    try:
        init_database()
        print("✅ Database initialized successfully")
    except Exception as e:
        print(f"❌ Database initialization failed: {e}")

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
