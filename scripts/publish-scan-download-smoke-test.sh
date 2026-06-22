#!/usr/bin/env bash

set -euo pipefail

BASE_URL="${1:-http://localhost:8080}"
ADMIN_USERNAME="${BOOTSTRAP_ADMIN_USERNAME:-admin}"
ADMIN_PASSWORD="${BOOTSTRAP_ADMIN_PASSWORD:-Admin@staging2026}"
SCAN_WAIT_SECONDS="${SMOKE_SCAN_WAIT_SECONDS:-120}"
POLL_INTERVAL_SECONDS="${SMOKE_POLL_INTERVAL_SECONDS:-2}"

PASS=0
WORK_DIR="$(mktemp -d)"
PY_WORK_DIR="$(cygpath -w "$WORK_DIR" 2>/dev/null || printf '%s' "$WORK_DIR")"
USER_COOKIE="$WORK_DIR/user.cookie"
ADMIN_COOKIE="$WORK_DIR/admin.cookie"
RESPONSE_FILE="$WORK_DIR/response.body"
RUN_ID="$(date +%s)$RANDOM"
SLUG="scansmoke$RUN_ID"
USERNAME="scanuser$RUN_ID"
EMAIL="$USERNAME@example.com"
PASSWORD="Smoke@2026A"
SKILL_NAME="Scan Smoke Skill $SLUG"
HTTP_STATUS=""
HTTP_BODY=""

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

json_audit_completed() {
  local json="$1"
  JSON_INPUT="$json" "$PYTHON_BIN" - <<'PY'
import json
import os

items = json.loads(os.environ["JSON_INPUT"])["data"]
if not items:
    raise SystemExit(1)
audit = items[0]
if not audit.get("scanId") or not audit.get("scannedAt"):
    raise SystemExit(1)
print(audit.get("verdict") or "")
PY
}

create_skill_package() {
  WORK_DIR="$PY_WORK_DIR" SKILL_NAME="$SKILL_NAME" "$PYTHON_BIN" <<'PY'
import os
from pathlib import Path
from zipfile import ZipFile

work_dir = Path(os.environ["WORK_DIR"])
skill_name = os.environ["SKILL_NAME"]
skill_md = f"""---
name: {skill_name}
description: Containerized scanner smoke package
version: 1.0.0
---
# {skill_name}
"""
with ZipFile(work_dir / "skill.zip", "w") as archive:
    archive.writestr("SKILL.md", skill_md)
    archive.writestr("src/main.py", "print('scan smoke')\n")
PY
}

echo "=== Publish Scan Download Smoke Test ==="
echo "Target:    $BASE_URL"
echo "Namespace: $SLUG"
echo "User:      $USERNAME"
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
  -d "{\"slug\":\"$SLUG\",\"displayName\":\"Scan Smoke $SLUG\",\"description\":\"publish scan download smoke\"}"
expect_status "Bootstrap admin can create a namespace" "200"
NAMESPACE_ID="$(json_field "$HTTP_BODY" "data.id")"

curl_capture \
  -b "$ADMIN_COOKIE" \
  -c "$ADMIN_COOKIE" \
  -H "X-XSRF-TOKEN: $ADMIN_CSRF" \
  -H "Content-Type: application/json" \
  -X POST "$BASE_URL/api/web/namespaces/$SLUG/members" \
  -d "{\"userId\":\"$USER_ID\",\"role\":\"MEMBER\"}"
expect_status "Bootstrap admin can grant namespace membership to the smoke user" "200"

create_skill_package
[[ -f "$WORK_DIR/skill.zip" ]] || fail_exit "Skill package was not created at $WORK_DIR/skill.zip"
UPLOAD_FILE="$(cygpath -m "$WORK_DIR/skill.zip" 2>/dev/null || printf '%s' "$WORK_DIR/skill.zip")"
curl_capture \
  -b "$USER_COOKIE" \
  -c "$USER_COOKIE" \
  -H "X-XSRF-TOKEN: $USER_CSRF" \
  -F "file=@$UPLOAD_FILE;type=application/zip" \
  -F "visibility=PUBLIC" \
  "$BASE_URL/api/web/skills/$SLUG/publish"
expect_status "Namespace owner can publish a skill package" "200"
SKILL_SLUG="$(json_field "$HTTP_BODY" "data.slug")"
VERSION="$(json_field "$HTTP_BODY" "data.version")"

curl_capture \
  -b "$USER_COOKIE" \
  -c "$USER_COOKIE" \
  "$BASE_URL/api/web/skills/$SLUG/$SKILL_SLUG"
expect_status "Owner can load the newly published skill detail" "200"
SKILL_ID="$(json_field "$HTTP_BODY" "data.id")"

