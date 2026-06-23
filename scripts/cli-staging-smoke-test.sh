#!/usr/bin/env bash

set -euo pipefail

BASE_URL="${1:-http://localhost:8080}"
ADMIN_USERNAME="${BOOTSTRAP_ADMIN_USERNAME:-admin}"
ADMIN_PASSWORD="${BOOTSTRAP_ADMIN_PASSWORD:-Admin@staging2026}"
SCAN_WAIT_SECONDS="${SMOKE_SCAN_WAIT_SECONDS:-120}"
POLL_INTERVAL_SECONDS="${SMOKE_POLL_INTERVAL_SECONDS:-2}"
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CLI_DIR="$ROOT_DIR/cli"

PASS=0
WORK_DIR="$(mktemp -d)"
PY_WORK_DIR="$(cygpath -w "$WORK_DIR" 2>/dev/null || printf '%s' "$WORK_DIR")"
CLI_HOME="$(cygpath -w "$WORK_DIR/cli-home" 2>/dev/null || printf '%s' "$WORK_DIR/cli-home")"
USER_COOKIE="$WORK_DIR/user.cookie"
ADMIN_COOKIE="$WORK_DIR/admin.cookie"
RESPONSE_FILE="$WORK_DIR/response.body"
CLI_STDOUT_FILE="$WORK_DIR/cli.stdout"
CLI_STDERR_FILE="$WORK_DIR/cli.stderr"
RUN_ID="$(date +%s)$RANDOM"
NAMESPACE="clismoke$RUN_ID"
USERNAME="cliuser$RUN_ID"
EMAIL="$USERNAME@example.com"
PASSWORD="Smoke@2026A"
SKILL_SLUG="cli-skill-$RUN_ID"
SKILL_NAME="$SKILL_SLUG"
HTTP_STATUS=""
HTTP_BODY=""
CLI_STATUS=0
CLI_STDOUT=""
CLI_STDERR=""

cleanup() {
  rm -rf "$WORK_DIR"
}

trap cleanup EXIT

if command -v python >/dev/null 2>&1; then
  PYTHON_BIN=python
elif command -v python3 >/dev/null 2>&1; then
  PYTHON_BIN=python3
else
  echo "FAIL: python3 or python is required"
  exit 1
fi

pass() {
  echo "PASS: $1"
  PASS=$((PASS + 1))
}

fail_exit() {
  echo "FAIL: $1"
  if [[ -n "${CLI_STDOUT:-}" || -n "${CLI_STDERR:-}" ]]; then
    echo "Last CLI status: ${CLI_STATUS:-n/a}"
    if [[ -n "${CLI_STDOUT:-}" ]]; then
      echo "Last CLI stdout:"
      echo "$CLI_STDOUT"
    fi
    if [[ -n "${CLI_STDERR:-}" ]]; then
      echo "Last CLI stderr:"
      echo "$CLI_STDERR"
    fi
  fi
  if [[ -n "${HTTP_STATUS:-}" || -n "${HTTP_BODY:-}" ]]; then
    echo "Last HTTP status: ${HTTP_STATUS:-n/a}"
    if [[ -n "${HTTP_BODY:-}" ]]; then
      echo "Last response body:"
      echo "$HTTP_BODY"
    fi
  fi
  exit 1
}

curl_capture() {
  : > "$RESPONSE_FILE"
  HTTP_STATUS="$(curl --max-time 30 -sS -o "$RESPONSE_FILE" -w "%{http_code}" "$@" || true)"
  HTTP_BODY="$(cat "$RESPONSE_FILE")"
}

expect_status() {
  local description="$1"
  local expected="$2"
  if [[ "$HTTP_STATUS" == "$expected" ]]; then
    pass "$description"
  else
    fail_exit "$description expected HTTP $expected but got $HTTP_STATUS"
  fi
}

run_cli_capture() {
  local description="$1"
  shift
  CLI_STATUS=0
  : > "$CLI_STDOUT_FILE"
  : > "$CLI_STDERR_FILE"
  (
    cd "$CLI_DIR"
    HOME="$CLI_HOME" USERPROFILE="$CLI_HOME" bun src/index.ts "$@"
  ) >"$CLI_STDOUT_FILE" 2>"$CLI_STDERR_FILE" || CLI_STATUS=$?
  CLI_STDOUT="$(cat "$CLI_STDOUT_FILE")"
  CLI_STDERR="$(cat "$CLI_STDERR_FILE")"
  if [[ "$CLI_STATUS" == "0" ]]; then
    pass "$description"
  else
    fail_exit "$description failed with exit code $CLI_STATUS"
  fi
}

