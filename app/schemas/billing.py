from pydantic import BaseModel, model_validator


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
    model_provider: str
    chat_model: str | None = None
    self_hosted_base_url: str | None = None

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
    model_provider: str = "openrouter"
    chat_model: str | None = None
    self_hosted_base_url: str | None = None

    @model_validator(mode="after")
    def _validate_model_provider(self) -> "PackageUpsert":
        if self.model_provider not in ("self_hosted", "openrouter"):
            raise ValueError("model_provider must be 'self_hosted' or 'openrouter'")
        if self.model_provider == "self_hosted" and not (self.self_hosted_base_url or "").strip():
            raise ValueError("self_hosted_base_url is required when model_provider is 'self_hosted'")
        return self


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


class CheckoutOut(BaseModel):
    """Result of POST /billing/checkout.

    - Paid plan: `payment_url` is the Billplz page to redirect the browser to;
      the plan activates via webhook after payment.
    - Free plan / downgrade: `subscription` is the already-applied plan and
      `payment_url` is null (no payment needed).
    """
    payment_url: str | None = None
    bill_id: str | None = None
    subscription: SubscriptionOut | None = None


class ClientRow(BaseModel):
    organization_id: int
    organization_name: str
    owner_email: str | None = None
    plan: str
    tokens_used: int
    tokens_quota: int
    bots: int
    created_at: str | None = None


class PaymentRow(BaseModel):
    id: int
    organization_id: int
    organization_name: str | None = None
    plan_slug: str
    amount_cents: int
    status: str
    sandbox: bool
    billplz_bill_id: str | None = None
    paid_at: str | None = None
    created_at: str | None = None


class PaymentsSummary(BaseModel):
    total: int
    paid: int
    pending: int
    failed: int
    live_revenue_cents: int  # sum of paid, non-sandbox bills


class PaymentsOut(BaseModel):
    summary: PaymentsSummary
    payments: list[PaymentRow]


class BillplzSettingsOut(BaseModel):
    """Billplz gateway config for the admin panel. Secret keys are never returned
    in full — only whether they're set + a last-4 hint."""
    enabled: bool
    sandbox: bool
    api_key_set: bool
    api_key_hint: str | None = None
    x_signature_key_set: bool
    x_signature_key_hint: str | None = None
    collection_id: str
    configured: bool  # enabled + api key + collection all present


class BillplzSettingsUpdate(BaseModel):
    """Admin submits fields to store. Omit or leave a secret blank to keep it."""
    enabled: bool | None = None
    sandbox: bool | None = None
    api_key: str | None = None            # blank -> keep existing
    x_signature_key: str | None = None    # blank -> keep existing
    collection_id: str | None = None
