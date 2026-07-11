from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.api.deps import get_platform_admin
from app.core import config_store, models_catalog, billing
from app.models.user import User
from app.models.organization import Organization
from app.models.bot import Bot
from app.models.subscription import Subscription
from app.models.package import Package
from app.schemas.setting import SettingsUpdate, SettingsOut
from app.schemas.billing import PackageOut, PackageUpsert, ClientRow, SubscribeRequest

router = APIRouter()


def _hint(value: str) -> str | None:
    if not value:
        return None
    return "…" + value[-4:] if len(value) > 4 else "…"


@router.get("/settings", response_model=SettingsOut)
def get_settings(db: Session = Depends(get_db), admin: User = Depends(get_platform_admin)):
    """Current platform config. Secrets are never returned in full — only set/hint."""
    ork = config_store.get("OPENROUTER_API_KEY")
    voy = config_store.get("VOYAGE_API_KEY")
    return SettingsOut(
        openrouter_api_key_set=bool(ork),
        openrouter_api_key_hint=_hint(ork),
        voyage_api_key_set=bool(voy),
        voyage_api_key_hint=_hint(voy),
        openrouter_base_url=config_store.get("OPENROUTER_BASE_URL") or "https://openrouter.ai/api/v1",
        default_chat_model=models_catalog.default_model(),
    )


@router.put("/settings", response_model=SettingsOut)
def update_settings(
    payload: SettingsUpdate,
    db: Session = Depends(get_db),
    admin: User = Depends(get_platform_admin),
):
    """Store provided keys. Blank/omitted fields are left unchanged."""
    field_to_key = {
        "openrouter_api_key": "OPENROUTER_API_KEY",
        "voyage_api_key": "VOYAGE_API_KEY",
        "openrouter_base_url": "OPENROUTER_BASE_URL",
        "default_chat_model": "DEFAULT_CHAT_MODEL",
    }
    updates: dict[str, str] = {}
    for field, key in field_to_key.items():
        value = getattr(payload, field)
        if value is not None and value.strip() != "":
            updates[key] = value.strip()
    if updates:
        config_store.set_many(db, updates)
    return get_settings(db=db, admin=admin)


# ===== Packages (the products the operator sells) =====

@router.get("/packages", response_model=list[PackageOut])
def list_packages(db: Session = Depends(get_db), admin: User = Depends(get_platform_admin)):
    return db.query(Package).order_by(Package.sort_order, Package.price_myr).all()


@router.post("/packages", response_model=PackageOut, status_code=201)
def create_package(payload: PackageUpsert, db: Session = Depends(get_db), admin: User = Depends(get_platform_admin)):
    if db.query(Package).filter(Package.slug == payload.slug).first():
        raise HTTPException(status_code=400, detail="A package with that slug already exists")
    pkg = Package(**payload.model_dump())
    db.add(pkg)
    db.commit()
    db.refresh(pkg)
    return pkg


@router.put("/packages/{package_id}", response_model=PackageOut)
def update_package(package_id: int, payload: PackageUpsert, db: Session = Depends(get_db), admin: User = Depends(get_platform_admin)):
    pkg = db.query(Package).filter(Package.id == package_id).first()
    if not pkg:
        raise HTTPException(status_code=404, detail="Package not found")
    for k, v in payload.model_dump().items():
        setattr(pkg, k, v)
    db.commit()
    db.refresh(pkg)
    return pkg


@router.delete("/packages/{package_id}", status_code=204)
def delete_package(package_id: int, db: Session = Depends(get_db), admin: User = Depends(get_platform_admin)):
    pkg = db.query(Package).filter(Package.id == package_id).first()
    if not pkg:
        raise HTTPException(status_code=404, detail="Package not found")
    # Refuse to orphan subscribers (plan is referenced by slug, not FK). Deactivate
    # instead of deleting so their quota/limits keep resolving.
    in_use = db.query(Subscription).filter(Subscription.plan == pkg.slug).count()
    if in_use:
        raise HTTPException(
            status_code=400,
            detail=f"{in_use} client(s) are on this package. Set it inactive instead of deleting.",
        )
    db.delete(pkg)
    db.commit()


# ===== Clients (every organization + its plan/usage) =====

@router.get("/clients", response_model=list[ClientRow])
def list_clients(db: Session = Depends(get_db), admin: User = Depends(get_platform_admin)):
    orgs = db.query(Organization).order_by(Organization.id.desc()).all()
    subs = {s.organization_id: s for s in db.query(Subscription).all()}
    quotas = {p.slug: p.monthly_token_quota for p in db.query(Package).all()}
    # one owner email per org
    owners = {
        u.organization_id: u.email
        for u in db.query(User).filter(User.role == "owner").order_by(User.id).all()
    }
    bot_counts = dict(
        db.query(Bot.organization_id, func.count(Bot.id)).group_by(Bot.organization_id).all()
    )
    rows = []
    for org in orgs:
        sub = subs.get(org.id)
        plan = sub.plan if sub else "free"
        rows.append(
            ClientRow(
                organization_id=org.id,
                organization_name=org.name,
                owner_email=owners.get(org.id),
                plan=plan,
                tokens_used=(sub.tokens_used if sub else 0) or 0,
                tokens_quota=quotas.get(plan, 0),
                bots=bot_counts.get(org.id, 0),
                created_at=org.created_at.isoformat() if org.created_at else None,
            )
        )
    return rows


@router.put("/clients/{organization_id}/plan", response_model=ClientRow)
def set_client_plan(
    organization_id: int,
    payload: SubscribeRequest,
    db: Session = Depends(get_db),
    admin: User = Depends(get_platform_admin),
):
    """Operator manually assigns a plan to a client (used while online payment is off)."""
    org = db.query(Organization).filter(Organization.id == organization_id).first()
    if not org:
        raise HTTPException(status_code=404, detail="Client not found")
    pkg = billing.package_for(db, payload.package_slug)
    if not pkg:
        raise HTTPException(status_code=404, detail="Package not found")
    sub = billing.subscribe(db, organization_id, pkg)
    owner = db.query(User).filter(User.organization_id == organization_id, User.role == "owner").first()
    bots = db.query(func.count(Bot.id)).filter(Bot.organization_id == organization_id).scalar() or 0
    return ClientRow(
        organization_id=org.id,
        organization_name=org.name,
        owner_email=owner.email if owner else None,
        plan=sub.plan,
        tokens_used=sub.tokens_used or 0,
        tokens_quota=pkg.monthly_token_quota,
        bots=bots,
        created_at=org.created_at.isoformat() if org.created_at else None,
    )
