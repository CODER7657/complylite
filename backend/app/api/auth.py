from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from app.core.security import create_access_token


router = APIRouter()


class LoginRequest(BaseModel):
    username: str
    password: str


@router.post("/login")
async def login(body: LoginRequest):
    # Simple demo auth: single admin user. Replace with real user store.
    if body.username == "admin" and body.password == "admin123":
        token = create_access_token(subject=body.username, role="admin")
        return {"access_token": token, "token_type": "bearer"}
    raise HTTPException(status_code=401, detail="Invalid credentials")


