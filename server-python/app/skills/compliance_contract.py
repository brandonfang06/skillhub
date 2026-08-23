from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class ComplianceEvidenceResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: str | None = None
    path: str | None = None
    url: str | None = None
    sha256: str | None = None


class ComplianceMappingResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    standard: str | None = None
    version: str | None = None
    control_id: str | None = Field(default=None, alias="controlId")
    title: str | None = None
    evidence: list[ComplianceEvidenceResponse] = Field(default_factory=list)


class ComplianceSnapshotResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    schema_version: str | None = Field(default=None, alias="schemaVersion")
    items: list[ComplianceMappingResponse] = Field(default_factory=list)
    digest: str | None = None


class ComplianceProjection(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    compliance_snapshot: ComplianceSnapshotResponse | None = Field(
        default=None,
        alias="complianceSnapshot",
    )


__all__ = [
    "ComplianceEvidenceResponse",
    "ComplianceMappingResponse",
    "ComplianceProjection",
    "ComplianceSnapshotResponse",
]
