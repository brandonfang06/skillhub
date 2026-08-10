#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
SMOKE_SCRIPT="$REPO_ROOT/scripts/smoke-test.sh"
TMP_DIR="$(mktemp -d)"

cleanup() {
  rm -rf "$TMP_DIR"
}
trap cleanup EXIT

fail() {
  echo "FAIL: $*" >&2
  exit 1
}

mkdir -p "$TMP_DIR/bin"
cat >"$TMP_DIR/bin/curl" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail

url=""
method="GET"
data=""
cookie_in=""
cookie_out=""
write_code=false
while (($#)); do
  case "$1" in
    -X) method="$2"; shift 2 ;;
    -d) data="$2"; shift 2 ;;
    -b) cookie_in="$2"; shift 2 ;;
    -c) cookie_out="$2"; shift 2 ;;
    -w) write_code=true; shift 2 ;;
    -o|-H|--max-time|--retry|--retry-delay) shift 2 ;;
    -s|-sS) shift ;;
    http://*|https://*) url="$1"; shift ;;
    *) shift ;;
  esac
done

if [[ -n "$cookie_out" ]]; then
  printf '%s\n' "localhost FALSE / FALSE 0 XSRF-TOKEN csrf-token" >>"$cookie_out"
fi
printf '%s\n' "$method $url $data" >>"${SMOKE_CURL_LOG:?SMOKE_CURL_LOG is required}"

status=200
case "$url" in
  */api/v1/auth/me)
    if [[ -n "$cookie_in" && -f "$cookie_in.session" && ! -f "$cookie_in.logged-out" ]]; then
      status=200
    else
      status=401
    fi
    ;;
  */api/v1/namespaces)
    if [[ -n "$cookie_in" && -f "$cookie_in.session" ]]; then status=200; else status=401; fi
    ;;
  */api/v1/auth/local/register)
    [[ -n "$cookie_out" ]] && touch "$cookie_out.session"
    ;;
  */api/v1/auth/logout)
    [[ -n "$cookie_out" ]] && touch "$cookie_out.logged-out"
    ;;
  */api/v1/auth/local/login)
    if [[ "$data" == *'"username":"current-admin"'* && "$data" == *'"password":"current-secret"'* ]]; then
      [[ -n "$cookie_out" ]] && touch "$cookie_out.session"
    else
      status=401
    fi
    ;;
esac

if [[ "$write_code" == true ]]; then
  printf '%s' "$status"
fi
EOF
chmod +x "$TMP_DIR/bin/curl"

run_smoke() {
  local name="$1"
  shift
  local log="$TMP_DIR/$name.curl.log"
  local out="$TMP_DIR/$name.out"
  local status=0
  env PATH="$TMP_DIR/bin:/usr/bin:/bin:$PATH" SMOKE_CURL_LOG="$log" "$@" "$SMOKE_SCRIPT" http://skillhub.test >"$out" 2>&1 || status=$?
  printf '%s\n' "$status"
}

status="$(run_smoke skip-admin env)"
if [[ "$status" != "0" ]]; then
  cat "$TMP_DIR/skip-admin.out" >&2
  fail "default smoke without admin credentials should pass"
fi
grep -Fq "SKIP: Admin label management" "$TMP_DIR/skip-admin.out" \
  || fail "default smoke should skip admin checks"
if grep -Fq "/api/v1/auth/local/login" "$TMP_DIR/skip-admin.curl.log"; then
  fail "default smoke must not attempt admin login"
fi

status="$(run_smoke missing-admin env SMOKE_ADMIN_CHECKS=true)"
[[ "$status" != "0" ]] || fail "forced admin checks without credentials should fail"
grep -Fq "SMOKE_ADMIN_CHECKS=true requires SMOKE_ADMIN_USERNAME and SMOKE_ADMIN_PASSWORD" "$TMP_DIR/missing-admin.out" \
  || fail "missing credentials should produce an actionable error"

status="$(run_smoke explicit-admin env SMOKE_ADMIN_USERNAME=current-admin SMOKE_ADMIN_PASSWORD=current-secret BOOTSTRAP_ADMIN_PASSWORD=wrong-bootstrap)"
if [[ "$status" != "0" ]]; then
  cat "$TMP_DIR/explicit-admin.out" >&2
  fail "explicit smoke credentials should pass"
fi
grep -Fq '"username":"current-admin","password":"current-secret"' "$TMP_DIR/explicit-admin.curl.log" \
  || fail "admin login should use SMOKE_ADMIN credentials"
if grep -Fq 'wrong-bootstrap' "$TMP_DIR/explicit-admin.curl.log"; then
  fail "admin login must not use bootstrap credentials"
fi

echo "smoke-test-admin-mode-test passed"
