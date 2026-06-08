from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from io import BytesIO
from pathlib import Path
from zipfile import ZipFile

from app.publish.package import PackageEntry, normalize_entry_path


@dataclass(frozen=True)
class SkillFileWriteRecord:
    version_id: int
    file_path: str
    file_size: int
    content_type: str
    sha256: str
    storage_key: str


@dataclass(frozen=True)
class StoredPackageResult:
    files: list[SkillFileWriteRecord]
    bundle_key: str
    bundle_size: int
    file_count: int
    total_size: int
    bundle_ready: bool
    download_ready: bool


def skill_storage_key(skill_id: int, version_id: int, path: str) -> str:
    return f"skills/{skill_id}/{version_id}/{normalize_entry_path(path)}"


def bundle_storage_key(skill_id: int, version_id: int) -> str:
    return f"packages/{skill_id}/{version_id}/bundle.zip"


def build_bundle_zip(entries: list[PackageEntry]) -> bytes:
    output = BytesIO()
    with ZipFile(output, "w") as archive:
        for entry in entries:
            archive.writestr(entry.path, entry.content)
    return output.getvalue()


def write_local_package_objects(
    storage_base_path: str,
    skill_id: int,
    version_id: int,
    entries: list[PackageEntry],
) -> StoredPackageResult:
    records: list[SkillFileWriteRecord] = []
    total_size = 0
    for entry in entries:
        key = skill_storage_key(skill_id, version_id, entry.path)
        write_local_object(storage_base_path, key, entry.content)
        digest = sha256(entry.content).hexdigest()
        records.append(
            SkillFileWriteRecord(
                version_id=version_id,
                file_path=entry.path,
                file_size=entry.size,
                content_type=entry.content_type,
                sha256=digest,
                storage_key=key,
            )
        )
        total_size += entry.size

    bundle = build_bundle_zip(entries)
    bundle_key = bundle_storage_key(skill_id, version_id)
    write_local_object(storage_base_path, bundle_key, bundle)

    return StoredPackageResult(
        files=records,
        bundle_key=bundle_key,
        bundle_size=len(bundle),
        file_count=len(records),
        total_size=total_size,
        bundle_ready=True,
        download_ready=bool(records),
    )


def write_local_object(storage_base_path: str, object_key: str, content: bytes) -> None:
    base = Path(storage_base_path).resolve()
    target = (base / object_key).resolve()
    try:
        target.relative_to(base)
    except ValueError as exc:
        raise ValueError(f"Object key escapes storage base: {object_key}") from exc

    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(content)
