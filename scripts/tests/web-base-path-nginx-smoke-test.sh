#!/bin/sh
set -eu

ROOT_DIR=$(CDPATH='' cd -- "$(dirname -- "$0")/../.." && pwd)
IMAGE="skillhub-web-base-path-smoke:local"
name_root="skillhub-web-root-smoke-$$"
name_subpath="skillhub-web-subpath-smoke-$$"
root_port=$((18080 + ($$ % 1000)))
subpath_port=$((19080 + ($$ % 1000)))

cleanup() {
  docker rm -f "$name_root" "$name_subpath" >/dev/null 2>&1 || true
}
trap cleanup EXIT

wait_for_health() {
  container_name="$1"
  base_url="$2"
  attempts=0
  until [ "$(docker inspect -f '{{.State.Health.Status}}' "$container_name" 2>/dev/null || true)" = "healthy" ]; do
    attempts=$((attempts + 1))
    if [ "$attempts" -ge 30 ]; then
      echo "web image did not become healthy: $base_url" >&2
      docker logs "$container_name" >&2 || true
      return 1
    fi
    sleep 1
  done
  curl -fsS "$base_url/nginx-health" >/dev/null
}

assert_javascript_asset() {
  url="$1"
  headers=$(mktemp)
  body=$(mktemp)
  curl -fsS -D "$headers" -o "$body" "$url"
  grep -Eiq '^Content-Type: (application|text)/javascript' "$headers"
  if grep -Eiq '<!doctype html|<html' "$body"; then
    echo "JavaScript asset fell through to SPA HTML: $url" >&2
    return 1
  fi
  rm -f "$headers" "$body"
}

assert_cache_control() {
  url="$1"
  expected="$2"
  actual=$(curl -fsS -o /dev/null -D - "$url" | tr -d '\r' | sed -n 's/^Cache-Control: //Ip')
  if ! printf '%s' "$actual" | grep -F "$expected" >/dev/null; then
    echo "unexpected Cache-Control for $url: $actual" >&2
    return 1
  fi
}

docker build -q -t "$IMAGE" -f "$ROOT_DIR/web/Dockerfile" "$ROOT_DIR/web" >/dev/null

MSYS_NO_PATHCONV=1 docker run -d --name "$name_root" \
  -p "127.0.0.1:${root_port}:80" \
  -e SKILLHUB_API_UPSTREAM=http://127.0.0.1:9 \
  -e SKILLHUB_WEB_BASE_PATH= \
  "$IMAGE" >/dev/null

root_url="http://127.0.0.1:${root_port}"
wait_for_health "$name_root" "$root_url"
root_asset=$(MSYS_NO_PATHCONV=1 docker exec "$name_root" sh -c \
  'find /usr/share/nginx/html/assets -type f -name "*.js" | head -n 1 | sed "s#^/usr/share/nginx/html##"')
test -n "$root_asset"
assert_javascript_asset "$root_url$root_asset"
curl -fsS "$root_url/dashboard" | grep -F 'id="root"' >/dev/null
assert_cache_control "$root_url/" 'no-cache, must-revalidate'
assert_cache_control "$root_url/index.html" 'no-cache, must-revalidate'
assert_cache_control "$root_url/dashboard" 'no-cache, must-revalidate'
assert_cache_control "$root_url$root_asset" 'public, immutable'
test "$(curl -sS -o /dev/null -w '%{http_code}' "$root_url/api/v1/health")" = "502"
root_guide=$(curl -fsS "$root_url/install/skillhub.md")
printf '%s' "$root_guide" | grep -F "The browser guide belongs to \`$root_url\`." >/dev/null
printf '%s' "$root_guide" | grep -F "The primary CLI registry is \`$root_url\`." >/dev/null
untrusted_https=$(curl -fsS -H 'X-Forwarded-Proto: https' "$root_url/install/skillhub.md")
printf '%s' "$untrusted_https" | grep -F "The browser guide belongs to \`$root_url\`." >/dev/null
for hostile_host in 'evil.example;echo_injected' 'evil.example$(id)' 'evil.example&whoami'; do
  test "$(curl -sS -o /dev/null -w '%{http_code}' -H "Host: $hostile_host" "$root_url/install/skillhub.md")" = "400"
done

