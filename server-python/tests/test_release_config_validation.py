from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
VALID_CONFIG = {
    "SKILLHUB_PUBLIC_BASE_URL": "https://skills.example.com/skillhub",
    "SKILLHUB_WEB_BASE_PATH": "/skillhub",
    "SKILLHUB_DEVICE_AUTH_VERIFICATION_URI": "",
    "DEVICE_AUTH_VERIFICATION_URI": "",
    "SESSION_COOKIE_SECURE": "true",
    "BOOTSTRAP_ADMIN_ENABLED": "false",
    "POSTGRES_DB": "skillhub",
    "POSTGRES_USER": "skillhub",
    "POSTGRES_PASSWORD": "release-postgres-password",
    "SKILLHUB_STORAGE_PROVIDER": "local",
}


def run_validator(tmp_path: Path, overrides: dict[str, str | None]) -> subprocess.CompletedProcess[str]:
    config = {**VALID_CONFIG, **overrides}
    env_file = tmp_path / ".env.release"
    env_file.write_text(
        "".join(f"{name}={value}\n" for name, value in config.items() if value is not None),
        encoding="utf-8",
    )
    shell = shutil.which("sh")
    assert shell is not None, "release validation requires a POSIX shell"
    return subprocess.run(
        [shell, (ROOT / "scripts" / "validate-release-config.sh").as_posix(), env_file.as_posix()],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )


@pytest.mark.parametrize(
    "overrides",
    [
        {"SKILLHUB_PUBLIC_BASE_URL": "https://skills.example.com", "SKILLHUB_WEB_BASE_PATH": ""},
        {
            "SKILLHUB_PUBLIC_BASE_URL": "http://skillhub:8080",
            "SKILLHUB_WEB_BASE_PATH": "",
            "SESSION_COOKIE_SECURE": "false",
        },
        {"SKILLHUB_PUBLIC_BASE_URL": "http://[::1]", "SKILLHUB_WEB_BASE_PATH": ""},
        {"SKILLHUB_PUBLIC_BASE_URL": "http://[::1]:8080", "SKILLHUB_WEB_BASE_PATH": ""},
        {
            "SKILLHUB_PUBLIC_BASE_URL": "http://[::ffff:192.0.2.1]",
            "SKILLHUB_WEB_BASE_PATH": "",
            "SESSION_COOKIE_SECURE": "false",
        },
        {"SKILLHUB_WEB_BASE_PATH": "/skillhub/"},
        {
            "SKILLHUB_DEVICE_AUTH_VERIFICATION_URI": "https://auth.example.com/verify",
            "DEVICE_AUTH_VERIFICATION_URI": "not-a-url",
        },
        {
            "SKILLHUB_DEVICE_AUTH_VERIFICATION_URI": "",
            "DEVICE_AUTH_VERIFICATION_URI": "https://legacy.example.com/device",
        },
    ],
)
def test_release_validator_accepts_supported_subpath_and_device_url_combinations(
    tmp_path: Path,
    overrides: dict[str, str],
) -> None:
    result = run_validator(tmp_path, overrides)

    assert result.returncode == 0, result.stderr


def test_release_validator_accepts_a_max_length_fqdn_with_root_dot(
    tmp_path: Path,
) -> None:
    hostname = ".".join(["a" * 63, "b" * 63, "c" * 63, "d" * 61]) + "."

    result = run_validator(
        tmp_path,
        {"SKILLHUB_PUBLIC_BASE_URL": f"https://{hostname}/skillhub"},
    )

    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize(
    ("base_path", "expected_message"),
    [
        ("skillhub", "SKILLHUB_WEB_BASE_PATH must be blank, /, or a root-relative path"),
        ("//evil.example", "SKILLHUB_WEB_BASE_PATH is invalid"),
        ("/skillhub?next=/admin", "SKILLHUB_WEB_BASE_PATH is invalid"),
        ("/skillhub#admin", "SKILLHUB_WEB_BASE_PATH is invalid"),
        ("/skillhub/../admin", "SKILLHUB_WEB_BASE_PATH is invalid"),
        ("/skillhub//admin", "SKILLHUB_WEB_BASE_PATH is invalid"),
    ],
)
def test_release_validator_rejects_malformed_web_base_paths(
    tmp_path: Path,
    base_path: str,
    expected_message: str,
) -> None:
    result = run_validator(tmp_path, {"SKILLHUB_WEB_BASE_PATH": base_path})

    assert result.returncode == 1
    assert expected_message in result.stderr


