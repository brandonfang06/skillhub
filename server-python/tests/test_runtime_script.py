from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _run_runtime_up(
    tmp_path: Path, *arguments: str
) -> subprocess.CompletedProcess[str]:
    shell = shutil.which("sh")
    assert shell is not None, "runtime script validation requires a POSIX shell"

    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    docker = bin_dir / "docker"
    docker.write_text(
        """#!/bin/sh
exit 0
""",
        encoding="utf-8",
        newline="\n",
    )
    docker.chmod(0o755)

    runtime_home = tmp_path / "runtime"
    environment = {
        **os.environ,
        "PATH": f"{bin_dir}{os.pathsep}{os.environ['PATH']}",
        "SKILLHUB_RAW_BASE": ROOT.as_uri(),
    }
    return subprocess.run(
        [
            shell,
            (ROOT / "scripts" / "runtime.sh").as_posix(),
            "up",
            *arguments,
            "--home",
            runtime_home.as_posix(),
        ],
        cwd=ROOT,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )


def _stop_command(result: subprocess.CompletedProcess[str]) -> str:
    return next(
        line.strip() for line in result.stdout.splitlines() if "curl -fsSL" in line
    )


def _execute_emitted_stop_command(
    tmp_path: Path, *runtime_arguments: str
) -> tuple[subprocess.CompletedProcess[str], str, list[str]]:
    shell = shutil.which("sh")
    assert shell is not None, "runtime script validation requires a POSIX shell"

    tmp_path.mkdir(parents=True)
    runtime_driver = tmp_path / "runtime-driver.sh"
    runtime_driver.write_text(
        """#!/bin/sh
docker() {
  return 0
}
curl() {
output=""
while [ "$#" -gt 0 ]; do
  case "$1" in
    -o) output="$2"; shift 2 ;;
    -*) shift ;;
    *) shift ;;
  esac
done
: > "$output"
}
. "$RUNTIME_SCRIPT" "$@"
""",
        encoding="utf-8",
        newline="\n",
    )

    down_stub = tmp_path / "down-stub.sh"
    down_stub.write_text(
        '#!/bin/sh\nprintf \'%s\\n\' "$@" > "$DOWN_CAPTURE"\n',
        encoding="utf-8",
        newline="\n",
    )
    raw_base = "https://runtime.example.test/raw path/'quoted;$(touch url-injected)"
    runtime_home = tmp_path / "runtime home 'quoted;$(touch home-injected)"
    environment = {
        **os.environ,
        "CURL_CAPTURE": str(tmp_path / "curl-url.txt"),
        "DOWN_CAPTURE": str(tmp_path / "down-args.txt"),
        "DOWN_STUB": str(down_stub),
        "RUNTIME_SCRIPT": (ROOT / "scripts" / "runtime.sh").as_posix(),
        "SKILLHUB_RAW_BASE": raw_base,
    }
    start_result = subprocess.run(
        [
            shell,
            runtime_driver.as_posix(),
            "up",
            *runtime_arguments,
            "--home",
            runtime_home.as_posix(),
        ],
        cwd=tmp_path,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )
    assert start_result.returncode == 0, start_result.stderr

    stop_driver = """curl() {
  url=""
  while [ "$#" -gt 0 ]; do
    case "$1" in
      -*) shift ;;
      *) url="$1"; shift ;;
    esac
  done
  printf '%s' "$url" > "$CURL_CAPTURE"
  cat "$DOWN_STUB"
}
"""
    stop_result = subprocess.run(
        [shell, "-c", f"{stop_driver}{_stop_command(start_result)}"],
        cwd=tmp_path,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )
    curl_capture = tmp_path / "curl-url.txt"
    down_capture = tmp_path / "down-args.txt"
    captured_url = (
        curl_capture.read_text(encoding="utf-8") if curl_capture.exists() else ""
    )
    captured_arguments = (
        down_capture.read_text(encoding="utf-8").splitlines()
        if down_capture.exists()
        else []
    )
    return stop_result, captured_url, captured_arguments


def test_runtime_script_preserves_aliyun_source_in_stop_command(tmp_path: Path) -> None:
    result = _run_runtime_up(tmp_path, "--aliyun")

    assert result.returncode == 0, result.stderr
    assert _stop_command(result) == (
        f"curl -fsSL '{ROOT.as_uri()}/runtime.sh' | sh -s -- down --aliyun "
        f"--home '{(tmp_path / 'runtime').as_posix()}'"
    )


def test_runtime_script_uses_github_script_path_without_aliyun(tmp_path: Path) -> None:
    result = _run_runtime_up(tmp_path)

    assert result.returncode == 0, result.stderr
    assert _stop_command(result) == (
        f"curl -fsSL '{ROOT.as_uri()}/scripts/runtime.sh' | sh -s -- down "
        f"--home '{(tmp_path / 'runtime').as_posix()}'"
    )


def test_runtime_script_stop_command_round_trips_shell_metacharacters(
    tmp_path: Path,
) -> None:
    for mode, runtime_arguments, url_suffix, expected_arguments in (
        (
            "github",
            (),
            "/scripts/runtime.sh",
            ["down", "--home"],
        ),
        (
            "aliyun",
            ("--aliyun",),
            "/runtime.sh",
            ["down", "--aliyun", "--home"],
        ),
    ):
        case_dir = tmp_path / mode
        stop_result, captured_url, captured_arguments = _execute_emitted_stop_command(
            case_dir, *runtime_arguments
        )

        assert stop_result.returncode == 0, stop_result.stderr
        assert captured_url == (
            "https://runtime.example.test/raw path/'quoted;$(touch url-injected)"
            f"{url_suffix}"
        )
        assert captured_arguments == [
            *expected_arguments,
            (case_dir / "runtime home 'quoted;$(touch home-injected)").as_posix(),
        ]
        assert not (case_dir / "url-injected").exists()
        assert not (case_dir / "home-injected").exists()


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
