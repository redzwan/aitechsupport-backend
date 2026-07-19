"""Shared FastAPI dependencies: DB session + current authenticated user."""
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.core.security import SECRET_KEY, ALGORITHM
from app.models.user import User

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")


def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
) -> User:
    credentials_exc = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id = payload.get("sub")
        if user_id is None:
            raise credentials_exc
        user_id = int(user_id)  # a validly-signed but malformed sub -> 401, not 500
    except (JWTError, ValueError, TypeError):
        raise credentials_exc

    user = db.query(User).filter(User.id == user_id).first()
    if user is None or not user.is_active:
        raise credentials_exc
    return user


def get_platform_admin(user: User = Depends(get_current_user)) -> User:
    """Guard for platform-wide settings (API keys, default model)."""
    if not user.is_platform_admin:
        raise HTTPException(status_code=403, detail="Platform admin only")
    return user


def get_agent_user(user: User = Depends(get_current_user)) -> User:
    """Guard for live human-agent takeover actions. Permissive by design — any org
    staff (owner|admin|agent) may claim and answer; queries stay scoped to their org."""
    if user.role not in ("owner", "admin", "agent"):
        raise HTTPException(status_code=403, detail="Agent access required")
    return user