@pytest.mark.parametrize(
    "overrides",
    [
        {"SKILLHUB_PUBLIC_BASE_URL": "https://skills.example.com", "SKILLHUB_WEB_BASE_PATH": "/skillhub"},
        {"SKILLHUB_PUBLIC_BASE_URL": "https://skills.example.com/skillhub", "SKILLHUB_WEB_BASE_PATH": ""},
        {"SKILLHUB_PUBLIC_BASE_URL": "https://skills.example.com/other", "SKILLHUB_WEB_BASE_PATH": "/skillhub"},
    ],
)
def test_release_validator_rejects_public_url_and_web_base_path_mismatches(
    tmp_path: Path,
    overrides: dict[str, str],
) -> None:
    result = run_validator(tmp_path, overrides)

    assert result.returncode == 1
    assert "SKILLHUB_PUBLIC_BASE_URL path must match SKILLHUB_WEB_BASE_PATH" in result.stderr


def test_release_validator_rejects_insecure_cookie_for_https_public_url(tmp_path: Path) -> None:
    result = run_validator(tmp_path, {"SESSION_COOKIE_SECURE": "false"})

    assert result.returncode == 1
    assert "SESSION_COOKIE_SECURE must be true for an HTTPS public URL" in result.stderr


@pytest.mark.parametrize("cookie_value", ["", None])
def test_release_validator_rejects_missing_secure_cookie_for_https_public_url(
    tmp_path: Path,
    cookie_value: str | None,
) -> None:
    result = run_validator(tmp_path, {"SESSION_COOKIE_SECURE": cookie_value})

    assert result.returncode == 1
    assert "SESSION_COOKIE_SECURE must be true for an HTTPS public URL" in result.stderr


@pytest.mark.parametrize(
    "public_url",
    [
        "https://user:password@skills.example.com/skillhub",
        "https://skills.example.com:bad/skillhub",
        "https://skills.example.com:0/skillhub",
        "https://-/skillhub",
        "https://.example.com/skillhub",
        "https://example..com/skillhub",
        "https://-skills.example.com/skillhub",
        "https://skills-.example.com/skillhub",
        "https://[::1/skillhub",
        "https://[::::]/skillhub",
        "https://[1::2::3]/skillhub",
        "https://[12345::1]/skillhub",
        "https://[1:2:3:4:5:6:7:8:9]/skillhub",
        "https://[::ffff:999.1.1.1]/skillhub",
        "https://skills.example.com/skillhub/../admin",
        "https://skills.example.com/skillhub%2fadmin",
        'https://skills.example.com/skillhub";alert(1)//',
    ],
)
def test_release_validator_rejects_public_urls_the_backend_would_reject(
    tmp_path: Path,
    public_url: str,
) -> None:
    result = run_validator(tmp_path, {"SKILLHUB_PUBLIC_BASE_URL": public_url})

    assert result.returncode == 1
    assert "SKILLHUB_PUBLIC_BASE_URL must be an absolute HTTP/HTTPS URL" in result.stderr


@pytest.mark.parametrize(
    "overrides",
    [
        {"SKILLHUB_DEVICE_AUTH_VERIFICATION_URI": "/skillhub/cli/auth"},
        {"SKILLHUB_DEVICE_AUTH_VERIFICATION_URI": "ftp://auth.example.com/verify"},
        {"SKILLHUB_DEVICE_AUTH_VERIFICATION_URI": "https://user:password@auth.example.com/verify"},
        {"SKILLHUB_DEVICE_AUTH_VERIFICATION_URI": "https://auth.example.com/verify?source=cli"},
        {"SKILLHUB_DEVICE_AUTH_VERIFICATION_URI": "https://auth.example.com/verify#device"},
        {"SKILLHUB_DEVICE_AUTH_VERIFICATION_URI": "https://auth.example.com:bad/verify"},
        {"SKILLHUB_DEVICE_AUTH_VERIFICATION_URI": "https://auth.example.com:0/verify"},
        {"SKILLHUB_DEVICE_AUTH_VERIFICATION_URI": "https://-/verify"},
        {"SKILLHUB_DEVICE_AUTH_VERIFICATION_URI": "https://auth..example.com/verify"},
        {"SKILLHUB_DEVICE_AUTH_VERIFICATION_URI": "https://[::1/verify"},
        {"SKILLHUB_DEVICE_AUTH_VERIFICATION_URI": "https://auth.example.com/verify/../admin"},
        {"SKILLHUB_DEVICE_AUTH_VERIFICATION_URI": "https://auth.example.com/verify%2fadmin"},
        {"SKILLHUB_DEVICE_AUTH_VERIFICATION_URI": "https://auth.example.com//verify"},
        {
            "SKILLHUB_DEVICE_AUTH_VERIFICATION_URI": "not-a-url",
            "DEVICE_AUTH_VERIFICATION_URI": "https://legacy.example.com/device",
        },
        {
            "SKILLHUB_DEVICE_AUTH_VERIFICATION_URI": "",
            "DEVICE_AUTH_VERIFICATION_URI": "/device",
        },
    ],
)
def test_release_validator_rejects_the_effective_invalid_device_verification_url(
    tmp_path: Path,
    overrides: dict[str, str],
) -> None:
    result = run_validator(tmp_path, overrides)

    assert result.returncode == 1
    assert "device auth verification URI must be" in result.stderr
