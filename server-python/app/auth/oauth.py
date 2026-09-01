from __future__ import annotations

from datetime import UTC, datetime
from ipaddress import IPv6Address, ip_address
import json
import os
import re
import uuid
from typing import Any
from urllib.parse import urlsplit

import httpx
from sqlalchemy import text

from app.core.public_url import resolve_public_base_url

DEFAULT_USER_ROLE = "USER"
MAX_GITHUB_EMAIL_RESPONSE_BYTES = 1024 * 1024


def _is_safe_github_email_api_uri(uri: str) -> bool:
    try:
        parsed = urlsplit(uri)
        _ = parsed.port
    except ValueError:
        return False
    if not (
        parsed.scheme == "https"
        and parsed.hostname is not None
        and parsed.username is None
        and parsed.password is None
        and parsed.query == ""
        and parsed.fragment == ""
    ):
        return False

    hostname = parsed.hostname.lower()
    if hostname == "localhost" or hostname.endswith(".localhost"):
        return False
    if hostname in {
        "metadata.google.internal",
        "metadata.google",
        "metadata.azure.internal",
    }:
        return False
    try:
        address = ip_address(hostname)
    except ValueError:
        return True
    addresses = [address]
    if isinstance(address, IPv6Address) and address.ipv4_mapped is not None:
        addresses.append(address.ipv4_mapped)
    return not any(
        candidate.is_loopback
        or candidate.is_link_local
        or candidate.is_multicast
        or candidate.is_reserved
        or candidate.is_unspecified
        for candidate in addresses
    )


def oauth_registrations_from_env() -> list[dict[str, object]]:
    return _spring_oidc_registrations(resolve_public_base_url())


def _spring_oidc_registrations(public_base_url: str) -> list[dict[str, object]]:
    prefix = "SPRING_SECURITY_OAUTH2_CLIENT_REGISTRATION_"
    suffix = "_CLIENT_ID"
    registration_names = sorted(
        key[len(prefix) : -len(suffix)]
        for key in os.environ
        if key.startswith(prefix) and key.endswith(suffix)
    )
    registrations: list[dict[str, object]] = []
    for name in registration_names:
        registration_id = _spring_env_id(name)
        provider_name = os.getenv(f"{prefix}{name}_PROVIDER", name).upper()
        provider_prefix = f"SPRING_SECURITY_OAUTH2_CLIENT_PROVIDER_{provider_name}_"
        issuer_uri = os.getenv(f"{provider_prefix}ISSUER_URI", "").rstrip("/")
        redirect_template = os.getenv(
            f"{prefix}{name}_REDIRECT_URI",
            "{baseUrl}/login/oauth2/code/{registrationId}",
        )
        scopes = _split_scopes(os.getenv(f"{prefix}{name}_SCOPE", "openid,profile,email"))
        registration = {
            "id": registration_id,
            "clientName": os.getenv(f"{prefix}{name}_CLIENT_NAME", registration_id.title()),
            "clientId": os.getenv(f"{prefix}{name}_CLIENT_ID", "placeholder"),
            "clientSecret": os.getenv(f"{prefix}{name}_CLIENT_SECRET", "placeholder"),
            "authorizationUri": os.getenv(
                f"{provider_prefix}AUTHORIZATION_URI",
                f"{issuer_uri}/protocol/openid-connect/auth" if issuer_uri else "",
            ),
            "tokenUri": os.getenv(
                f"{provider_prefix}TOKEN_URI",
                f"{issuer_uri}/protocol/openid-connect/token" if issuer_uri else "",
            ),
            "userInfoUri": os.getenv(
                f"{provider_prefix}USER_INFO_URI",
                f"{issuer_uri}/protocol/openid-connect/userinfo" if issuer_uri else "",
            ),
            "redirectUri": _expand_redirect_uri(redirect_template, public_base_url, registration_id),
            "scopes": scopes,
            "userNameAttribute": os.getenv(f"{provider_prefix}USER_NAME_ATTRIBUTE", "sub"),
        }
        if registration_id == "github":
            github_api_base_url = os.getenv(
                "SKILLHUB_AUTH_GITHUB_API_BASE_URL",
                "https://api.github.com",
            ).rstrip("/")
            email_api_uri = f"{github_api_base_url}/user/emails"
            if not _is_safe_github_email_api_uri(email_api_uri):
                raise ValueError(
                    "SKILLHUB_AUTH_GITHUB_API_BASE_URL must be an HTTPS URL "
                    "without credentials, query, or fragment"
                )
            registration["emailApiUri"] = email_api_uri
        registrations.append(registration)
    return registrations


