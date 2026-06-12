from collections.abc import Awaitable
from datetime import UTC, datetime
from inspect import isawaitable
import os
import secrets
from typing import Any
from urllib.parse import urlencode
from urllib.parse import quote_plus

from fastapi import APIRouter, Header, HTTPException, Request, Response
from sqlalchemy import text
from starlette.responses import RedirectResponse

from app.auth.oauth import (
    bind_oauth_principal,
    configured_oauth_registration,
    default_oauth_flow_configured,
    exchange_oauth_code,
    oauth_registrations_from_env,
)
from app.auth.session import clear_session, establish_session, read_session_principal
from app.auth.tokens import sha256_token
from app.core.response import ok

router = APIRouter()

DEFAULT_USER_ROLE = "USER"
DEFAULT_OAUTH_TARGET_URL = "/dashboard"


def normalize_platform_roles(role_codes: list[str]) -> list[str]:
    normalized = sorted({role for role in role_codes if role})
    return normalized if normalized else [DEFAULT_USER_ROLE]


def build_auth_me_response(user_row: dict[str, Any], role_codes: list[str]) -> dict[str, object]:
    return {
        "userId": str(user_row["id"]),
        "displayName": str(user_row["display_name"]),
        "email": user_row["email"] or "",
        "avatarUrl": user_row["avatar_url"] or "",
        "oauthProvider": str(user_row.get("oauth_provider") or "mock"),
        "platformRoles": normalize_platform_roles(role_codes),
    }


def build_clawhub_whoami_response(user: dict[str, object]) -> dict[str, object]:
    return {
        "user": {
            "handle": str(user["userId"]),
            "displayName": str(user["displayName"]),
            "image": user.get("avatarUrl") or "",
        }
    }


def build_cli_whoami_response(user: dict[str, object]) -> dict[str, object]:
    return {
        "handle": str(user["userId"]),
        "displayName": str(user["displayName"]),
        "email": user.get("email") or "",
    }


def sanitize_return_to(candidate: str | None) -> str | None:
    if candidate is None or candidate.strip() == "":
        return None
    trimmed = candidate.strip()
    if not trimmed.startswith("/") or trimmed.startswith("//"):
        return None
    if "\r" in trimmed or "\n" in trimmed:
        return None
    return trimmed


def _registration_id(registration: dict[str, object]) -> str:
    return str(registration["id"])


def _registration_name(registration: dict[str, object]) -> str:
    client_name = str(registration.get("clientName") or "").strip()
    return client_name if client_name else _registration_id(registration)


def _authorization_url(registration_id: str, return_to: str | None) -> str:
    base_url = f"/oauth2/authorization/{registration_id}"
    sanitized_return_to = sanitize_return_to(return_to)
    if sanitized_return_to is None:
        return base_url
    return f"{base_url}?returnTo={quote_plus(sanitized_return_to)}"


def build_auth_providers(oauth_registrations: list[dict[str, object]], return_to: str | None = None) -> list[dict[str, str]]:
    return [
        {
            "id": _registration_id(registration),
            "name": _registration_name(registration),
            "authorizationUrl": _authorization_url(_registration_id(registration), return_to),
        }
        for registration in sorted(oauth_registrations, key=_registration_id)
    ]


def build_auth_methods(
    oauth_registrations: list[dict[str, object]],
    *,
    return_to: str | None = None,
    direct_enabled: bool = False,
    session_bootstrap_enabled: bool = False,
) -> list[dict[str, str]]:
    methods = [
        {
            "id": "local-password",
            "methodType": "PASSWORD",
            "provider": "local",
            "displayName": "Local Account",
            "actionUrl": "/api/v1/auth/local/login",
        }
    ]
    for provider in build_auth_providers(oauth_registrations, return_to):
        methods.append(
            {
                "id": f"oauth-{provider['id']}",
                "methodType": "OAUTH_REDIRECT",
                "provider": provider["id"],
                "displayName": provider["name"],
                "actionUrl": provider["authorizationUrl"],
            }
        )
    if direct_enabled:
        methods.append(
            {
                "id": "direct-local",
                "methodType": "DIRECT_PASSWORD",
                "provider": "local",
                "displayName": "Local Account",
                "actionUrl": "/api/v1/auth/direct/login",
            }
        )
    if session_bootstrap_enabled:
        methods.append(
            {
                "id": "bootstrap-mock",
                "methodType": "SESSION_BOOTSTRAP",
                "provider": "mock",
                "displayName": "Mock Session",
                "actionUrl": "/api/v1/auth/session/bootstrap",
            }
        )
    return methods