VERSION_ID=""
VERSION_STATUS=""
deadline=$((SECONDS + SCAN_WAIT_SECONDS))
while (( SECONDS < deadline )); do
  curl_capture \
    -b "$USER_COOKIE" \
    -c "$USER_COOKIE" \
    "$BASE_URL/api/web/skills/$SLUG/$SKILL_SLUG/versions?size=10"
  if [[ "$HTTP_STATUS" == "200" ]]; then
    VERSION_ID="$(json_version_field "$HTTP_BODY" "$VERSION" "id" || true)"
    VERSION_STATUS="$(json_version_field "$HTTP_BODY" "$VERSION" "status" || true)"
    if [[ -n "$VERSION_ID" && "$VERSION_STATUS" != "SCANNING" && "$VERSION_STATUS" != "" ]]; then
      break
    fi
    echo "Waiting for scanner consumer: version status=${VERSION_STATUS:-missing}"
  else
    echo "Waiting for versions endpoint: HTTP $HTTP_STATUS"
  fi
  sleep "$POLL_INTERVAL_SECONDS"
done

[[ -n "$VERSION_ID" ]] || fail_exit "Could not resolve published version id"
if [[ "$VERSION_STATUS" != "PENDING_REVIEW" && "$VERSION_STATUS" != "PUBLISHED" ]]; then
  fail_exit "Scanner consumer did not move version out of SCANNING; final status=$VERSION_STATUS"
fi
pass "Scanner consumer processed the publish task and restored reviewable status"

AUDIT_VERDICT=""
deadline=$((SECONDS + SCAN_WAIT_SECONDS))
while (( SECONDS < deadline )); do
  curl_capture \
    -b "$USER_COOKIE" \
    -c "$USER_COOKIE" \
    "$BASE_URL/api/v1/skills/$SKILL_ID/versions/$VERSION_ID/security-audit?scannerType=skill-scanner"
  if [[ "$HTTP_STATUS" == "200" ]]; then
    AUDIT_VERDICT="$(json_audit_completed "$HTTP_BODY" || true)"
    if [[ -n "$AUDIT_VERDICT" ]]; then
      break
    fi
    echo "Waiting for security audit evidence"
  else
    echo "Waiting for security audit endpoint: HTTP $HTTP_STATUS"
  fi
  sleep "$POLL_INTERVAL_SECONDS"
done
[[ -n "$AUDIT_VERDICT" ]] || fail_exit "Security audit did not record scan evidence"
pass "Security audit exposes completed scanner evidence ($AUDIT_VERDICT)"

curl_capture \
  -b "$ADMIN_COOKIE" \
  -c "$ADMIN_COOKIE" \
  "$BASE_URL/api/web/reviews?status=PENDING&namespaceId=$NAMESPACE_ID"
expect_status "Admin can list pending reviews for the smoke namespace" "200"
REVIEW_ID="$(json_review_id "$HTTP_BODY" "$SKILL_SLUG" || true)"
[[ -n "$REVIEW_ID" ]] || fail_exit "Could not find pending review for $SKILL_SLUG"

curl_capture \
  -b "$ADMIN_COOKIE" \
  -c "$ADMIN_COOKIE" \
  -H "X-XSRF-TOKEN: $ADMIN_CSRF" \
  -H "Content-Type: application/json" \
  -X POST "$BASE_URL/api/web/reviews/$REVIEW_ID/approve" \
  -d '{"comment":"scan smoke approved"}'
expect_status "Admin can approve the scanned review" "200"

DOWNLOAD_FILE="$WORK_DIR/download.zip"
DOWNLOAD_STATUS="$(curl --max-time 30 -sS -L -o "$DOWNLOAD_FILE" -w "%{http_code}" \
  -b "$USER_COOKIE" \
  -c "$USER_COOKIE" \
  "$BASE_URL/api/web/skills/$SLUG/$SKILL_SLUG/download" || true)"
if [[ "$DOWNLOAD_STATUS" != "200" ]]; then
  HTTP_STATUS="$DOWNLOAD_STATUS"
  HTTP_BODY=""
  fail_exit "Owner could not download the approved skill package"
fi

PY_DOWNLOAD_FILE="$(cygpath -w "$DOWNLOAD_FILE" 2>/dev/null || printf '%s' "$DOWNLOAD_FILE")"
DOWNLOAD_FILE="$PY_DOWNLOAD_FILE" "$PYTHON_BIN" <<'PY'
import os
from pathlib import Path
from zipfile import ZipFile

download = Path(os.environ["DOWNLOAD_FILE"])
if download.stat().st_size <= 0:
    raise SystemExit("downloaded package is empty")
with ZipFile(download) as archive:
    names = set(archive.namelist())
    if "SKILL.md" not in names:
        raise SystemExit("downloaded package is missing SKILL.md")
PY
pass "Owner can download the approved package from object storage"

echo
echo "Results: $PASS passed"
echo "Smoke user id: $USER_ID"
