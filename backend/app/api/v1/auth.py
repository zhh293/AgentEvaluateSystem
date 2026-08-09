from pydantic import BaseModel, EmailStr, Field
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import create_access_token, hash_password, verify_password
from app.infrastructure.database import get_db
from app.models.user import User


router = APIRouter(prefix="/auth", tags=["auth"])


class RegisterRequest(BaseModel):
    username: str = Field(min_length=3, max_length=100, pattern=r"^[A-Za-z0-9_.-]+$")
    email: EmailStr
    password: str = Field(min_length=10, max_length=200)


class LoginRequest(BaseModel):
    username: str
    password: str


@router.post("/register", status_code=201)
async def register(data: RegisterRequest, db: AsyncSession = Depends(get_db)):
    existing = (await db.execute(select(User).where(or_(User.username == data.username, User.email == str(data.email))))).scalar_one_or_none()
    if existing:
        raise HTTPException(status_code=409, detail="Username or email already exists")
    user = User(username=data.username, email=str(data.email), password_hash=hash_password(data.password))
    db.add(user); await db.flush()
    return {"id": str(user.id), "username": user.username}


@router.post("/login")
async def login(data: LoginRequest, db: AsyncSession = Depends(get_db)):
    user = (await db.execute(select(User).where(User.username == data.username))).scalar_one_or_none()
    if user is None or not verify_password(data.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    return {"access_token": create_access_token(str(user.id), user.role), "token_type": "bearer", "expires_in": settings.JWT_EXPIRE_MINUTES * 60}


from app.core.config import settings
