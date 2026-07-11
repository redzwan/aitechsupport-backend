from pydantic import BaseModel, EmailStr


class RegisterRequest(BaseModel):
    organization_name: str
    email: EmailStr
    password: str
    full_name: str | None = None


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserProfile(BaseModel):
    id: int
    organization_id: int
    email: EmailStr
    full_name: str | None = None
    role: str
    is_platform_admin: bool = False

    class Config:
        from_attributes = True


class UpdateProfileRequest(BaseModel):
    full_name: str | None = None


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str