def _parse_bool_env(name: str) -> bool:
    value = os.getenv(name)
    return value is not None and value.strip().lower() in {"1", "true", "yes", "on"}


def _oauth_registrations(request: Request) -> list[dict[str, object]]:
    configured = getattr(request.app.state, "auth_oauth_registrations", None)
    return configured if configured is not None else oauth_registrations_from_env()


def _find_oauth_registration(request: Request, registration_id: str) -> dict[str, object] | None:
    for registration in _oauth_registrations(request):
        if _registration_id(registration) == registration_id:
            return registration
    return None


def _oauth_scopes(registration: dict[str, object]) -> str | None:
    scopes = registration.get("scopes")
    if isinstance(scopes, list):
        normalized = [str(scope).strip() for scope in scopes if str(scope).strip()]
        return " ".join(normalized) if normalized else None
    if isinstance(scopes, str) and scopes.strip():
        return scopes.strip()
    return None


def _oauth_state_store(request: Request) -> dict[str, str]:
    store = getattr(request.app.state, "oauth_state_store", None)
    if store is None:
        store = {}
        request.app.state.oauth_state_store = store
    return store


def _remember_oauth_return_to(request: Request, return_to: str | None) -> str:
    state = secrets.token_urlsafe(24)
    _oauth_state_store(request)[state] = sanitize_return_to(return_to) or DEFAULT_OAUTH_TARGET_URL
    return state


def _consume_oauth_return_to(request: Request, state: str | None) -> str:
    if state is None or state.strip() == "":
        return DEFAULT_OAUTH_TARGET_URL
    return _oauth_state_store(request).pop(state, DEFAULT_OAUTH_TARGET_URL)


def _direct_enabled(request: Request) -> bool:
    configured = getattr(request.app.state, "auth_direct_enabled", None)
    return bool(configured) if configured is not None else _parse_bool_env("SKILLHUB_AUTH_DIRECT_ENABLED")


def _session_bootstrap_enabled(request: Request) -> bool:
    configured = getattr(request.app.state, "auth_session_bootstrap_enabled", None)
    return bool(configured) if configured is not None else _parse_bool_env("SKILLHUB_AUTH_SESSION_BOOTSTRAP_ENABLED")


async def read_current_mock_user(engine: Any, user_id: str) -> dict[str, object] | None:
    async with engine.connect() as connection:
        user_row = (
            await connection.execute(
                text(
                    """
                    SELECT id, display_name, email, avatar_url
                    FROM user_account
                    WHERE id = :user_id
                      AND status = 'ACTIVE'
                    LIMIT 1
                    """
                ),
                {"user_id": user_id},
            )
        ).mappings().one_or_none()

        if user_row is None:
            return None

        role_rows = (
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

    return build_auth_me_response(dict(user_row), [str(row["code"]) for row in role_rows])


def _decode_scope_json(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item) for item in value]
    if isinstance(value, str):
        import json

        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return []
        if isinstance(parsed, list):
            return [str(item) for item in parsed]
    return []


async def read_current_bearer_user(engine: Any, raw_token: str) -> dict[str, object] | None:
    now = datetime.now(UTC)
    async with engine.begin() as connection:
        row = (
            await connection.execute(
                text(
                    """
                    SELECT
                        t.id AS token_id,
                        t.scope_json,
                        u.id,
                        u.display_name,
                        u.email,
                        u.avatar_url
                    FROM api_token t
                    JOIN user_account u ON u.id = t.user_id
                    WHERE t.token_hash = :token_hash
                      AND t.revoked_at IS NULL
                      AND (t.expires_at IS NULL OR t.expires_at > :now)
                      AND u.status = 'ACTIVE'
                    LIMIT 1
                    """
                ),
                {"token_hash": sha256_token(raw_token), "now": now},
            )
        ).mappings().one_or_none()
        if row is None:
            return None

        role_rows = (
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
                {"user_id": row["id"]},
            )
        ).mappings().all()
        await connection.execute(
            text("UPDATE api_token SET last_used_at = :last_used_at WHERE id = :token_id"),
            {"last_used_at": now, "token_id": int(row["token_id"])},
        )

    data = dict(row)
    data["oauth_provider"] = "api_token"
    response = build_auth_me_response(data, [str(role["code"]) for role in role_rows])
    response["tokenScopes"] = _decode_scope_json(row.get("scope_json"))
    return response


