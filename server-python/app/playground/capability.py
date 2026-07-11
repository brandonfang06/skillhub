from __future__ import annotations

import base64
import binascii
from datetime import UTC, datetime
import hashlib
import hmac
import json
from uuid import uuid4


class CapabilityError(ValueError):
    pass


def _encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def _decode(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def issue_capability(
    *,
    secret: str,
    issuer: str,
    audience: str,
    subject: str,
    namespace: str,
    slug: str,
    version: str,
    ttl_seconds: int,
    now: datetime | None = None,
    token_id: str | None = None,
) -> str:
    issued_at = now or datetime.now(UTC)
    issued_at_seconds = int(issued_at.timestamp())
    claims = {
        "iss": issuer,
        "aud": audience,
        "sub": subject,
        "namespace": namespace,
        "slug": slug,
        "version": version,
        "scope": "playground:read",
        "iat": issued_at_seconds,
        "exp": issued_at_seconds + ttl_seconds,
        "jti": token_id or str(uuid4()),
    }
    payload = _encode(
        json.dumps(
            claims,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
    )
    signature = _sign(payload, secret)
    return f"{payload}.{signature}"


def verify_capability(
    token: str,
    *,
    secret: str,
    issuer: str,
    audience: str,
    now: datetime | None = None,
) -> dict[str, object]:
    try:
        payload, signature = token.split(".", 1)
        if not hmac.compare_digest(signature, _sign(payload, secret)):
            raise CapabilityError("invalid signature")
        claims = json.loads(_decode(payload).decode("utf-8"))
    except CapabilityError:
        raise
    except (
        ValueError,
        UnicodeDecodeError,
        json.JSONDecodeError,
        binascii.Error,
    ) as exc:
        raise CapabilityError("invalid capability") from exc

    if not isinstance(claims, dict):
        raise CapabilityError("invalid claims")
    if (
        claims.get("iss") != issuer
        or claims.get("aud") != audience
        or claims.get("scope") != "playground:read"
    ):
        raise CapabilityError("invalid claims")
    for name in ("sub", "namespace", "slug", "version", "jti"):
        if not isinstance(claims.get(name), str) or not claims[name]:
            raise CapabilityError("invalid claims")

    try:
        expires_at = int(claims["exp"])
    except (KeyError, TypeError, ValueError) as exc:
        raise CapabilityError("invalid claims") from exc
    current = int((now or datetime.now(UTC)).timestamp())
    if expires_at <= current:
        raise CapabilityError("expired capability")
    return claims


def _sign(payload: str, secret: str) -> str:
    return _encode(
        hmac.new(
            secret.encode("utf-8"),
            payload.encode("ascii"),
            hashlib.sha256,
        ).digest()
    )
