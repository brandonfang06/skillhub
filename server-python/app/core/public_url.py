from __future__ import annotations

import os
import re
from urllib.parse import unquote, urlsplit, urlunsplit

DEFAULT_PUBLIC_BASE_URL = "http://localhost:8080"
_PUBLIC_PATH_PATTERN = re.compile(r"/[A-Za-z0-9._~!$&'()*+,;=:@/-]*")
_WEB_BASE_PATH_PATTERN = re.compile(r"/[A-Za-z0-9._~/-]+/?")
_PERCENT_ESCAPE_PATTERN = re.compile(r"%(?![0-9A-Fa-f]{2})")
_PUBLIC_AUTHORITY_PATTERN = re.compile(r"(?:[A-Za-z0-9.-]+|\[[0-9A-Fa-f:.]+\])(?::[0-9]{1,5})?")


def resolve_public_base_url(value: str | None = None) -> str:
    raw = os.getenv("SKILLHUB_PUBLIC_BASE_URL") if value is None else value
    normalized = (raw or DEFAULT_PUBLIC_BASE_URL).strip() or DEFAULT_PUBLIC_BASE_URL
    resolved = resolve_absolute_http_url(normalized, "SKILLHUB_PUBLIC_BASE_URL")
    parsed = urlsplit(resolved)
    path = parsed.path.rstrip("/")
    if path == "/":
        path = ""
    return urlunsplit((parsed.scheme, parsed.netloc, path, "", ""))


def resolve_absolute_http_url(value: str, variable_name: str) -> str:
    normalized = value.strip()
    try:
        parsed = urlsplit(normalized)
    except ValueError as exc:
        raise ValueError(f"Invalid {variable_name}") from exc
    if (
        parsed.scheme not in {"http", "https"}
        or parsed.hostname is None
        or not _valid_public_netloc(parsed.netloc)
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
        or not _valid_public_base_path(parsed.path)
    ):
        raise ValueError(f"Invalid {variable_name}")
    try:
        parsed.port
    except ValueError as exc:
        raise ValueError(f"Invalid {variable_name}") from exc

    return urlunsplit((parsed.scheme, parsed.netloc, parsed.path, "", ""))


def public_base_path(value: str | None = None) -> str:
    return urlsplit(resolve_public_base_url(value)).path


def resolve_web_base_path(value: str | None = None) -> str:
    raw = os.getenv("SKILLHUB_WEB_BASE_PATH") if value is None else value
    normalized = (raw or "").strip()
    if normalized in {"", "/"}:
        return ""
    if (
        not _WEB_BASE_PATH_PATTERN.fullmatch(normalized)
        or "//" in normalized
        or "\\" in normalized
    ):
        raise ValueError("Invalid SKILLHUB_WEB_BASE_PATH")
    resolved = normalized.rstrip("/")
    if any(segment in {"", ".", ".."} for segment in resolved[1:].split("/")):
        raise ValueError("Invalid SKILLHUB_WEB_BASE_PATH")
    return resolved


def validate_deployment_url_contract(
    public_url: str | None = None,
    web_base_path: str | None = None,
    *,
    session_cookie_secure: bool,
) -> None:
    resolved_public_url = resolve_public_base_url(public_url)
    resolved_web_base_path = resolve_web_base_path(web_base_path)
    parsed = urlsplit(resolved_public_url)
    if parsed.path != resolved_web_base_path:
        raise ValueError("SKILLHUB_PUBLIC_BASE_URL path must match SKILLHUB_WEB_BASE_PATH")
    if parsed.scheme == "https" and not session_cookie_secure:
        raise ValueError("SKILLHUB_SESSION_COOKIE_SECURE must be enabled for an HTTPS public URL")


def to_public_path(app_path: str, value: str | None = None) -> str:
    if not is_safe_app_path(app_path):
        raise ValueError("Application path must be a safe root-relative path")
    return f"{public_base_path(value)}{app_path}"


def to_public_url(app_path: str, value: str | None = None) -> str:
    if not is_safe_app_path(app_path):
        raise ValueError("Application path must be a safe root-relative path")
    base_url = resolve_public_base_url(value)
    return f"{base_url}{app_path}"


def is_safe_app_path(value: str) -> bool:
    if not value.startswith("/") or value.startswith("//") or "\r" in value or "\n" in value or "\\" in value:
        return False
    if _PERCENT_ESCAPE_PATTERN.search(value):
        return False
    parsed = urlsplit(value)
    if parsed.scheme or parsed.netloc:
        return False

    decoded_path = unquote(parsed.path)
    if "/" in decoded_path.replace("/", "", 1) and re.search(r"%2f", parsed.path, re.IGNORECASE):
        return False
    if "\\" in decoded_path or any(ord(character) < 32 for character in decoded_path):
        return False
    return all(segment not in {".", ".."} for segment in decoded_path.split("/"))


def _valid_public_base_path(path: str) -> bool:
    if path == "":
        return True
    if not _PUBLIC_PATH_PATTERN.fullmatch(path) or "//" in path or "\\" in path:
        return False
    return all(segment not in {".", ".."} for segment in path.split("/"))


def _valid_public_netloc(netloc: str) -> bool:
    if not netloc or "%" in netloc or "\\" in netloc:
        return False
    if any(character.isspace() or ord(character) < 33 or ord(character) == 127 for character in netloc):
        return False
    return _PUBLIC_AUTHORITY_PATTERN.fullmatch(netloc) is not None
