from datetime import datetime, timezone
from typing import Any
from uuid import UUID, uuid4

from app.core.config import get_settings
from app.core.security import create_access_token, create_refresh_token, decode_token


settings = get_settings()


class AuthTokenService:
    def __init__(self, redis_client: Any):
        self.redis = redis_client

    @staticmethod
    def _active_refresh_key(subject: str) -> str:
        return f"auth:refresh:active:{subject}"

    @staticmethod
    def _revoked_access_key(jti: str) -> str:
        return f"auth:access:revoked:{jti}"

    @staticmethod
    def _remaining_seconds(payload: dict) -> int:
        exp = payload.get("exp")
        if not isinstance(exp, (int, float)):
            return 1
        seconds = int(exp - datetime.now(timezone.utc).timestamp())
        return max(1, seconds)

    @staticmethod
    def _safe_subject(payload: dict) -> str | None:
        subject = payload.get("sub")
        if not isinstance(subject, str):
            return None
        try:
            UUID(subject)
        except (TypeError, ValueError):
            return None
        return subject

    async def issue_token_pair(
        self, *, subject: str, extra: dict | None = None
    ) -> dict[str, str]:
        access_jti = str(uuid4())
        refresh_jti = str(uuid4())

        access_token = create_access_token(subject=subject, extra=extra, jti=access_jti)
        refresh_token = create_refresh_token(
            subject=subject, extra=extra, jti=refresh_jti
        )

        refresh_ttl = settings.refresh_token_expiration_days * 24 * 60 * 60
        await self.redis.set(
            self._active_refresh_key(subject),
            refresh_jti,
            ex=refresh_ttl,
        )

        return {
            "access_token": access_token,
            "refresh_token": refresh_token,
            "token_type": "bearer",
        }

    async def rotate_refresh_token(self, refresh_token: str) -> dict[str, str] | None:
        payload = decode_token(refresh_token)
        if payload is None or payload.get("token_type") != "refresh":
            return None

        subject = self._safe_subject(payload)
        jti = payload.get("jti")
        if subject is None or not isinstance(jti, str):
            return None

        active_key = self._active_refresh_key(subject)
        active_jti = await self.redis.get(active_key)
        if isinstance(active_jti, bytes):
            active_jti = active_jti.decode()
        if active_jti != jti:
            return None

        extras = {
            key: value
            for key, value in payload.items()
            if key not in {"sub", "exp", "iat", "nbf", "token_type", "jti"}
        }
        return await self.issue_token_pair(
            subject=subject, extra=extras if extras else None
        )

    async def revoke_access_token(self, access_token: str) -> bool:
        payload = decode_token(access_token)
        if payload is None or payload.get("token_type") != "access":
            return False
        return await self.revoke_access_payload(payload)

    async def revoke_access_payload(self, payload: dict) -> bool:
        jti = payload.get("jti")
        if not isinstance(jti, str):
            return False

        await self.redis.set(
            self._revoked_access_key(jti),
            "1",
            ex=self._remaining_seconds(payload),
        )
        return True

    async def is_access_token_revoked(self, access_token: str) -> bool:
        payload = decode_token(access_token)
        if payload is None or payload.get("token_type") != "access":
            return False
        return await self.is_access_payload_revoked(payload)

    async def is_access_payload_revoked(self, payload: dict) -> bool:
        jti = payload.get("jti")
        if not isinstance(jti, str):
            return True

        revoked = await self.redis.get(self._revoked_access_key(jti))
        if isinstance(revoked, bytes):
            return revoked == b"1"
        if isinstance(revoked, str):
            return revoked == "1"
        if isinstance(revoked, bool):
            return revoked
        if isinstance(revoked, int):
            return revoked == 1
        return False

    async def revoke_refresh_tokens_for_subject(self, subject: str) -> None:
        await self.redis.delete(self._active_refresh_key(subject))