csrf_token() {
  local cookie_file="$1"
  awk '$6 == "XSRF-TOKEN" { print $7 }' "$cookie_file" | tail -n 1
}

bootstrap_csrf() {
  local cookie_file="$1"
  curl --max-time 10 -s -c "$cookie_file" "$BASE_URL/api/v1/auth/providers" >/dev/null || true
}

json_field() {
  local json="$1"
  local expr="$2"
  JSON_INPUT="$json" "$PYTHON_BIN" - "$expr" <<'PY'
import json
import os
import sys

expr = sys.argv[1]
value = json.loads(os.environ["JSON_INPUT"])
for part in expr.split("."):
    if part.isdigit():
        value = value[int(part)]
    else:
        value = value[part]
if value is None:
    print("")
elif isinstance(value, bool):
    print(str(value).lower())
elif isinstance(value, (dict, list)):
    print(json.dumps(value, ensure_ascii=False))
else:
    print(value)
PY
}

json_version_field() {
  local json="$1"
  local version="$2"
  local field="$3"
  JSON_INPUT="$json" "$PYTHON_BIN" - "$version" "$field" <<'PY'
import json
import os
import sys

version = sys.argv[1]
field = sys.argv[2]
items = json.loads(os.environ["JSON_INPUT"])["data"]["items"]
for item in items:
    if str(item.get("version")) == version:
        value = item.get(field)
        print("" if value is None else value)
        raise SystemExit(0)
raise SystemExit(1)
PY
}

json_review_id() {
  local json="$1"
  local skill_slug="$2"
  JSON_INPUT="$json" "$PYTHON_BIN" - "$skill_slug" <<'PY'
import json
import os
import sys

skill_slug = sys.argv[1]
items = json.loads(os.environ["JSON_INPUT"])["data"]["items"]
for item in items:
    if str(item.get("skillSlug")) == skill_slug:
        print(item["id"])
        raise SystemExit(0)
raise SystemExit(1)
PY
}

json_search_contains() {
  local json="$1"
  local namespace="$2"
  local skill_slug="$3"
  JSON_INPUT="$json" "$PYTHON_BIN" - "$namespace" "$skill_slug" <<'PY'
import json
import os
import sys

namespace = sys.argv[1]
skill_slug = sys.argv[2]
items = json.loads(os.environ["JSON_INPUT"])["items"]
for item in items:
    if item.get("namespace") == namespace and item.get("slug") == skill_slug:
        raise SystemExit(0)
raise SystemExit(1)
PY
}

create_skill_source() {
  WORK_DIR="$PY_WORK_DIR" SKILL_NAME="$SKILL_NAME" "$PYTHON_BIN" <<'PY'
import os
from pathlib import Path

work_dir = Path(os.environ["WORK_DIR"])
skill_name = os.environ["SKILL_NAME"]
source = work_dir / "skill-src"
source.mkdir(parents=True, exist_ok=True)
(source / "SKILL.md").write_text(
    f"""---
name: {skill_name}
description: CLI staging smoke package
version: 1.0.0
---
# {skill_name}
""",
    encoding="utf-8",
)
(source / "main.py").write_text("print('cli staging smoke')\n", encoding="utf-8")
PY
}

assert_installed_package() {
  local install_root="$1"
  local skill_slug="$2"
  INSTALL_ROOT="$install_root" SKILL_SLUG="$skill_slug" "$PYTHON_BIN" <<'PY'
import os
from pathlib import Path

root = Path(os.environ["INSTALL_ROOT"])
skill_slug = os.environ["SKILL_SLUG"]
skill_md = root / skill_slug / "SKILL.md"
metadata = root / skill_slug / ".skillhub" / "metadata.json"
if not skill_md.exists():
    raise SystemExit(f"missing installed SKILL.md: {skill_md}")
if not metadata.exists():
    raise SystemExit(f"missing installed metadata: {metadata}")
PY
}

echo "=== CLI Staging Smoke Test ==="
echo "Target:    $BASE_URL"
echo "Namespace: $NAMESPACE"
echo "User:      $USERNAME"
echo "Skill:     $SKILL_SLUG"
echo

