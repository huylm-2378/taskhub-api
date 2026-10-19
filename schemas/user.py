from uuid import uuid4

from pydantic import ConfigDict, EmailStr, Field, SecretStr, field_validator

from schemas.base import InputSchema, ReadSchema
from models.user import UserRole


class UserCreate(InputSchema):
    name: str = Field(min_length=1, max_length=100)
    email: EmailStr = Field(max_length=254)
    username: str = Field(
        default_factory=lambda: f"user_{uuid4().hex}",
        min_length=3, max_length=64, pattern=r"^[a-z0-9_]+$",
    )

    @field_validator("username", mode="before")
    @classmethod
    def normalize_username(cls, value):
        return value.strip().lower() if isinstance(value, str) else value


class UserRead(ReadSchema):
    name: str
    email: EmailStr
    username: str
    is_active: bool
    role: UserRole


class UserRegister(UserCreate):
    # InputSchema trims ordinary text; passwords must retain their exact bytes.
    model_config = ConfigDict(str_strip_whitespace=False)

    password: SecretStr = Field(min_length=8, max_length=72)

    @field_validator("name", "email", mode="before")
    @classmethod
    def strip_profile_text(cls, value):
        return value.strip() if isinstance(value, str) else value

    @field_validator("password")
    @classmethod
    def validate_password_bytes(cls, value: SecretStr) -> SecretStr:
        if len(value.get_secret_value().encode("utf-8")) > 72:
            raise ValueError("Password must not exceed 72 UTF-8 bytes")
        return value


class UserUpdate(InputSchema):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    email: EmailStr | None = Field(default=None, max_length=254)
    username: str | None = Field(default=None, min_length=3, max_length=64, pattern=r"^[a-z0-9_]+$")

    @field_validator("username", mode="before")
    @classmethod
    def normalize_username(cls, value):
        return UserCreate.normalize_username(value)

    @field_validator("name", "email", "username")
    @classmethod
    def reject_null_fields(cls, value):
        if value is None:
            raise ValueError("Field cannot be null")
        return value
