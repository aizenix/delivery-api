import re
from typing import Annotated

from pydantic import AfterValidator, BaseModel, ConfigDict, Field

from app.models import Role


def normalize_phone(value: str) -> str:
    phone = re.sub(r"[\s\-()]", "", value)
    if phone.startswith("998"):
        phone = "+" + phone
    # [0-9], not \d: \d also matches non-ASCII digits like Arabic-Indic ones
    if not re.fullmatch(r"\+998[0-9]{9}", phone):
        raise ValueError("expected an Uzbek number like +998901234567")
    return phone


Phone = Annotated[str, AfterValidator(normalize_phone)]


class OTPRequest(BaseModel):
    phone: Phone


class OTPVerify(BaseModel):
    phone: Phone
    code: str = Field(pattern=r"^[0-9]{6}$")


class RefreshRequest(BaseModel):
    refresh_token: str


class TokenPair(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    phone: str
    name: str | None
    role: Role
