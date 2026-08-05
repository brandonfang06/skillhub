from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_runtime_script_derives_web_base_path_from_public_url(tmp_path: Path) -> None:
    shell = shutil.which("sh")
    assert shell is not None, "runtime script validation requires a POSIX shell"

    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    docker = bin_dir / "docker"
    docker.write_text(
        """#!/bin/sh
if [ "$1" = "compose" ] && [ "${2:-}" = "version" ]; then
  exit 0
fi
printf '%s\n' "$@" > "$DOCKER_CAPTURE"
""",
        encoding="utf-8",
        newline="\n",
    )
    docker.chmod(0o755)

    runtime_home = tmp_path / "runtime"
    environment = {
        **os.environ,
        "DOCKER_CAPTURE": str(tmp_path / "docker-args.txt"),
        "PATH": f"{bin_dir}{os.pathsep}{os.environ['PATH']}",
        "SKILLHUB_RAW_BASE": ROOT.as_uri(),
    }
    result = subprocess.run(
        [
            shell,
            (ROOT / "scripts" / "runtime.sh").as_posix(),
            "ps",
            "--home",
            runtime_home.as_posix(),
            "--public-url",
            "https://skills.example.com/skillhub/",
        ],
        cwd=ROOT,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    release_env = (runtime_home / ".env.release").read_text(encoding="utf-8")
    assert (
        "SKILLHUB_PUBLIC_BASE_URL=https://skills.example.com/skillhub/" in release_env
    )
    assert "SKILLHUB_WEB_BASE_PATH=/skillhub" in release_env
