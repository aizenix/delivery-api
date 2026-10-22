import hmac
import secrets
import time
import uuid
from datetime import UTC, datetime, timedelta

import jwt
from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app import tasks
from app.config import settings
from app.errors import AppError, Forbidden, TooManyRequests, Unauthorized
from app.models import User
from app.schemas.auth import TokenPair

ALGORITHM = "HS256"


async def request_otp(redis: Redis, phone: str) -> None:
    cooldown_key = f"otp:cooldown:{phone}"
    # SET NX doubles as the rate limit: it fails until the resend window expires
    if not await redis.set(cooldown_key, 1, nx=True, ex=settings.otp_resend_seconds):
        retry_after = max(await redis.ttl(cooldown_key), 1)
        raise TooManyRequests(
            f"code already sent, retry in {retry_after}s", headers={"Retry-After": str(retry_after)}
        )

    code = f"{secrets.randbelow(10**6):06d}"
    async with redis.pipeline(transaction=True) as pipe:
        pipe.set(f"otp:code:{phone}", code, ex=settings.otp_ttl_seconds)
        pipe.delete(f"otp:attempts:{phone}")
        await pipe.execute()

    tasks.send_sms.delay(phone, f"Delivery code: {code}")


async def verify_otp(session: AsyncSession, redis: Redis, phone: str, code: str) -> User:
    code_key = f"otp:code:{phone}"
    attempts_key = f"otp:attempts:{phone}"

    expected = await redis.get(code_key)
    if expected is None:
        raise AppError("code expired or was not requested")

    attempts = await redis.incr(attempts_key)
    if attempts == 1:
        await redis.expire(attempts_key, settings.otp_ttl_seconds)
    if attempts > settings.otp_max_attempts:
        await redis.delete(code_key, attempts_key)
        raise TooManyRequests("too many attempts, request a new code")

    if not hmac.compare_digest(expected, code):
        raise AppError("invalid code")
    await redis.delete(code_key, attempts_key)

    user = await session.scalar(select(User).where(User.phone == phone))
    if user is None:
        user = User(phone=phone)
        session.add(user)
        await session.commit()
    elif not user.is_active:
        raise Forbidden("account is disabled")
    return user


def create_tokens(user_id: int) -> TokenPair:
    now = datetime.now(UTC)
    access = {
        "sub": str(user_id),
        "type": "access",
        "iat": now,
        "exp": now + timedelta(minutes=settings.access_token_minutes),
    }
    refresh = {
        "sub": str(user_id),
        "type": "refresh",
        "jti": uuid.uuid4().hex,
        "iat": now,
        "exp": now + timedelta(days=settings.refresh_token_days),
    }
    return TokenPair(
        access_token=jwt.encode(access, settings.jwt_secret, ALGORITHM),
        refresh_token=jwt.encode(refresh, settings.jwt_secret, ALGORITHM),
    )


def decode_token(token: str, token_type: str) -> dict:
    payload = jwt.decode(
        token,
        settings.jwt_secret,
        algorithms=[ALGORITHM],
        options={"require": ["exp", "sub", "type"]},
    )
    if payload["type"] != token_type:
        raise jwt.InvalidTokenError(f"expected {token_type} token")
    return payload


async def refresh_tokens(session: AsyncSession, redis: Redis, refresh_token: str) -> TokenPair:
    try:
        payload = decode_token(refresh_token, "refresh")
    except jwt.PyJWTError:
        raise Unauthorized("invalid refresh token") from None

    # refresh tokens are single use; a second use of the same jti means it leaked
    ttl = max(payload["exp"] - int(time.time()), 1)
    if not await redis.set(f"refresh:used:{payload['jti']}", 1, nx=True, ex=ttl):
        raise Unauthorized("refresh token already used")

    user = await session.get(User, int(payload["sub"]))
    if user is None or not user.is_active:
        raise Unauthorized("invalid refresh token")
    return create_tokens(user.id)
