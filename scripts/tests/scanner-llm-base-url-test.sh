#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
SCANNER_DIR="$REPO_ROOT/scanner"
TMP_DIRS=()

cleanup() {
  local status=$?
  local d
  for d in "${TMP_DIRS[@]+"${TMP_DIRS[@]}"}"; do
    rm -rf "$d"
  done
  exit "$status"
}
trap cleanup EXIT

fail() {
  echo "FAIL: $*" >&2
  exit 1
}

tmp="$(mktemp -d)"
TMP_DIRS+=("$tmp")
skill_dir="$tmp/skill"
mkdir -p "$skill_dir/demo-skill"

cat >"$skill_dir/demo-skill/SKILL.md" <<'EOF'
---
name: demo-skill
description: Minimal valid skill used for scanner integration coverage.
license: Apache-2.0
---

This is a harmless demo skill used for scanner integration testing.
EOF

cat >"$skill_dir/demo-skill/run.sh" <<'EOF'
#!/usr/bin/env sh
echo "demo"
EOF
chmod +x "$skill_dir/demo-skill/run.sh"

IMAGE_TAG="skillhub-scanner-llm-base-url-test:$(date +%s)"
docker build --no-cache -t "$IMAGE_TAG" "$SCANNER_DIR" >/dev/null

skill_mount_dir="$skill_dir"
docker_run=(docker run)
if [[ "$(uname -s)" == MINGW* ]]; then
  skill_mount_dir="$(cygpath -w "$skill_dir")"
  docker_run=(env MSYS_NO_PATHCONV=1 docker run)
fi

"${docker_run[@]}" --rm -i \
  -v "$skill_mount_dir:/work/skill:ro" \
  --entrypoint python \
  "$IMAGE_TAG" - <<'PY'
import asyncio
from datetime import datetime, timezone
import http.server
import inspect
import io
import json
import os
from pathlib import Path
import threading
import urllib.request
import zipfile

from fastapi.params import Query
from skill_scanner.core.models import ScanResult
import skill_scanner.api.router as router

signature = inspect.signature(router.scan_uploaded_skill)
if not isinstance(signature.parameters["use_llm"].default, Query):
    raise SystemExit("scan-upload use_llm should remain a Query parameter")
if not isinstance(signature.parameters["llm_provider"].default, Query):
    raise SystemExit("scan-upload llm_provider should remain a Query parameter")

state = {"base_urls": [], "paths": []}


class Handler(http.server.BaseHTTPRequestHandler):
    def log_message(self, format, *args):  # noqa: A003
        return

    def do_POST(self):  # noqa: N802
        length = int(self.headers.get("content-length", "0"))
        self.rfile.read(length)
        state["paths"].append(self.path)

        payload = json.dumps(
            {
                "id": "chatcmpl-test",
                "object": "chat.completion",
                "created": int(datetime.now(timezone.utc).timestamp()),
                "model": "local-model",
                "choices": [
                    {
                        "index": 0,
                        "message": {"role": "assistant", "content": "No findings."},
                        "finish_reason": "stop",
                    }
                ],
                "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
            }
        ).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)


server = http.server.HTTPServer(("127.0.0.1", 0), Handler)
thread = threading.Thread(target=server.serve_forever, daemon=True)
thread.start()

target_base_url = f"http://127.0.0.1:{server.server_port}/v1"
os.environ["SKILL_SCANNER_LLM_BASE_URL"] = target_base_url
os.environ["SKILL_SCANNER_LLM_MODEL"] = "test-model"


class FakeStaticAnalyzer:
    pass


class FakeLLMAnalyzer:
    def __init__(self, model=None, provider=None, base_url=None):
        self.model = model
        self.provider = provider
        self.base_url = base_url
        state["base_urls"].append(base_url)

    def analyze(self, skill_path):
        request = urllib.request.Request(
            self.base_url + "/chat/completions",
            data=b"{}",
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=5) as response:
            response.read()


class FakeSkillScanner:
    def __init__(self, analyzers):
        self.analyzers = analyzers

    def scan_skill(self, skill_path):
        for analyzer in self.analyzers:
            analyze = getattr(analyzer, "analyze", None)
            if callable(analyze):
                analyze(skill_path)

        return ScanResult(
            skill_name="demo-skill",
            skill_directory=str(skill_path),
            findings=[],
            scan_duration_seconds=0.05,
            analyzers_used=["fake-llm"],
            timestamp=datetime.now(timezone.utc),
        )


router.StaticAnalyzer = FakeStaticAnalyzer
router.LLMAnalyzer = FakeLLMAnalyzer
router.SkillScanner = FakeSkillScanner
router.LLM_AVAILABLE = True

request = router.ScanRequest(
    skill_directory="/work/skill/demo-skill",
    use_llm=True,
    llm_provider="openai",
    use_behavioral=False,
    use_aidefense=False,
    aidefense_api_key=None,
)


def build_skill_archive_bytes(skill_root: str) -> bytes:
    skill_path = Path(skill_root)
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in skill_path.rglob("*"):
            if path.is_file():
                archive.writestr(str(path.relative_to(skill_path.parent)), path.read_bytes())
    return buffer.getvalue()


class FakeUploadFile:
    def __init__(self, filename: str, payload: bytes):
        self.filename = filename
        self._payload = payload

    async def read(self) -> bytes:
        return self._payload


try:
    direct_response = asyncio.run(router.scan_skill(request))
    upload_response = asyncio.run(
        router.scan_uploaded_skill(
            file=FakeUploadFile("demo-skill.zip", build_skill_archive_bytes("/work/skill/demo-skill")),
            use_llm=True,
            llm_provider="openai",
            use_behavioral=False,
            use_aidefense=False,
            aidefense_api_key=None,
        )
    )
finally:
    server.shutdown()
    thread.join(timeout=5)

if not getattr(direct_response, "scan_id", None):
    raise SystemExit("scan_skill should still return a scan response")
if not getattr(upload_response, "scan_id", None):
    raise SystemExit("scan_uploaded_skill should still return a scan response")
if len(state["base_urls"]) != 2:
    raise SystemExit(f"expected two LLM analyzer constructions, got {len(state['base_urls'])}")
if any(base_url != target_base_url for base_url in state["base_urls"]):
    raise SystemExit(f"expected every base_url to be {target_base_url}, got {state['base_urls']}")
if len(state["paths"]) != 2:
    raise SystemExit(f"expected two LLM requests, got {state['paths']}")
if not all(path.startswith("/v1/") for path in state["paths"]):
    raise SystemExit(f"expected every request path to start with /v1/, got {state['paths']}")
PY

grep -Fq "name: SKILL_SCANNER_LLM_BASE_URL" "$REPO_ROOT/deploy/k8s/base/scanner-deployment.yaml" \
  || fail "Kubernetes scanner deployment must expose SKILL_SCANNER_LLM_BASE_URL"
grep -Fq "skill-scanner-llm-base-url" "$REPO_ROOT/deploy/k8s/base/secret.yaml.example" \
  || fail "Kubernetes secret example must document skill-scanner-llm-base-url"

echo "scanner-llm-base-url-test passed"
