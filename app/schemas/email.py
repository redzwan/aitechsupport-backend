from pydantic import BaseModel, EmailStr


class SMTPSettingsOut(BaseModel):
    host: str
    port: int
    username: str
    password_set: bool
    from_email: str
    from_name: str
    security: str  # tls | ssl | none
    enabled: bool


class SMTPSettingsUpdate(BaseModel):
    host: str | None = None
    port: int | None = None
    username: str | None = None
    password: str | None = None  # blank -> keep existing
    from_email: str | None = None
    from_name: str | None = None
    security: str | None = None
    enabled: bool | None = None


class TestEmailRequest(BaseModel):
    to_email: EmailStr


class EmailTemplateOut(BaseModel):
    id: int
    key: str
    name: str
    subject: str
    body_html: str
    is_active: bool

    class Config:
        from_attributes = True


class EmailTemplateUpdate(BaseModel):
    subject: str | None = None
    body_html: str | None = None
    is_active: bool | None = None
