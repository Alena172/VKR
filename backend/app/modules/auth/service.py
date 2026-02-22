from datetime import datetime, timedelta, timezone

import jwt

from app.core.config import get_settings


class AuthService:
    def __init__(self) -> None:
        settings = get_settings()
        self._secret = settings.jwt_secret
        self._issuer = settings.jwt_issuer
        self._ttl_minutes = settings.jwt_access_ttl_minutes
        self._algorithm = "HS256"

    def create_access_token(self, user_id: int) -> str:
        now = datetime.now(timezone.utc)
        payload = {
            "sub": str(user_id),
            "iat": int(now.timestamp()),
            "exp": int((now + timedelta(minutes=self._ttl_minutes)).timestamp()),
            "iss": self._issuer,
        }
        return jwt.encode(payload, self._secret, algorithm=self._algorithm)

    def verify_token(self, token: str) -> int | None:
        try:
            payload = jwt.decode(
                token,
                self._secret,
                algorithms=[self._algorithm],
                issuer=self._issuer,
            )
        except Exception:
            return None

        user_id = payload.get("sub")
        if not user_id:
            return None
        try:
            return int(user_id)
        except ValueError:
            return None


auth_service = AuthService()
