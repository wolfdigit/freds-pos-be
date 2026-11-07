from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class AuthUserDto(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: str
    email: str
    name: str
    role: str


class AuthStateDto(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    expires_at: datetime = Field(..., alias="expiresAt")
    store_selected: bool = Field(..., alias="storeSelected")
    store_name: Optional[str] = Field(None, alias="storeName")
    user: AuthUserDto


class AuthLoginDto(AuthStateDto):
    token: str
    token_type: str = Field("Bearer", alias="tokenType")


class GoogleLoginRequest(BaseModel):
    credential: str = Field(..., min_length=1, max_length=8192)


class SelectStoreRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    store_name: str = Field(..., alias="storeName", min_length=1, max_length=128)


class LogoutDto(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    logged_out: bool = Field(True, alias="loggedOut")
