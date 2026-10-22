from typing import Annotated

import jwt
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_redis, get_session
from app.models import Role, User
from app.services.auth import decode_token

SessionDep = Annotated[AsyncSession, Depends(get_session)]
RedisDep = Annotated[Redis, Depends(get_redis)]

bearer = HTTPBearer(auto_error=False)


def _unauthorized(detail: str) -> HTTPException:
    return HTTPException(401, detail, headers={"WWW-Authenticate": "Bearer"})


async def get_current_user(
    session: SessionDep,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
) -> User:
    if credentials is None:
        raise _unauthorized("not authenticated")
    try:
        payload = decode_token(credentials.credentials, "access")
    except jwt.PyJWTError:
        raise _unauthorized("invalid token") from None

    user = await session.get(User, int(payload["sub"]))
    if user is None or not user.is_active:
        raise _unauthorized("invalid token")
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


def require_role(*roles: Role):
    async def check(user: CurrentUser) -> User:
        if user.role not in roles:
            raise HTTPException(403, "not allowed")
        return user

    return check


CourierUser = Annotated[User, Depends(require_role(Role.courier))]
AdminUser = Annotated[User, Depends(require_role(Role.admin))]
