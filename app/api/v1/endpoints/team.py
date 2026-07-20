"""Staff management: an owner/admin provisions support-agent accounts.

Closes the gap where only owners could self-register — now the org owner (or an
admin) can create agent logins in-product, deactivate them, rename them, or reset
a password. Agents then sign in with username/password like anyone else."""
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.api.deps import get_org_admin
from app.core.security import get_password_hash
from app.core.settings import settings
from app.core import invites as invites_core
from app.models.user import User
from app.models.org_invite import OrgInvite
from app.schemas.team import AgentOut, AgentCreate, AgentUpdate
from app.schemas.invite import InviteCreate, InviteOut

router = APIRouter()

_ASSIGNABLE_ROLES = ("agent", "admin")


def _invite_out(inv: OrgInvite) -> InviteOut:
    return InviteOut(
        id=inv.id,
        code=inv.code,
        role=inv.role,
        max_uses=inv.max_uses,
        uses=inv.uses,
        expires_at=inv.expires_at,
        is_active=inv.is_active,
        created_at=inv.created_at,
        join_url=f"{settings.FRONTEND_URL}/join?code={inv.code}",
    )


@router.get("/agents", response_model=list[AgentOut])
def list_agents(db: Session = Depends(get_db), admin: User = Depends(get_org_admin)):
    """All staff accounts in the admin's organization."""
    return (
        db.query(User)
        .filter(User.organization_id == admin.organization_id)
        .order_by(User.id)
        .all()
    )


@router.post("/agents", response_model=AgentOut, status_code=201)
def create_agent(payload: AgentCreate, db: Session = Depends(get_db), admin: User = Depends(get_org_admin)):
    """Create a support-agent (or admin) login in the admin's org."""
    email = payload.email.strip().lower()
    # email is globally unique on users; check case-insensitively.
    if db.query(User).filter(func.lower(User.email) == email).first():
        raise HTTPException(status_code=409, detail="A user with that email already exists.")
    role = payload.role if payload.role in _ASSIGNABLE_ROLES else "agent"
    user = User(
        organization_id=admin.organization_id,
        email=email,
        full_name=(payload.full_name or "").strip() or None,
        hashed_password=get_password_hash(payload.password),
        role=role,
        is_active=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@router.patch("/agents/{user_id}", response_model=AgentOut)
def update_agent(user_id: int, payload: AgentUpdate, db: Session = Depends(get_db), admin: User = Depends(get_org_admin)):
    """Rename, change role, deactivate/reactivate, or reset an agent's password."""
    user = (
        db.query(User)
        .filter(User.id == user_id, User.organization_id == admin.organization_id)
        .first()
    )
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    if user.role == "owner":
        raise HTTPException(status_code=403, detail="The owner account can't be modified here.")

    if payload.full_name is not None:
        user.full_name = payload.full_name.strip() or None
    if payload.role is not None:
        if payload.role not in _ASSIGNABLE_ROLES:
            raise HTTPException(status_code=422, detail="role must be one of: agent, admin")
        user.role = payload.role
    if payload.is_active is not None:
        # Don't let an admin lock themselves out.
        if user.id == admin.id and not payload.is_active:
            raise HTTPException(status_code=400, detail="You can't deactivate your own account.")
        user.is_active = payload.is_active
    if payload.password:
        user.hashed_password = get_password_hash(payload.password)

    db.commit()
    db.refresh(user)
    return user


# ===== Invite codes (self-service org join) =====

@router.get("/invites", response_model=list[InviteOut])
def list_invites(db: Session = Depends(get_db), admin: User = Depends(get_org_admin)):
    """Active (unrevoked) invites for the admin's org, newest first."""
    rows = (
        db.query(OrgInvite)
        .filter(OrgInvite.organization_id == admin.organization_id, OrgInvite.is_active.is_(True))
        .order_by(OrgInvite.id.desc())
        .all()
    )
    return [_invite_out(i) for i in rows]


@router.post("/invites", response_model=InviteOut, status_code=201)
def create_invite(payload: InviteCreate, db: Session = Depends(get_db), admin: User = Depends(get_org_admin)):
    """Mint a shareable join code. Role capped to agent|admin; default single-use + 7-day expiry."""
    role = payload.role if payload.role in _ASSIGNABLE_ROLES else "agent"
    expires_at = None
    if payload.expires_in_hours:
        expires_at = datetime.utcnow() + timedelta(hours=payload.expires_in_hours)
    inv = OrgInvite(
        organization_id=admin.organization_id,
        code=invites_core.gen_code(),
        role=role,
        created_by_user_id=admin.id,
        max_uses=payload.max_uses,
        uses=0,
        expires_at=expires_at,
        is_active=True,
    )
    db.add(inv)
    db.commit()
    db.refresh(inv)
    return _invite_out(inv)


@router.delete("/invites/{invite_id}", status_code=204)
def revoke_invite(invite_id: int, db: Session = Depends(get_db), admin: User = Depends(get_org_admin)):
    """Revoke an invite (deactivate; existing joined users are unaffected)."""
    inv = (
        db.query(OrgInvite)
        .filter(OrgInvite.id == invite_id, OrgInvite.organization_id == admin.organization_id)
        .first()
    )
    if inv is None:
        raise HTTPException(status_code=404, detail="Invite not found")
    inv.is_active = False
    db.commit()
