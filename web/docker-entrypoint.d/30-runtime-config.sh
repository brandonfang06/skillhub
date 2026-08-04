#!/bin/sh
set -eu

: "${SKILLHUB_WEB_API_BASE_URL:=}"
: "${SKILLHUB_PUBLIC_BASE_URL:=}"
: "${SKILLHUB_WEB_BASE_PATH:=}"
: "${SKILLHUB_WEB_CLI_REGISTRY_URL:=}"
: "${SKILLHUB_WEB_AUTH_DIRECT_ENABLED:=false}"
: "${SKILLHUB_WEB_AUTH_DIRECT_PROVIDER:=}"
: "${SKILLHUB_LOCAL_REGISTRATION_ENABLED:=true}"

# Session-bootstrap variables are defaulted here so envsubst writes
# `authSessionBootstrapEnabled: "false"` into runtime-config.js instead of leaving
# the literal `${...}` placeholder. They are intentionally NOT exposed in
# compose.release.yml or .env.release.example: the matching server-side switch
# does not exist yet, so surfacing the toggle would let the frontend hit
# /api/v1/auth/session/bootstrap and receive 403. See PR #280 discussion.
: "${SKILLHUB_WEB_AUTH_SESSION_BOOTSTRAP_ENABLED:=false}"
: "${SKILLHUB_WEB_AUTH_SESSION_BOOTSTRAP_PROVIDER:=}"
: "${SKILLHUB_WEB_AUTH_SESSION_BOOTSTRAP_AUTO:=false}"
: "${SKILLHUB_WEB_PLAYGROUND_ENABLED:=false}"
: "${SKILLHUB_WEB_PLAYGROUND_BASE_URL:=}"

case "${SKILLHUB_WEB_BASE_PATH}" in
  ""|"/")
    SKILLHUB_WEB_BASE_PATH=""
    SKILLHUB_WEB_BASE_HREF="/"
    ;;
  /*)
    if ! printf '%s' "${SKILLHUB_WEB_BASE_PATH}" | grep -Eq '^/[A-Za-z0-9._~/-]+/?$'; then
      echo "Invalid SKILLHUB_WEB_BASE_PATH" >&2
      exit 1
    fi
    SKILLHUB_WEB_BASE_PATH="${SKILLHUB_WEB_BASE_PATH%/}"
    case "/${SKILLHUB_WEB_BASE_PATH#/}/" in
      *"//"*|*"/./"*|*"/../"*)
        echo "Invalid SKILLHUB_WEB_BASE_PATH" >&2
        exit 1
        ;;
    esac
    SKILLHUB_WEB_BASE_HREF="${SKILLHUB_WEB_BASE_PATH}/"
    ;;
  *)
    echo "Invalid SKILLHUB_WEB_BASE_PATH" >&2
    exit 1
    ;;
esac

validate_runtime_template_value() {
  variable_name="$1"
  eval "variable_value=\${$variable_name:-}"
  invalid=false
  case "$variable_value" in
    *\"*|*\\*) invalid=true ;;
  esac
  if [ "$(printf '%s' "$variable_value" | wc -l | tr -d ' ')" -ne 0 ] \
    || printf '%s' "$variable_value" | LC_ALL=C grep -q '[[:cntrl:]]'; then
    invalid=true
  fi
  if [ "$invalid" = "true" ]; then
    echo "Invalid runtime template value: $variable_name" >&2
    exit 1
  fi
}

for variable_name in \
  SKILLHUB_WEB_BASE_HREF \
  SKILLHUB_WEB_API_BASE_URL \
  SKILLHUB_PUBLIC_BASE_URL \
  SKILLHUB_WEB_BASE_PATH \
  SKILLHUB_WEB_CLI_REGISTRY_URL \
  SKILLHUB_WEB_AUTH_DIRECT_ENABLED \
  SKILLHUB_WEB_AUTH_DIRECT_PROVIDER \
  SKILLHUB_LOCAL_REGISTRATION_ENABLED \
  SKILLHUB_WEB_AUTH_SESSION_BOOTSTRAP_ENABLED \
  SKILLHUB_WEB_AUTH_SESSION_BOOTSTRAP_PROVIDER \
  SKILLHUB_WEB_AUTH_SESSION_BOOTSTRAP_AUTO \
  SKILLHUB_WEB_PLAYGROUND_ENABLED \
  SKILLHUB_WEB_PLAYGROUND_BASE_URL
do
  validate_runtime_template_value "$variable_name"
done

# Export runtime template variables so envsubst sees shell-assigned defaults.
export \
  SKILLHUB_WEB_BASE_HREF \
  SKILLHUB_WEB_API_BASE_URL \
  SKILLHUB_PUBLIC_BASE_URL \
  SKILLHUB_WEB_BASE_PATH \
  SKILLHUB_WEB_CLI_REGISTRY_URL \
  SKILLHUB_WEB_AUTH_DIRECT_ENABLED \
  SKILLHUB_WEB_AUTH_DIRECT_PROVIDER \
  SKILLHUB_LOCAL_REGISTRATION_ENABLED \
  SKILLHUB_WEB_AUTH_SESSION_BOOTSTRAP_ENABLED \
  SKILLHUB_WEB_AUTH_SESSION_BOOTSTRAP_PROVIDER \
  SKILLHUB_WEB_AUTH_SESSION_BOOTSTRAP_AUTO \
  SKILLHUB_WEB_PLAYGROUND_ENABLED \
  SKILLHUB_WEB_PLAYGROUND_BASE_URL

# Generate index.html with the browser-visible application base.
envsubst '${SKILLHUB_WEB_BASE_HREF}' \
  < /usr/share/nginx/html/index.html.template \
  > /usr/share/nginx/html/index.html

# Generate runtime-config.js
envsubst '${SKILLHUB_WEB_API_BASE_URL} ${SKILLHUB_PUBLIC_BASE_URL} ${SKILLHUB_WEB_BASE_PATH} ${SKILLHUB_WEB_CLI_REGISTRY_URL} ${SKILLHUB_WEB_AUTH_DIRECT_ENABLED} ${SKILLHUB_WEB_AUTH_DIRECT_PROVIDER} ${SKILLHUB_LOCAL_REGISTRATION_ENABLED} ${SKILLHUB_WEB_AUTH_SESSION_BOOTSTRAP_ENABLED} ${SKILLHUB_WEB_AUTH_SESSION_BOOTSTRAP_PROVIDER} ${SKILLHUB_WEB_AUTH_SESSION_BOOTSTRAP_AUTO} ${SKILLHUB_WEB_PLAYGROUND_ENABLED} ${SKILLHUB_WEB_PLAYGROUND_BASE_URL}' \
  < /usr/share/nginx/html/runtime-config.js.template \
  > /usr/share/nginx/html/runtime-config.js

# Generate registry/skill.md with actual public URL
envsubst '${SKILLHUB_PUBLIC_BASE_URL}' \
  < /usr/share/nginx/html/registry/skill.md.template \
  > /usr/share/nginx/html/registry/skill.md
