from pydantic import BaseModel


class PackageOut(BaseModel):
    id: int
    slug: str
    name: str
    price_myr: int
    monthly_token_quota: int
    max_bots: int
    features: list[str] = []
    is_active: bool
    sort_order: int

    class Config:
        from_attributes = True


class PackageUpsert(BaseModel):
    slug: str
    name: str
    price_myr: int = 0
    monthly_token_quota: int = 0
    max_bots: int = 1
    features: list[str] = []
    is_active: bool = True
    sort_order: int = 0


class SubscriptionOut(BaseModel):
    plan: str
    plan_name: str
    status: str
    tokens_used: int
    tokens_quota: int
    tokens_remaining: int
    max_bots: int
    period_start: str | None = None


class SubscribeRequest(BaseModel):
    package_slug: str


class ClientRow(BaseModel):
    organization_id: int
    organization_name: str
    owner_email: str | None = None
    plan: str
    tokens_used: int
    tokens_quota: int
    bots: int
    created_at: str | None = None
