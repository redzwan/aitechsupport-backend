import os
import hashlib
import logging
from datetime import datetime, timedelta
from typing import Optional

import bcrypt
from jose import jwt
from dotenv import load_dotenv

# Ensure .env is loaded before reading SECRET_KEY (regardless of import order).
load_dotenv()

logger = logging.getLogger(__name__)

# JWT signing key MUST come from the environment so signing here matches
# verification everywhere else. Never hardcode it in production.
SECRET_KEY = os.getenv("SECRET_KEY", "supersecretkey123")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", 60 * 24 * 8))


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a plaintext password against a bcrypt hash (SHA-256 pre-hashed)."""
    try:
        if isinstance(plain_password, bytes):
            plain_password = plain_password.decode("utf-8")
        # Pre-hash with SHA-256 so bcrypt's 72-byte input limit never truncates.
        hashed_input = hashlib.sha256(plain_password.encode()).hexdigest()
        return bcrypt.checkpw(hashed_input.encode(), hashed_password.encode())
    except Exception as e:  # noqa: BLE001
        logger.error(f"Password verification error: {e}")
        return False


def get_password_hash(password: str) -> str:
    """Hash a password using SHA-256 + bcrypt."""
    if isinstance(password, bytes):
        password = password.decode("utf-8")
    hashed_input = hashlib.sha256(password.encode()).hexdigest()
    return bcrypt.hashpw(hashed_input.encode(), bcrypt.gensalt()).decode("utf-8")


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    to_encode = data.copy()
    expire = datetime.utcnow() + (expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
