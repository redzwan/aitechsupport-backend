from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.core.security import verify_password, get_password_hash, create_access_token
from app.api.deps import get_current_user
from app.models.organization import Organization
from app.models.user import User
from app.schemas.auth import RegisterRequest, Token, UserProfile

router = APIRouter()


def _slugify(name: str) -> str:
    return "".join(c.lower() if c.isalnum() else "-" for c in name).strip("-")


@router.post("/register", response_model=Token, status_code=201)
def register(payload: RegisterRequest, db: Session = Depends(get_db)) -> Token:
    if db.query(User).filter(User.email == payload.email).first():
        raise HTTPException(status_code=400, detail="Email already registered")

    org = Organization(name=payload.organization_name, slug=_slugify(payload.organization_name))
    db.add(org)
    db.flush()  # assign org.id before creating the user

    user = User(
        organization_id=org.id,
        email=payload.email,
        hashed_password=get_password_hash(payload.password),
        full_name=payload.full_name,
        role="owner",
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    token = create_access_token({"sub": str(user.id), "org": org.id})
    return Token(access_token=token)


@router.post("/login", response_model=Token)
def login(form: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)) -> Token:
    user = db.query(User).filter(User.email == form.username).first()
    if not user or not verify_password(form.password, user.hashed_password):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Incorrect email or password")
    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Account is inactive")
    token = create_access_token({"sub": str(user.id), "org": user.organization_id})
    return Token(access_token=token)


@router.get("/me", response_model=UserProfile)
def me(current_user: User = Depends(get_current_user)) -> User:
    return current_user
