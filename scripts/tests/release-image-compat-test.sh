#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
SERVER_DOCKERFILE="$REPO_ROOT/server-python/Dockerfile"
WEB_DOCKERFILE="$REPO_ROOT/web/Dockerfile"
NGINX_TEMPLATE="$REPO_ROOT/web/nginx.conf.template"
PUBLISH_WORKFLOW="$REPO_ROOT/.github/workflows/publish-images.yml"
RISCV_WORKFLOW="$REPO_ROOT/.github/workflows/riscv64-images.yml"
PR_SCRIPTS_WORKFLOW="$REPO_ROOT/.github/workflows/pr-scripts.yml"

fail() {
  echo "FAIL: $*" >&2
  exit 1
}

grep -Fq 'build-essential cargo' "$SERVER_DOCKERFILE" \
  || fail 'Python target builds must include C and Rust toolchains for source distributions'
grep -Fq 'groupadd --system --gid 101 app' "$SERVER_DOCKERFILE" \
  || fail 'server runtime must retain gid 101 for storage-volume upgrades'
grep -Fq 'useradd --system --uid 100 --gid app --create-home app' "$SERVER_DOCKERFILE" \
  || fail 'server runtime must retain uid 100 for storage-volume upgrades'
grep -Eq '^USER app[[:space:]]*$' "$SERVER_DOCKERFILE" \
  || fail 'server runtime must run as the non-root app user'

head -n 1 "$WEB_DOCKERFILE" | grep -Fqx 'FROM --platform=$BUILDPLATFORM node:22-alpine AS build' \
  || fail 'web assets must build on BUILDPLATFORM for RISC-V images'
grep -Eq '^[[:space:]]*server_tokens off;' "$NGINX_TEMPLATE" \
  || fail 'nginx must suppress its version token'

test "$(grep -Fc 'platforms: linux/amd64,linux/arm64,linux/riscv64' "$PUBLISH_WORKFLOW")" -eq 2 \
  || fail 'publish workflow must enable RISC-V for exactly Server and Web'
test "$(grep -Ec '^[[:space:]]+platforms: linux/amd64,linux/arm64[[:space:]]*$' "$PUBLISH_WORKFLOW")" -eq 1 \
  || fail 'publish workflow must keep Scanner on amd64/arm64 only'
grep -Fq 'platforms: ${{ matrix.platforms }}' "$PUBLISH_WORKFLOW" \
  || fail 'publish workflow must build each image with its own platform matrix'

test -f "$RISCV_WORKFLOW" || fail 'dedicated RISC-V image workflow is required'
grep -Fq -- "- 'server-python/**'" "$RISCV_WORKFLOW" \
  || fail 'RISC-V workflow must watch the Python backend'
grep -Fq 'context: .' "$RISCV_WORKFLOW" \
  || fail 'Python image must build from repository-root context'
grep -Fq 'dockerfile: ./server-python/Dockerfile' "$RISCV_WORKFLOW" \
  || fail 'RISC-V workflow must use the Python server Dockerfile'
grep -Fq -- '--entrypoint .venv/bin/python' "$RISCV_WORKFLOW" \
  || fail 'RISC-V server runtime probe must execute the application virtualenv Python'
grep -Fq -- '--entrypoint nginx' "$RISCV_WORKFLOW" \
  || fail 'RISC-V web runtime probe must execute Nginx'
if grep -Eqi '(^|[/[:space:]])server/|java|maven|mvn|spring' "$RISCV_WORKFLOW"; then
  fail 'RISC-V workflow must remain Python-only'
fi

grep -Fq -- "- 'server-python/Dockerfile'" "$PR_SCRIPTS_WORKFLOW" \
  || fail 'PR scripts workflow must watch the Python image contract'
grep -Fq -- "- '.github/workflows/publish-images.yml'" "$PR_SCRIPTS_WORKFLOW" \
  || fail 'PR scripts workflow must watch the publish matrix'
grep -Fq -- "- '.github/workflows/riscv64-images.yml'" "$PR_SCRIPTS_WORKFLOW" \
  || fail 'PR scripts workflow must watch the RISC-V workflow'
grep -Fq 'bash scripts/tests/release-image-compat-test.sh' "$PR_SCRIPTS_WORKFLOW" \
  || fail 'PR scripts workflow must execute this contract test'

echo 'release-image-compat-test passed'