def _spring_env_id(name: str) -> str:
    return name.lower().replace("_", "-")


def _split_scopes(value: str) -> list[str]:
    scopes = [scope for scope in re.split(r"[,\s]+", value.strip()) if scope]
    return scopes or ["openid", "profile", "email"]


def _expand_redirect_uri(template: str, public_base_url: str, registration_id: str) -> str:
    return (
        template.replace("{baseUrl}", public_base_url)
        .replace("{registrationId}", registration_id)
        .replace("{baseScheme}", public_base_url.split("://", 1)[0])
    )


def configured_oauth_registration(registration: dict[str, object]) -> bool:
    required = ("authorizationUri", "clientId", "redirectUri")
    values = [str(registration.get(key) or "").strip() for key in required]
    return all(values) and values[1] != "placeholder"


def default_oauth_flow_configured(registration: dict[str, object]) -> bool:
    required = ("clientSecret", "tokenUri", "userInfoUri")
    values = [str(registration.get(key) or "").strip() for key in required]
    return configured_oauth_registration(registration) and all(values) and values[0] != "placeholder"


async def exchange_oauth_code(
    registration: dict[str, object],
    code: str,
    *,
    http_client_factory: Any = None,
) -> dict[str, object]:
    factory = http_client_factory or (
        lambda: httpx.AsyncClient(timeout=10.0, follow_redirects=False)
    )
    async with factory() as client:
        token_response = await client.post(
            str(registration["tokenUri"]),
            data={
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": str(registration["redirectUri"]),
                "client_id": str(registration["clientId"]),
                "client_secret": str(registration["clientSecret"]),
            },
            headers={"Accept": "application/json"},
        )
        token_response.raise_for_status()
        token_payload = token_response.json()
        access_token = str(token_payload.get("access_token") or "").strip()
        if access_token == "":
            raise ValueError("OAuth token response missing access_token")

        user_response = await client.get(
            str(registration["userInfoUri"]),
            headers={"Accept": "application/json", "Authorization": f"Bearer {access_token}"},
        )
        user_response.raise_for_status()
        attributes = user_response.json()

        if not isinstance(attributes, dict):
            raise ValueError("OAuth userinfo response must be an object")
        if str(registration["id"]) == "github":
            verified_email = await _read_github_verified_email(
                client,
                str(
                    registration.get("emailApiUri")
                    or "https://api.github.com/user/emails"
                ),
                access_token,
            )
            return _claims_from_attributes(
                "github",
                attributes,
                email=(
                    verified_email
                    if verified_email is not None
                    else attributes.get("email")
                ),
                email_verified=verified_email is not None,
            )

    return _claims_from_attributes(str(registration["id"]), attributes)


async def _read_github_verified_email(
    client: Any,
    email_api_uri: str,
    access_token: str,
) -> str | None:
    if not _is_safe_github_email_api_uri(email_api_uri):
        return None
    try:
        async with client.stream(
            "GET",
            email_api_uri,
            headers={
                "Accept": "application/json",
                "Authorization": f"Bearer {access_token}",
            },
        ) as response:
            if not 200 <= int(response.status_code) < 300:
                return None
            content_type = str(response.headers.get("content-type") or "")
            if (
                content_type.partition(";")[0].strip().lower()
                != "application/json"
            ):
                return None
            content = bytearray()
            async for chunk in response.aiter_bytes():
                if len(content) + len(chunk) > MAX_GITHUB_EMAIL_RESPONSE_BYTES:
                    return None
                content.extend(chunk)
        payload = json.loads(content)
    except (AttributeError, httpx.HTTPError, TypeError, ValueError):
        return None

    if not isinstance(payload, list):
        return None
    verified = [
        item
        for item in payload
        if isinstance(item, dict)
        and item.get("verified") is True
        and str(item.get("email") or "").strip()
    ]
    verified.sort(key=lambda item: item.get("primary") is True, reverse=True)
    if not verified:
        return None
    return str(verified[0]["email"]).strip()