bootstrap_csrf "$USER_COOKIE"
USER_CSRF="$(csrf_token "$USER_COOKIE")"

curl_capture \
  -b "$USER_COOKIE" \
  -c "$USER_COOKIE" \
  -H "X-XSRF-TOKEN: $USER_CSRF" \
  -H "Content-Type: application/json" \
  -X POST "$BASE_URL/api/v1/auth/local/register" \
  -d "{\"username\":\"$USERNAME\",\"password\":\"$PASSWORD\",\"email\":\"$EMAIL\"}"
expect_status "Smoke user can register and establish a session" "200"
USER_ID="$(json_field "$HTTP_BODY" "data.userId")"
USER_CSRF="$(csrf_token "$USER_COOKIE")"

curl_capture \
  -b "$USER_COOKIE" \
  -c "$USER_COOKIE" \
  -H "X-XSRF-TOKEN: $USER_CSRF" \
  -H "Content-Type: application/json" \
  -X POST "$BASE_URL/api/v1/tokens" \
  -d "{\"name\":\"CLI Smoke $RUN_ID\",\"scopes\":[\"skill:read\",\"skill:publish\"]}"
expect_status "Smoke user can create a CLI API token" "200"
API_TOKEN="$(json_field "$HTTP_BODY" "data.token")"

bootstrap_csrf "$ADMIN_COOKIE"
ADMIN_CSRF="$(csrf_token "$ADMIN_COOKIE")"

curl_capture \
  -b "$ADMIN_COOKIE" \
  -c "$ADMIN_COOKIE" \
  -H "X-XSRF-TOKEN: $ADMIN_CSRF" \
  -H "Content-Type: application/json" \
  -X POST "$BASE_URL/api/v1/auth/local/login" \
  -d "{\"username\":\"$ADMIN_USERNAME\",\"password\":\"$ADMIN_PASSWORD\"}"
expect_status "Bootstrap admin can log in" "200"
ADMIN_CSRF="$(csrf_token "$ADMIN_COOKIE")"

curl_capture \
  -b "$ADMIN_COOKIE" \
  -c "$ADMIN_COOKIE" \
  -H "X-XSRF-TOKEN: $ADMIN_CSRF" \
  -H "Content-Type: application/json" \
  -X POST "$BASE_URL/api/web/namespaces" \
  -d "{\"slug\":\"$NAMESPACE\",\"displayName\":\"CLI Smoke $NAMESPACE\",\"description\":\"cli staging smoke\"}"
expect_status "Bootstrap admin can create a namespace" "200"
NAMESPACE_ID="$(json_field "$HTTP_BODY" "data.id")"

curl_capture \
  -b "$ADMIN_COOKIE" \
  -c "$ADMIN_COOKIE" \
  -H "X-XSRF-TOKEN: $ADMIN_CSRF" \
  -H "Content-Type: application/json" \
  -X POST "$BASE_URL/api/web/namespaces/$NAMESPACE/members" \
  -d "{\"userId\":\"$USER_ID\",\"role\":\"MEMBER\"}"
expect_status "Bootstrap admin can grant namespace membership to the CLI user" "200"

create_skill_source
SKILL_SOURCE="$(cygpath -w "$WORK_DIR/skill-src" 2>/dev/null || printf '%s' "$WORK_DIR/skill-src")"
INSTALL_ROOT="$WORK_DIR/install-root"
INSTALL_ROOT_CLI="$(cygpath -w "$INSTALL_ROOT" 2>/dev/null || printf '%s' "$INSTALL_ROOT")"
mkdir -p "$WORK_DIR/cli-home" "$INSTALL_ROOT"

run_cli_capture \
  "CLI dry-run publish validates the local package through Python backend" \
  publish "$SKILL_SOURCE" \
  --namespace "$NAMESPACE" \
  --visibility public \
  --registry "$BASE_URL" \
  --token "$API_TOKEN" \
  --dry-run \
  --json
[[ "$(json_field "$CLI_STDOUT" "valid")" == "true" ]] || fail_exit "CLI dry-run publish response was not valid"

run_cli_capture \
  "CLI publish uploads the package through Python backend" \
  publish "$SKILL_SOURCE" \
  --namespace "$NAMESPACE" \
  --visibility public \
  --registry "$BASE_URL" \
  --token "$API_TOKEN" \
  --json
