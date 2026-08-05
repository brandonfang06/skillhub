import importlib

import pytest


def public_url_module():
    return importlib.import_module("app.core.public_url")


def test_public_base_url_normalizes_the_configured_subpath(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SKILLHUB_PUBLIC_BASE_URL", "https://ai-coding-platform.tsmc.com/skillhub/")

    public_url = public_url_module()

    assert public_url.resolve_public_base_url() == "https://ai-coding-platform.tsmc.com/skillhub"
    assert public_url.public_base_path() == "/skillhub"
    assert public_url.to_public_path("/dashboard") == "/skillhub/dashboard"
    assert public_url.to_public_url("/cli/auth") == "https://ai-coding-platform.tsmc.com/skillhub/cli/auth"


def test_public_base_url_preserves_root_deployment_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SKILLHUB_PUBLIC_BASE_URL", raising=False)

    public_url = public_url_module()

    assert public_url.resolve_public_base_url() == "http://localhost:8080"
    assert public_url.public_base_path() == ""
    assert public_url.to_public_path("/dashboard") == "/dashboard"


def test_public_url_rejects_an_unsafe_application_path() -> None:
    public_url = public_url_module()

    with pytest.raises(ValueError, match="root-relative"):
        public_url.to_public_url("//evil.example/login")


def test_deployment_url_contract_accepts_matching_secure_subpath() -> None:
    public_url = public_url_module()

    public_url.validate_deployment_url_contract(
        "https://skills.example.com/skillhub",
        "/skillhub/",
        session_cookie_secure=True,
    )


def test_settings_accepts_the_legacy_secure_cookie_alias(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SKILLHUB_PUBLIC_BASE_URL", "https://skills.example.com/skillhub")
    monkeypatch.setenv("SKILLHUB_WEB_BASE_PATH", "/skillhub")
    monkeypatch.delenv("SKILLHUB_SESSION_COOKIE_SECURE", raising=False)
    monkeypatch.setenv("SESSION_COOKIE_SECURE", "true")

    config = importlib.import_module("app.core.config")

    assert config.get_settings().storage_provider == "local"


@pytest.mark.parametrize(
    ("configured_public_url", "web_base_path", "secure", "message"),
    [
        (
            "https://skills.example.com/skillhub",
            "",
            True,
            "SKILLHUB_PUBLIC_BASE_URL path must match SKILLHUB_WEB_BASE_PATH",
        ),
        (
            "https://skills.example.com/skillhub",
            "/other",
            True,
            "SKILLHUB_PUBLIC_BASE_URL path must match SKILLHUB_WEB_BASE_PATH",
        ),
        (
            "https://skills.example.com/skillhub",
            "/skillhub",
            False,
            "SKILLHUB_SESSION_COOKIE_SECURE must be enabled",
        ),
        (
            "https://skills.example.com",
            "",
            False,
            "SKILLHUB_SESSION_COOKIE_SECURE must be enabled",
        ),
        (
            "http://localhost:8080",
            "/../admin",
            False,
            "Invalid SKILLHUB_WEB_BASE_PATH",
        ),
    ],
)
def test_deployment_url_contract_rejects_inconsistent_or_insecure_values(
    configured_public_url: str,
    web_base_path: str,
    secure: bool,
    message: str,
) -> None:
    public_url = public_url_module()

    with pytest.raises(ValueError, match=message):
        public_url.validate_deployment_url_contract(
            configured_public_url,
            web_base_path,
            session_cookie_secure=secure,
        )


@pytest.mark.parametrize(
    "value",
    [
        "//evil.example/skillhub",
        "ftp://skillhub.example/skillhub",
        "https://user:password@skillhub.example/skillhub",
        "https://skillhub.example/skillhub?next=/admin",
        "https://skillhub.example/skillhub#fragment",
        "https://skillhub.example/skillhub/../admin",
        "https://skillhub.example/skillhub%2f..%2fadmin",
        "https://skill hub.example/skillhub",
        "https://skill%20hub.example/skillhub",
        'https://skill"hub.example/skillhub',
        "https://skills.example.com:0/skillhub",
        "https://-/skillhub",
        "https://.example.com/skillhub",
        "https://example..com/skillhub",
        "https://-skills.example.com/skillhub",
        "https://skills-.example.com/skillhub",
        "https://[::::]/skillhub",
    ],
)
def test_public_base_url_rejects_unsafe_values(value: str) -> None:
    public_url = public_url_module()

    with pytest.raises(ValueError, match="SKILLHUB_PUBLIC_BASE_URL"):
        public_url.resolve_public_base_url(value)
