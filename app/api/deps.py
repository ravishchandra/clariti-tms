from __future__ import annotations

import hashlib
from typing import Annotated

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models import ApiKey

DB = Annotated[AsyncSession, Depends(get_db)]


async def _get_api_key(
    db: DB,
    x_api_key: str = Header(..., alias="X-API-Key"),
) -> ApiKey:
    key_hash = hashlib.sha256(x_api_key.encode()).hexdigest()
    result = await db.execute(select(ApiKey).where(ApiKey.key_hash == key_hash))
    api_key = result.scalar_one_or_none()
    if api_key is None or not api_key.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or revoked API key")
    return api_key


CurrentKey = Annotated[ApiKey, Depends(_get_api_key)]
