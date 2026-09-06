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

if [ -n "${SKILLHUB_WEB_BASE_PATH}" ]; then
  first_segment=${SKILLHUB_WEB_BASE_PATH#/}
  first_segment=${first_segment%%/*}
  case "$first_segment" in
    api|oauth2|login|assets|install|registry|nginx-health|.well-known|runtime-config.js)
      echo "SKILLHUB_WEB_BASE_PATH must not start with a reserved segment: $first_segment" >&2
      exit 1
      ;;
  esac
fi

validate_runtime_template_value() {
  variable_name="$1"
  variable_value=""
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

if [ -n "${SKILLHUB_WEB_API_BASE_URL}" ]; then
  case "${SKILLHUB_WEB_API_BASE_URL}" in
    http://*|https://*) ;;
    /*)
      if [ "${SKILLHUB_WEB_API_BASE_URL}" != "${SKILLHUB_WEB_BASE_PATH}" ]; then
        echo "SKILLHUB_WEB_API_BASE_URL must match SKILLHUB_WEB_BASE_PATH for same-origin routing" >&2
        exit 1
      fi
      ;;
    *)
      echo "SKILLHUB_WEB_API_BASE_URL must be an absolute HTTP/HTTPS URL or a root-relative path" >&2
      exit 1
      ;;
  esac
fi

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
# envsubst requires literal variable names.
# shellcheck disable=SC2016
envsubst '${SKILLHUB_WEB_BASE_HREF}' \
  < /usr/share/nginx/html/index.html.template \
  > /usr/share/nginx/html/index.html

# Generate runtime-config.js
# shellcheck disable=SC2016
envsubst '${SKILLHUB_WEB_API_BASE_URL} ${SKILLHUB_PUBLIC_BASE_URL} ${SKILLHUB_WEB_BASE_PATH} ${SKILLHUB_WEB_CLI_REGISTRY_URL} ${SKILLHUB_WEB_AUTH_DIRECT_ENABLED} ${SKILLHUB_WEB_AUTH_DIRECT_PROVIDER} ${SKILLHUB_LOCAL_REGISTRATION_ENABLED} ${SKILLHUB_WEB_AUTH_SESSION_BOOTSTRAP_ENABLED} ${SKILLHUB_WEB_AUTH_SESSION_BOOTSTRAP_PROVIDER} ${SKILLHUB_WEB_AUTH_SESSION_BOOTSTRAP_AUTO} ${SKILLHUB_WEB_PLAYGROUND_ENABLED} ${SKILLHUB_WEB_PLAYGROUND_BASE_URL}' \
  < /usr/share/nginx/html/runtime-config.js.template \
  > /usr/share/nginx/html/runtime-config.js

# Generate both the preferred install guide and compatibility route from one
# template. The browser URL and CLI registry URL intentionally remain distinct.
mkdir -p /usr/share/nginx/html/install
guide_public_base_url="${SKILLHUB_PUBLIC_BASE_URL%/}"
if [ -z "$guide_public_base_url" ]; then
  guide_public_base_url='__SKILLHUB_PUBLIC_BASE_URL__'
fi

validate_guide_url() {
  variable_name="$1"
  variable_value=""
  eval "variable_value=\${$variable_name:-}"
  if [ -n "$variable_value" ] && ! printf '%s' "$variable_value" \
    | grep -Eq '^https?://([A-Za-z0-9.-]+|\[[0-9A-Fa-f:.]+\])(:[0-9]{1,5})?(/[A-Za-z0-9._~/-]*)?$'; then
    echo "Invalid guide URL: $variable_name" >&2
    exit 1
  fi
}

validate_guide_url SKILLHUB_PUBLIC_BASE_URL
validate_guide_url SKILLHUB_WEB_CLI_REGISTRY_URL
SKILLHUB_PUBLIC_BASE_URL="${SKILLHUB_PUBLIC_BASE_URL%/}"
SKILLHUB_WEB_CLI_REGISTRY_URL="${SKILLHUB_WEB_CLI_REGISTRY_URL%/}"
guide_cli_registry_url="${SKILLHUB_WEB_CLI_REGISTRY_URL%/}"
if [ -z "$guide_cli_registry_url" ]; then
  guide_cli_registry_url="$guide_public_base_url"
fi
guide_url_config="${SKILLHUB_NGINX_GUIDE_URL_CONFIG:-/etc/nginx/skillhub-guide-public-url.conf}"
if [ "$guide_public_base_url" = '__SKILLHUB_PUBLIC_BASE_URL__' ] || [ "$guide_cli_registry_url" = '__SKILLHUB_PUBLIC_BASE_URL__' ]; then
  printf '%s\n' \
    'if ($http_host !~ "^(?:[A-Za-z0-9.-]+|\\[[0-9A-Fa-f:.]+\\])(?::[0-9]{1,5})?$") { return 400; }' \
    > "$guide_url_config"
else
  printf '%s\n' '# Explicit guide URLs: request Host is not used.' > "$guide_url_config"
fi
SKILLHUB_PUBLIC_BASE_URL="$guide_public_base_url" \
SKILLHUB_WEB_CLI_REGISTRY_URL="$guide_cli_registry_url" \
envsubst '${SKILLHUB_PUBLIC_BASE_URL} ${SKILLHUB_WEB_CLI_REGISTRY_URL}' \
  < /usr/share/nginx/html/registry/skill.md.template \
  > /usr/share/nginx/html/registry/skill.md
cp /usr/share/nginx/html/registry/skill.md /usr/share/nginx/html/install/skillhub.md
