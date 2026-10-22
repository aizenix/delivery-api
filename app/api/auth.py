from fastapi import APIRouter

from app.api.deps import CurrentUser, RedisDep, SessionDep
from app.schemas.auth import OTPRequest, OTPVerify, RefreshRequest, TokenPair, UserOut
from app.services import auth

router = APIRouter(tags=["auth"])


@router.post("/auth/otp/request", status_code=202)
async def request_otp(data: OTPRequest, redis: RedisDep) -> dict:
    await auth.request_otp(redis, data.phone)
    return {"detail": "code sent"}


@router.post("/auth/otp/verify")
async def verify_otp(data: OTPVerify, session: SessionDep, redis: RedisDep) -> TokenPair:
    user = await auth.verify_otp(session, redis, data.phone, data.code)
    return auth.create_tokens(user.id)


@router.post("/auth/refresh")
async def refresh(data: RefreshRequest, session: SessionDep, redis: RedisDep) -> TokenPair:
    return await auth.refresh_tokens(session, redis, data.refresh_token)


@router.get("/users/me")
async def me(user: CurrentUser) -> UserOut:
    return UserOut.model_validate(user)