def _claims_from_attributes(
    provider: str,
    attributes: dict[str, object],
    *,
    email: object | None = None,
    email_verified: bool | None = None,
) -> dict[str, object]:
    if provider == "gitlab":
        provider_login = str(attributes.get("username") or attributes.get("login") or "").strip()
        avatar_url = attributes.get("avatar_url") or attributes.get("avatarUrl") or ""
    elif provider in {"github"}:
        provider_login = str(attributes.get("login") or attributes.get("username") or "").strip()
        avatar_url = attributes.get("avatar_url") or attributes.get("avatarUrl") or ""
    else:
        provider_login = str(
            attributes.get("preferred_username")
            or attributes.get("name")
            or attributes.get("email")
            or attributes.get("login")
            or attributes.get("username")
            or attributes.get("sub")
            or ""
        ).strip()
        avatar_url = attributes.get("avatar_url") or attributes.get("avatarUrl") or ""
    subject = str(attributes.get("id") or attributes.get("sub") or "").strip()
    if subject == "" or provider_login == "":
        raise ValueError("OAuth userinfo response missing subject or login")
    resolved_email = attributes.get("email") if email is None else email
    if email_verified is None:
        if provider == "gitlab":
            confirmed_at = attributes.get("confirmed_at")
            email_verified = (
                isinstance(confirmed_at, str) and confirmed_at.strip() != ""
            )
        elif provider == "github":
            email_verified = False
        else:
            email_verified = attributes.get("email_verified") is True
    return {
        "provider": provider,
        "subject": subject,
        "providerLogin": provider_login,
        "email": resolved_email,
        "emailVerified": email_verified,
        "avatarUrl": avatar_url,
        "extra": attributes,
    }


async def bind_oauth_principal(engine: Any, registration: dict[str, object], claims: dict[str, object]) -> dict[str, object]:
    provider = str(registration["id"])
    subject = str(claims["subject"])
    provider_login = str(claims["providerLogin"])
    email = claims.get("email") if claims.get("emailVerified") is True else None
    avatar_url = claims.get("avatarUrl") or ""
    async with engine.begin() as connection:
        user = await _find_bound_user(connection, provider, subject)
        if user is None:
            user_id = f"usr_{uuid.uuid4()}"
            await connection.execute(
                text(
                    """
                    INSERT INTO user_account (id, display_name, email, avatar_url, status)
                    VALUES (:id, :display_name, :email, :avatar_url, :status)
                    """
                ),
                {
                    "id": user_id,
                    "display_name": provider_login,
                    "email": email,
                    "avatar_url": avatar_url,
                    "status": "ACTIVE",
                },
            )
            await connection.execute(
                text(
                    """
                    INSERT INTO identity_binding (user_id, provider_code, subject, login_name, extra_json)
                    VALUES (:user_id, :provider_code, :subject, :login_name, CAST(:extra_json AS jsonb))
                    """
                ),
                {
                    "user_id": user_id,
                    "provider_code": provider,
                    "subject": subject,
                    "login_name": provider_login,
                    "extra_json": json.dumps(claims.get("extra") or {}),
                },
            )
            await _ensure_global_namespace_membership(connection, user_id)
            user = {
                "id": user_id,
                "display_name": provider_login,
                "email": email,
                "avatar_url": avatar_url,
                "status": "ACTIVE",
            }
        else:
            _ensure_user_status_allows_login(user)
            persisted_email = email if email is not None else user.get("email")
            await connection.execute(
                text(
                    """
                    UPDATE user_account
                    SET display_name = :display_name,
                        email = :email,
                        avatar_url = :avatar_url,
                        updated_at = :updated_at
                    WHERE id = :user_id
                    """
                ),
                {
                    "user_id": user["id"],
                    "display_name": provider_login,
                    "email": persisted_email,
                    "avatar_url": avatar_url,
                    "updated_at": datetime.now(UTC),
                },
            )
            await connection.execute(
                text(
                    """
                    UPDATE identity_binding
                    SET login_name = :login_name,
                        extra_json = CAST(:extra_json AS jsonb),
                        updated_at = :updated_at
                    WHERE id = :binding_id
                    """
                ),
                {
                    "binding_id": user["binding_id"],
                    "login_name": provider_login,
                    "extra_json": json.dumps(claims.get("extra") or {}),
                    "updated_at": datetime.now(UTC),
                },
            )
            user = {
                **user,
                "display_name": provider_login,
                "email": persisted_email,
                "avatar_url": avatar_url,
            }

        role_codes = await _role_codes(connection, str(user["id"]))

    _ensure_user_status_allows_login(user)
    return {
        "userId": str(user["id"]),
        "displayName": str(user["display_name"]),
        "email": user.get("email") or "",
        "avatarUrl": user.get("avatar_url") or "",
        "oauthProvider": provider,
        "platformRoles": _normalize_platform_roles(role_codes),
    }


