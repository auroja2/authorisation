import random

# In-memory user store (replace with DB in prod)
OTP_STORE: dict[str, str] = {}
def generate_otp(username: str) -> str:
    otp = str(random.randint(100000, 999999))
    OTP_STORE[username] = otp
    return otp

def verify_otp(username: str, otp: str) -> bool:
    return OTP_STORE.get(username) == otp
from datetime import datetime, timedelta
from typing import Optional
from jose import JWTError, jwt
from passlib.context import CryptContext
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from pydantic import BaseModel
from config import settings

pwd_context = CryptContext(schemes=["sha256_crypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/token")

# In-memory user store (replace with DB in prod)
USERS_DB: dict[str, dict] = {
    "admin": {
        "username": "admin",
        "hashed_password": pwd_context.hash("admin123"),
        "role": "admin",
        "email": "admin@recon.io",
    },
    "analyst": {
        "username": "analyst",
        "hashed_password": pwd_context.hash("analyst123"),
        "role": "analyst",
        "email": "analyst@recon.io",
    },
}


class TokenData(BaseModel):
    username: Optional[str] = None
    role: Optional[str] = None


class User(BaseModel):
    username: str
    email: str
    role: str


def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)


def authenticate_user(username: str, password: str) -> Optional[dict]:
    user = USERS_DB.get(username)
    if not user or not verify_password(password, user["hashed_password"]):
        return None
    return user


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    to_encode = data.copy()
    expire = datetime.utcnow() + (expires_delta or timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES))
    to_encode["exp"] = expire
    return jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


async def get_current_user(token: str = Depends(oauth2_scheme)) -> User:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or expired token",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        username: str = payload.get("sub")
        role: str = payload.get("role")
        if username is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception
    user = USERS_DB.get(username)
    if not user:
        raise credentials_exception
    return User(username=username, email=user["email"], role=role)


def require_role(*roles: str):
    async def checker(current_user: User = Depends(get_current_user)):
        if current_user.role not in roles:
            raise HTTPException(status_code=403, detail=f"Role '{current_user.role}' not authorized")
        return current_user
    return checker
