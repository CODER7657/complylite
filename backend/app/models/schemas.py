from pydantic import BaseModel
from datetime import datetime
from typing import Optional, Dict, Any

class OrderBase(BaseModel):
    order_id: str
    client_id: str
    trader_id: Optional[str] = None
    symbol: str
    side: str
    quantity: int
    price: float
    timestamp: datetime
    order_type: Optional[str] = None

class TradeBase(BaseModel):
    trade_id: str
    order_id: Optional[str] = None
    client_id: str
    symbol: str
    side: str
    quantity: int
    price: float
    timestamp: datetime

class ClientBase(BaseModel):
    client_id: str
    client_name: str
    client_type: Optional[str] = None
    risk_rating: Optional[str] = None
    account_status: Optional[str] = None
    created_date: Optional[datetime] = None

class AlertResponse(BaseModel):
    alert_id: str
    rule_name: str
    severity: str
    description: str
    client_id: Optional[str] = None
    symbol: Optional[str] = None
    data_json: Optional[str] = None
    status: str
    created_at: datetime

class DashboardStats(BaseModel):
    total_alerts: int
    high_risk_alerts: int
    medium_risk_alerts: int
    low_risk_alerts: int
    total_trades: int
    total_clients: int
    alerts_today: int