async def _find_bound_user(connection: Any, provider: str, subject: str) -> dict[str, object] | None:
    row = (
        await connection.execute(
            text(
                """
                SELECT
                    ib.id AS binding_id,
                    u.id,
                    u.display_name,
                    u.email,
                    u.avatar_url,
                    u.status,
                    u.merged_to_user_id,
                    u.system_account
                FROM identity_binding ib
                JOIN user_account u ON u.id = ib.user_id
                WHERE ib.provider_code = :provider_code
                  AND ib.subject = :subject
                LIMIT 1
                """
            ),
            {"provider_code": provider, "subject": subject},
        )
    ).mappings().one_or_none()
    return dict(row) if row is not None else None


async def _role_codes(connection: Any, user_id: str) -> list[str]:
    rows = (
        await connection.execute(
            text(
                """
                SELECT r.code
                FROM user_role_binding urb
                JOIN role r ON r.id = urb.role_id
                WHERE urb.user_id = :user_id
                ORDER BY r.code ASC
                """
            ),
            {"user_id": user_id},
        )
    ).mappings().all()
    return [str(row["code"]) for row in rows]


async def _ensure_global_namespace_membership(connection: Any, user_id: str) -> None:
    namespace = (
        await connection.execute(
            text(
                """
                SELECT id, slug
                FROM namespace
                WHERE slug = 'global'
                LIMIT 1
                """
            )
        )
    ).mappings().one_or_none()
    if namespace is None:
        return
    existing = (
        await connection.execute(
            text(
                """
                SELECT id
                FROM namespace_member
                WHERE namespace_id = :namespace_id
                  AND user_id = :user_id
                LIMIT 1
                """
            ),
            {"namespace_id": namespace["id"], "user_id": user_id},
        )
    ).mappings().one_or_none()
    if existing is not None:
        return
    await connection.execute(
        text(
            """
            INSERT INTO namespace_member (namespace_id, user_id, role)
            VALUES (:namespace_id, :user_id, :role)
            """
        ),
        {"namespace_id": namespace["id"], "user_id": user_id, "role": "MEMBER"},
    )


def _ensure_user_status_allows_login(user: dict[str, object]) -> None:
    if bool(user.get("system_account")):
        raise PermissionError("error.auth.oauth.systemAccount")
    status = str(user.get("status") or "ACTIVE")
    if status == "PENDING":
        raise PermissionError("error.auth.oauth.accountPending")
    if status == "DISABLED":
        raise PermissionError("error.auth.oauth.accountDisabled")
    if status == "MERGED":
        raise PermissionError("error.auth.oauth.accountMerged")


def _normalize_platform_roles(role_codes: list[str]) -> list[str]:
    normalized = sorted({role for role in role_codes if role})
    return normalized if normalized else [DEFAULT_USER_ROLE]
