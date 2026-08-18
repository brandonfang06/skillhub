from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pytest
from sqlalchemy.exc import IntegrityError

from app.publish.orchestration import PublishWriteResult
from app.publish.package import PackageEntry, SkillMetadata
from app.source_import.contracts import SourcePackage, SourceServiceActor
from app.source_import.service import (
    IdentityAccount,
    NamespaceRecord,
    NamespaceSourceBinding,
    SourceSkillRecord,
    SourceSkillSubmissionRuntime,
    SourceSkillValidationPlan,
    ValidateSourceSkillInput,
    build_source_publish_input,
    submit_source_skill,
)
from app.source_import.source import (
    canonicalize_github_repository,
    validate_source_revision,
)


def validation_request() -> ValidateSourceSkillInput:
    entries = [PackageEntry("SKILL.md", b"skill", "text/markdown")]
    return ValidateSourceSkillInput(
        namespace_slug="oss-mattpocock-skills",
        repository=canonicalize_github_repository("https://github.com/mattpocock/skills"),
        revision=validate_source_revision("a" * 40, "BRANCH", "main"),
        source_path="skills/code-review",
        entries=entries,
        version_override="git-" + "a" * 40,
        initiator=None,
        service_actor=SourceServiceActor(
            "svc_importer", "gitlab-oss-importer", "GitLab OSS Importer"
        ),
    )


def validation_plan(*, outcome: str = "IMPORT", existing: bool = False) -> SourceSkillValidationPlan:
    request = validation_request()
    owner = IdentityAccount("stable-owner", "Stable Owner", "ACTIVE", None, None)
    submitter = IdentityAccount("pipeline-trigger", "Pipeline Trigger", "ACTIVE", "keycloak", "alice")
    source_skill = (
        SourceSkillRecord(31, 21, "skills/code-review", 41, "code-review", owner.user_id, "ACTIVE")
        if existing
        else None
    )
    return SourceSkillValidationPlan(
        outcome=outcome,  # type: ignore[arg-type]
        namespace=NamespaceRecord(11, request.namespace_slug, "OSS-mattpocock-skills", "TEAM", "ACTIVE"),
        namespace_binding=NamespaceSourceBinding(21, 11, request.repository.canonical_url),
        source_skill=source_skill,
        package=SourcePackage(
            source_path=request.source_path,
            entries=request.entries,
            metadata=SkillMetadata("Code Review", "Reviews code", None, {"name": "Code Review", "description": "Reviews code"}),
            content_fingerprint="f" * 64,
            effective_version=request.version_override or "",
        ),
        skill_slug="code-review",
        stable_owner=owner,
        review_submitter=submitter,
        add_submitter_as_member=True,
    )


def test_builds_public_review_publish_input_with_separate_identities(tmp_path) -> None:
    request = build_source_publish_input(
        validation_plan(),
        validation_request(),
        SourceSkillSubmissionRuntime(storage_base_path=str(tmp_path), scanner_enabled=True, scan_mode="upload"),
    )

    assert request.publisher_id == "stable-owner"
    assert request.submitter_id == "pipeline-trigger"
    assert request.actor_service_principal_id == "svc_importer"
    assert request.visibility == "PUBLIC"
    assert request.auto_publish is False
    assert request.version == "git-" + "a" * 40
    assert request.metadata.version == request.version


@dataclass
class FakePublishResult:
    skill_id: int = 41
    version_id: int = 51
    version_status: str = "SCANNING"


class FakePersistenceRepository:
    def __init__(self, _connection: Any) -> None:
        self.calls: list[tuple[str, dict[str, object]]] = []

    async def persist_source_submission(self, **kwargs: object) -> None:
        self.calls.append(("persist", kwargs))


@pytest.mark.anyio
async def test_submits_import_and_persists_provenance_in_publish_transaction(tmp_path) -> None:
    plan = validation_plan()
    persisted: list[dict[str, object]] = []

    async def validator(_engine: Any, _request: ValidateSourceSkillInput) -> SourceSkillValidationPlan:
        return plan

    async def publisher(
        _engine: Any,
        write_input: Any,
        **kwargs: Any,
    ) -> FakePublishResult:
        assert write_input.publisher_id == "stable-owner"
        assert write_input.submitter_id == "pipeline-trigger"
        callback = kwargs["after_prepare"]

        class CapturingRepository:
            async def persist_source_submission(self, **values: object) -> None:
                persisted.append(values)

        await callback(CapturingRepository(), 41, 51)
        return FakePublishResult()

    result = await submit_source_skill(
        object(),
        validation_request(),
        SourceSkillSubmissionRuntime(storage_base_path=str(tmp_path), scanner_enabled=True, scan_mode="upload"),
        validator=validator,
        publisher=publisher,
        repository_factory=lambda value: value,
    )

    assert result.outcome == "IMPORTED"
    assert result.skill_id == 41
    assert result.version_id == 51
    assert result.version_status == "SCANNING"
    assert persisted[0]["source_skill_id"] is None
    assert persisted[0]["service_actor"].service_principal_id == "svc_importer"
    assert persisted[0]["review_submitter_id"] == "pipeline-trigger"
    assert persisted[0]["repository_url"] == "https://github.com/mattpocock/skills"
    assert persisted[0]["stable_owner_id"] == "stable-owner"
    assert persisted[0]["outcome"] == "IMPORTED"


@pytest.mark.anyio
async def test_revalidates_unique_constraint_race_as_idempotent_skip(tmp_path) -> None:
    initial = validation_plan()
    skipped = validation_plan(outcome="SKIPPED_ALREADY_IMPORTED", existing=True)
    validations = iter((initial, skipped))

    async def validator(_engine: Any, _request: ValidateSourceSkillInput) -> SourceSkillValidationPlan:
        return next(validations)

    async def publisher(*_args: object, **_kwargs: object) -> PublishWriteResult:
        raise IntegrityError("insert", {}, RuntimeError("duplicate source version"))

    result = await submit_source_skill(
        object(),
        validation_request(),
        SourceSkillSubmissionRuntime(storage_base_path=str(tmp_path)),
        validator=validator,
        publisher=publisher,
    )

    assert result.outcome == "SKIPPED_ALREADY_IMPORTED"
    assert result.skill_id == 41


@pytest.mark.anyio
@pytest.mark.parametrize("outcome", ["SKIPPED_UNCHANGED", "SKIPPED_ALREADY_IMPORTED"])
async def test_returns_skip_without_calling_publish(outcome: str, tmp_path) -> None:
    plan = validation_plan(outcome=outcome, existing=True)
    called = False

    async def validator(_engine: Any, _request: ValidateSourceSkillInput) -> SourceSkillValidationPlan:
        return plan

    async def publisher(*args: object, **kwargs: object) -> PublishWriteResult:
        nonlocal called
        called = True
        raise AssertionError((args, kwargs))

    result = await submit_source_skill(
        object(),
        validation_request(),
        SourceSkillSubmissionRuntime(storage_base_path=str(tmp_path)),
        validator=validator,
        publisher=publisher,
    )

    assert result.outcome == outcome
    assert result.skill_id == 41
    assert result.version_id is None
    assert called is False