async def _resolve_reader_result(
    result: dict[str, object] | None | Awaitable[dict[str, object] | None],
) -> dict[str, object] | None:
    if isawaitable(result):
        return await result
    return result


async def _read_mock_user_or_401(request: Request, mock_user_id: str | None) -> dict[str, object]:
    if mock_user_id is None or mock_user_id.strip() == "":
        raise HTTPException(status_code=401, detail="error.auth.required")

    user_id = mock_user_id.strip()
    reader = getattr(request.app.state, "auth_me_reader", None)
    if reader is not None:
        data = await _resolve_reader_result(reader(user_id))
    else:
        data = await read_current_mock_user(request.app.state.db_engine, user_id)

    if data is None:
        raise HTTPException(status_code=401, detail="error.auth.required")
    return data


def _bearer_token(authorization: str | None) -> str | None:
    if authorization is None or not authorization.startswith("Bearer "):
        return None
    token = authorization[len("Bearer ") :].strip()
    return token if token else None


async def _read_current_user_or_401(
    request: Request,
    mock_user_id: str | None,
    authorization: str | None,
) -> dict[str, object]:
    if mock_user_id is not None and mock_user_id.strip() != "":
        return await _read_mock_user_or_401(request, mock_user_id)

    token = _bearer_token(authorization)
    if token is not None:
        reader = getattr(request.app.state, "auth_bearer_reader", None)
        if reader is not None:
            data = await _resolve_reader_result(reader(token))
        else:
            data = await read_current_bearer_user(request.app.state.db_engine, token)

        if data is None:
            raise HTTPException(status_code=401, detail="error.auth.required")
        return data

    session_principal = await read_session_principal(request)
    if session_principal is not None:
        return session_principal

    raise HTTPException(status_code=401, detail="error.auth.required")


async def _resolve_result(result: Any | Awaitable[Any]) -> Any:
    if isawaitable(result):
        return await result
    return result


def _payload_provider(payload: dict[str, Any]) -> str:
    return str(payload.get("provider") or "").strip()


@router.get("/api/v1/auth/me")
async def get_current_user(
    request: Request,
    mock_user_id: str | None = Header(default=None, alias="X-Mock-User-Id"),
    authorization: str | None = Header(default=None, alias="Authorization"),
) -> dict[str, object]:
    data = await _read_current_user_or_401(request, mock_user_id, authorization)
    return ok("\u83b7\u53d6\u6210\u529f", data, request)


@router.post("/api/v1/auth/logout", status_code=204)
async def logout(request: Request, response: Response) -> None:
    await clear_session(request, response)


@router.get("/api/v1/whoami")
async def get_clawhub_whoami(
    request: Request,
    mock_user_id: str | None = Header(default=None, alias="X-Mock-User-Id"),
    authorization: str | None = Header(default=None, alias="Authorization"),
) -> dict[str, object]:
    data = await _read_current_user_or_401(request, mock_user_id, authorization)
    return build_clawhub_whoami_response(data)


@router.get("/api/cli/v1/auth/whoami")
async def get_cli_whoami(
    request: Request,
    mock_user_id: str | None = Header(default=None, alias="X-Mock-User-Id"),
    authorization: str | None = Header(default=None, alias="Authorization"),
) -> dict[str, object]:
    data = await _read_current_user_or_401(request, mock_user_id, authorization)
    return ok("\u83b7\u53d6\u6210\u529f", build_cli_whoami_response(data), request)


@router.get("/api/v1/auth/providers")
async def get_auth_providers(request: Request, returnTo: str | None = None) -> dict[str, object]:
    return ok("\u83b7\u53d6\u6210\u529f", build_auth_providers(_oauth_registrations(request), returnTo), request)


