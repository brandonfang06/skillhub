from pathlib import Path
from types import SimpleNamespace

from skillhub_oss_importer.orchestrator import run_import


class FakeClient:
    def __init__(self, validation_outcomes: list[str]) -> None:
        self.validation_outcomes = iter(validation_outcomes)
        self.calls: list[str] = []

    def ensure_namespace(self, _slug: str, _body: dict[str, object]) -> dict[str, object]:
        self.calls.append("ensure")
        return {"outcome": "CREATED"}

    def validate_skill(self, _slug: str, _content: bytes, metadata: dict[str, object]) -> dict[str, object]:
        self.calls.append(f"validate:{metadata['sourcePath']}")
        outcome = next(self.validation_outcomes)
        if outcome == "ERROR":
            raise ValueError("invalid package")
        return {"outcome": outcome, "coordinate": "@oss/x", "version": "1.0.0"}

    def submit_skill(self, _slug: str, _content: bytes, metadata: dict[str, object]) -> dict[str, object]:
        self.calls.append(f"submit:{metadata['sourcePath']}")
        return {"outcome": "IMPORTED", "coordinate": "@oss/x", "version": "1.0.0"}


def fixture_config(tmp_path: Path) -> SimpleNamespace:
    return SimpleNamespace(
        project_dir=tmp_path,
        source_root=tmp_path,
        namespace_slug="oss-owner-repo",
        namespace_display_name="OSS-owner-repo",
        repository_url="https://github.com/owner/repo",
        owner_provider_code="keycloak",
        owner_login_name="owner",
        trigger_provider_code="keycloak",
        trigger_login_name="alice",
        commit_sha="a" * 40,
        ref_type="COMMIT",
        source_ref=None,
        pipeline_id="1",
        job_id="2",
        ci_ref_name="main",
    )


def make_skills(tmp_path: Path) -> None:
    for name in ("a", "b"):
        root = tmp_path / name
        root.mkdir()
        (root / "SKILL.md").write_text(f"---\nname: {name}\ndescription: {name}\n---", encoding="utf-8")


def test_validates_every_package_before_sequential_submit(tmp_path: Path) -> None:
    make_skills(tmp_path)
    client = FakeClient(["IMPORT", "SKIPPED_UNCHANGED"])
    report = run_import(fixture_config(tmp_path), client, verify_revision=False)
    assert client.calls == ["ensure", "validate:a", "validate:b", "submit:a"]
    assert report["status"] == "SUCCESS"


def test_validation_failure_prevents_all_submissions(tmp_path: Path) -> None:
    make_skills(tmp_path)
    client = FakeClient(["IMPORT", "ERROR"])
    report = run_import(fixture_config(tmp_path), client, verify_revision=False)
    assert not any(call.startswith("submit:") for call in client.calls)
    assert report["status"] == "VALIDATION_FAILED"