MSYS_NO_PATHCONV=1 docker run -d --name "$name_subpath" \
  -p "127.0.0.1:${subpath_port}:80" \
  -e SKILLHUB_API_UPSTREAM=http://127.0.0.1:9 \
  -e SKILLHUB_PUBLIC_BASE_URL="http://127.0.0.1:${subpath_port}/skillhub" \
  -e SKILLHUB_WEB_CLI_REGISTRY_URL="http://skillhub.internal/skillhub" \
  -e SKILLHUB_WEB_BASE_PATH=/skillhub \
  "$IMAGE" >/dev/null

subpath_url="http://127.0.0.1:${subpath_port}"
wait_for_health "$name_subpath" "$subpath_url"
subpath_asset=$(MSYS_NO_PATHCONV=1 docker exec "$name_subpath" sh -c \
  'find /usr/share/nginx/html/assets -type f -name "*.js" | head -n 1 | sed "s#^/usr/share/nginx/html##"')
test -n "$subpath_asset"

test "$(curl -sS -o /dev/null -w '%{http_code}' "$subpath_url/skillhub")" = "301"
test "$(curl -sSI "$subpath_url/skillhub" | tr -d '\r' | sed -n 's/^Location: //p')" = "/skillhub/"
assert_javascript_asset "$subpath_url/skillhub$subpath_asset"
curl -fsS "$subpath_url/skillhub/dashboard" | grep -F 'id="root"' >/dev/null
assert_cache_control "$subpath_url/skillhub/" 'no-cache, must-revalidate'
assert_cache_control "$subpath_url/skillhub/dashboard" 'no-cache, must-revalidate'
assert_cache_control "$subpath_url/skillhub$subpath_asset" 'public, immutable'
curl -fsS "$subpath_url/skillhub/runtime-config.js" | grep -F 'basePath: "/skillhub"' >/dev/null
guide=$(curl -fsS "$subpath_url/skillhub/install/skillhub.md")
legacy_guide=$(curl -fsS "$subpath_url/skillhub/registry/skill.md")
test "$guide" = "$legacy_guide"
printf '%s' "$guide" | grep -F "The browser guide belongs to \`$subpath_url/skillhub\`." >/dev/null
printf '%s' "$guide" | grep -F 'The primary CLI registry is `http://skillhub.internal/skillhub`.' >/dev/null
printf '%s' "$guide" | grep -F 'skillhub install @<namespace>/<slug>' >/dev/null
printf '%s' "$guide" | grep -F -- '--version <version>' >/dev/null
printf '%s' "$guide" | grep -F -- '--registry http://skillhub.internal/skillhub' >/dev/null
test "$(curl -sSI "$subpath_url/skillhub/install/skillhub.md" | tr -d '\r' | sed -n 's/^Cache-Control: //Ip')" = "no-cache"
explicit_hostile=$(curl -fsS -H 'Host: evil.example;echo_injected' "$subpath_url/skillhub/install/skillhub.md")
if printf '%s' "$explicit_hostile" | grep -F 'echo_injected' >/dev/null; then
  echo 'explicit Agent guide must not interpolate request Host' >&2
  exit 1
fi
test "$(curl -fsS "$subpath_url/skillhub/nginx-health")" = "ok"

# Raw-prefix requests must redispatch to the existing proxy locations.
for path in \
  /skillhub/api/v1/health \
  /skillhub/api/web/notifications/sse \
  /skillhub/oauth2/authorization/keycloak \
  /skillhub/login/oauth2/code/keycloak \
  /skillhub/.well-known/oauth-authorization-server; do
  test "$(curl -sS -o /dev/null -w '%{http_code}' "$subpath_url$path")" = "502"
done
test "$(curl -sS -o /dev/null -w '%{http_code}' \
  -X POST -H 'Content-Type: application/octet-stream' --data-binary 'upload-smoke' \
  "$subpath_url/skillhub/api/v1/skills/smoke/publish")" = "502"

# Existing Istio prefix stripping remains valid with the same sub-path image.
assert_javascript_asset "$subpath_url$subpath_asset"
curl -fsS "$subpath_url/dashboard" | grep -F 'id="root"' >/dev/null
test "$(curl -sS -o /dev/null -w '%{http_code}' "$subpath_url/api/v1/health")" = "502"

printf '%s\n' 'web root/sub-path nginx smoke test passed'
