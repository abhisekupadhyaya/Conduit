"""App-managed JWT (AD8) — no Cognito.

Sessions are stay-scoped for guests and role-scoped for staff. Token carries
the actor id + role; ambient {room, section} is resolved per-request from the
active stay (D3a/D20/D29), never trusted from the token.
"""
from __future__ import annotations

import datetime as dt
from typing import Any

import jwt

from conduit.core.config import get_settings
from conduit.core.exceptions import AuthError

Role = str  # "guest" | "servicer" | "supervisor" | "duty_manager"


def issue_token(*, subject: str, role: Role) -> str:
    s = get_settings()
    now = dt.datetime.now(tz=dt.UTC)
    payload = {
        "sub": subject,
        "role": role,
        "iat": now,
        "exp": now + dt.timedelta(minutes=s.jwt_ttl_minutes),
    }
    return jwt.encode(payload, s.jwt_secret, algorithm=s.jwt_alg)


def decode_token(token: str) -> dict[str, Any]:
    s = get_settings()
    try:
        return jwt.decode(token, s.jwt_secret, algorithms=[s.jwt_alg])
    except jwt.PyJWTError as e:  # pragma: no cover - thin wrapper
        raise AuthError("invalid or expired session") from e


from fastapi import Response
from passlib.hash import bcrypt

_BCRYPT_MAX = 72


def _clamp(pw: str) -> bytes:
    return pw.encode("utf-8")[:_BCRYPT_MAX]


def hash_password(pw: str) -> str:
    return bcrypt.hash(_clamp(pw))


def verify_password(pw: str, hashed: str) -> bool:
    try:
        return bcrypt.verify(_clamp(pw), hashed)
    except ValueError:
        return False


def set_session_cookie(resp: Response, token: str) -> None:
    s = get_settings()
    resp.set_cookie(
        key=s.cookie_name,
        value=token,
        httponly=True,
        secure=s.cookie_secure,
        samesite=s.cookie_samesite,
        path="/",
        max_age=s.jwt_ttl_minutes * 60,
    )


def clear_session_cookie(resp: Response) -> None:
    s = get_settings()
    resp.delete_cookie(key=s.cookie_name, path="/")