@router.get("/api/v1/auth/methods")
async def get_auth_methods(request: Request, returnTo: str | None = None) -> dict[str, object]:
    return ok(
        "\u83b7\u53d6\u6210\u529f",
        build_auth_methods(
            _oauth_registrations(request),
            return_to=returnTo,
            direct_enabled=_direct_enabled(request),
            session_bootstrap_enabled=_session_bootstrap_enabled(request),
        ),
        request,
    )


@router.get("/oauth2/authorization/{registration_id}")
async def oauth_authorization_boundary(request: Request, registration_id: str, returnTo: str | None = None) -> RedirectResponse:
    registration = _find_oauth_registration(request, registration_id)
    if registration is None:
        raise HTTPException(status_code=404, detail="error.auth.oauth.providerNotFound")
    if not configured_oauth_registration(registration):
        sanitize_return_to(returnTo)
        raise HTTPException(status_code=501, detail="error.auth.oauth.deferred")

    params = {
        "response_type": "code",
        "client_id": str(registration["clientId"]),
        "redirect_uri": str(registration["redirectUri"]),
        "state": _remember_oauth_return_to(request, returnTo),
    }
    scopes = _oauth_scopes(registration)
    if scopes is not None:
        params["scope"] = scopes
    return RedirectResponse(f"{registration['authorizationUri']}?{urlencode(params)}")


@router.get("/login/oauth2/code/{registration_id}")
async def oauth_callback(
    request: Request,
    registration_id: str,
    code: str | None = None,
    state: str | None = None,
) -> RedirectResponse:
    registration = _find_oauth_registration(request, registration_id)
    if registration is None:
        raise HTTPException(status_code=404, detail="error.auth.oauth.providerNotFound")
    if code is None or code.strip() == "":
        raise HTTPException(status_code=400, detail="error.auth.oauth.codeRequired")
    if not configured_oauth_registration(registration):
        raise HTTPException(status_code=501, detail="error.auth.oauth.deferred")

    exchanger = getattr(request.app.state, "oauth_code_exchanger", None)
    binder = getattr(request.app.state, "oauth_principal_binder", None)
    if (exchanger is None or binder is None) and not default_oauth_flow_configured(registration):
        raise HTTPException(status_code=501, detail="error.auth.oauth.deferred")
    try:
        claims = await _resolve_result(
            exchanger(registration, code.strip())
            if exchanger is not None
            else exchange_oauth_code(
                registration,
                code.strip(),
                http_client_factory=getattr(request.app.state, "oauth_http_client_factory", None),
            )
        )
        principal = await _resolve_result(
            binder(registration, claims)
            if binder is not None
            else bind_oauth_principal(request.app.state.db_engine, registration, claims)
        )
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except (ValueError, KeyError) as exc:
        raise HTTPException(status_code=502, detail="error.auth.oauth.exchangeFailed") from exc
    redirect = RedirectResponse(_consume_oauth_return_to(request, state))
    await establish_session(request, redirect, principal)
    return redirect


@router.post("/api/v1/auth/direct/login")
async def direct_login(request: Request, response: Response, payload: dict[str, Any]) -> dict[str, object]:
    if not _direct_enabled(request):
        raise HTTPException(status_code=403, detail="error.auth.direct.disabled")

    provider = _payload_provider(payload)
    if provider != "local":
        raise HTTPException(status_code=400, detail="error.auth.direct.providerUnsupported")

    from app.auth.local import LocalAuthError, login_local_user

    login = getattr(request.app.state, "local_auth_login", None)
    try:
        data = await _resolve_result(
            login(payload)
            if login is not None
            else login_local_user(
                request.app.state.db_engine,
                username=payload.get("username"),
                password=payload.get("password"),
            )
        )
    except LocalAuthError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    await establish_session(request, response, data)
    return ok("response.success.read", data, request)


@router.post("/api/v1/auth/session/bootstrap")
async def session_bootstrap(request: Request, payload: dict[str, Any]) -> dict[str, object]:
    if not _session_bootstrap_enabled(request):
        raise HTTPException(status_code=403, detail="error.auth.sessionBootstrap.disabled")

    raise HTTPException(status_code=400, detail="error.auth.sessionBootstrap.providerUnsupported")
