from __future__ import annotations

from hashlib import sha256
from io import BytesIO
from zipfile import ZipFile

import pytest

from app.publish.package import PackageEntry
from app.publish.storage import (
    bundle_storage_key,
    build_bundle_zip,
    skill_storage_key,
    write_local_package_objects,
)


def package_entries() -> list[PackageEntry]:
    return [
        PackageEntry("SKILL.md", b"# Demo\n", "text/markdown"),
        PackageEntry("src/main.py", b"print('ok')\n", "text/x-python"),
    ]


def test_storage_key_helpers_match_java_publish_keys() -> None:
    assert skill_storage_key(7, 42, "src/main.py") == "skills/7/42/src/main.py"
    assert bundle_storage_key(7, 42) == "packages/7/42/bundle.zip"


def test_write_local_package_objects_writes_files_and_metadata(tmp_path) -> None:
    result = write_local_package_objects(str(tmp_path), 7, 42, package_entries())

    skill_md_path = tmp_path / "skills" / "7" / "42" / "SKILL.md"
    main_py_path = tmp_path / "skills" / "7" / "42" / "src" / "main.py"
    assert skill_md_path.read_bytes() == b"# Demo\n"
    assert main_py_path.read_bytes() == b"print('ok')\n"

    assert result.file_count == 2
    assert result.total_size == len(b"# Demo\n") + len(b"print('ok')\n")
    assert result.bundle_ready
    assert result.download_ready
    assert result.bundle_key == "packages/7/42/bundle.zip"
    assert result.bundle_size == (tmp_path / "packages" / "7" / "42" / "bundle.zip").stat().st_size

    assert result.files[0].version_id == 42
    assert result.files[0].file_path == "SKILL.md"
    assert result.files[0].file_size == len(b"# Demo\n")
    assert result.files[0].content_type == "text/markdown"
    assert result.files[0].sha256 == sha256(b"# Demo\n").hexdigest()
    assert result.files[0].storage_key == "skills/7/42/SKILL.md"
    assert result.files[1].storage_key == "skills/7/42/src/main.py"


def test_build_bundle_zip_preserves_entry_order_and_bytes() -> None:
    bundle = build_bundle_zip(package_entries())

    with ZipFile(BytesIO(bundle)) as archive:
        assert archive.namelist() == ["SKILL.md", "src/main.py"]
        assert archive.read("SKILL.md") == b"# Demo\n"
        assert archive.read("src/main.py") == b"print('ok')\n"


def test_write_local_package_objects_writes_bundle_zip(tmp_path) -> None:
    write_local_package_objects(str(tmp_path), 7, 42, package_entries())

    with ZipFile(tmp_path / "packages" / "7" / "42" / "bundle.zip") as archive:
        assert archive.namelist() == ["SKILL.md", "src/main.py"]
        assert archive.read("SKILL.md") == b"# Demo\n"
        assert archive.read("src/main.py") == b"print('ok')\n"


def test_write_local_package_objects_rejects_storage_escape(tmp_path) -> None:
    with pytest.raises(ValueError, match="Parent directory paths are not allowed"):
        write_local_package_objects(
            str(tmp_path),
            7,
            42,
            [PackageEntry("../outside.txt", b"escape", "text/plain")],
        )

    assert not (tmp_path.parent / "outside.txt").exists()


def test_empty_package_writes_empty_bundle_and_disables_download(tmp_path) -> None:
    result = write_local_package_objects(str(tmp_path), 7, 42, [])

    assert result.files == []
    assert result.file_count == 0
    assert result.total_size == 0
    assert result.bundle_ready
    assert not result.download_ready
    with ZipFile(tmp_path / "packages" / "7" / "42" / "bundle.zip") as archive:
        assert archive.namelist() == []