PUBLISHED_SLUG="$(json_field "$CLI_STDOUT" "slug")"
PUBLISHED_VERSION="$(json_field "$CLI_STDOUT" "version")"
[[ "$PUBLISHED_SLUG" == "$SKILL_SLUG" ]] || fail_exit "CLI publish returned unexpected slug: $PUBLISHED_SLUG"

curl_capture \
  -b "$USER_COOKIE" \
  -c "$USER_COOKIE" \
  "$BASE_URL/api/web/skills/$NAMESPACE/$PUBLISHED_SLUG"
expect_status "Publisher session can load the CLI-published skill detail" "200"
SKILL_ID="$(json_field "$HTTP_BODY" "data.id")"

VERSION_ID=""
VERSION_STATUS=""
deadline=$((SECONDS + SCAN_WAIT_SECONDS))
while (( SECONDS < deadline )); do
  curl_capture \
    -b "$USER_COOKIE" \
    -c "$USER_COOKIE" \
    "$BASE_URL/api/web/skills/$NAMESPACE/$PUBLISHED_SLUG/versions?size=10"
  if [[ "$HTTP_STATUS" == "200" ]]; then
    VERSION_ID="$(json_version_field "$HTTP_BODY" "$PUBLISHED_VERSION" "id" || true)"
    VERSION_STATUS="$(json_version_field "$HTTP_BODY" "$PUBLISHED_VERSION" "status" || true)"
    if [[ -n "$VERSION_ID" && "$VERSION_STATUS" != "SCANNING" && "$VERSION_STATUS" != "" ]]; then
      break
    fi
    echo "Waiting for scanner consumer: version status=${VERSION_STATUS:-missing}"
  else
    echo "Waiting for versions endpoint: HTTP $HTTP_STATUS"
  fi
  sleep "$POLL_INTERVAL_SECONDS"
done

[[ -n "$VERSION_ID" ]] || fail_exit "Could not resolve CLI-published version id"
if [[ "$VERSION_STATUS" != "PENDING_REVIEW" && "$VERSION_STATUS" != "PUBLISHED" ]]; then
  fail_exit "Scanner consumer did not move CLI-published version out of SCANNING; final status=$VERSION_STATUS"
fi
pass "Scanner consumer processed the CLI publish task"

curl_capture \
  -b "$ADMIN_COOKIE" \
  -c "$ADMIN_COOKIE" \
  "$BASE_URL/api/web/reviews?status=PENDING&namespaceId=$NAMESPACE_ID"
expect_status "Admin can list the pending CLI publish review" "200"
REVIEW_ID="$(json_review_id "$HTTP_BODY" "$PUBLISHED_SLUG" || true)"
[[ -n "$REVIEW_ID" ]] || fail_exit "Could not find pending review for $PUBLISHED_SLUG"

curl_capture \
  -b "$ADMIN_COOKIE" \
  -c "$ADMIN_COOKIE" \
  -H "X-XSRF-TOKEN: $ADMIN_CSRF" \
  -H "Content-Type: application/json" \
  -X POST "$BASE_URL/api/web/reviews/$REVIEW_ID/approve" \
  -d '{"comment":"cli staging smoke approved"}'
expect_status "Admin can approve the CLI-published review" "200"

run_cli_capture \
  "CLI search discovers the approved package through Python backend" \
  search "$PUBLISHED_SLUG" \
  --registry "$BASE_URL" \
  --token "$API_TOKEN" \
  --limit 5 \
  --json
json_search_contains "$CLI_STDOUT" "$NAMESPACE" "$PUBLISHED_SLUG" || fail_exit "CLI search did not return $NAMESPACE/$PUBLISHED_SLUG"

run_cli_capture \
  "CLI install resolves and downloads the approved package through Python backend" \
  install "$PUBLISHED_SLUG" \
  --namespace "$NAMESPACE" \
  --registry "$BASE_URL" \
  --token "$API_TOKEN" \
  --dir "$INSTALL_ROOT_CLI" \
  --force \
  --json
assert_installed_package "$PY_WORK_DIR/install-root" "$PUBLISHED_SLUG"

echo
echo "Results: $PASS passed"
echo "Smoke user id: $USER_ID"
echo "Skill id: $SKILL_ID"
