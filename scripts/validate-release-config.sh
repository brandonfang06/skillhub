#!/bin/sh
set -eu

ENV_FILE="${1:-.env.release}"

if [ ! -f "$ENV_FILE" ]; then
  echo "ERROR: env file not found: $ENV_FILE" >&2
  exit 1
fi

while IFS= read -r raw_line || [ -n "$raw_line" ]; do
  line=$(printf '%s' "$raw_line" | tr -d '\r')
  case "$line" in
    ""|\#*) continue ;;
  esac
  # The quoted line is a NAME=value assignment from the env file.
  # shellcheck disable=SC2163
  export "$line"
done < "$ENV_FILE"

errors=0
warnings=0

error() {
  errors=$((errors + 1))
  echo "ERROR: $*" >&2
}

warn() {
  warnings=$((warnings + 1))
  echo "WARN: $*" >&2
}

require_non_empty() {
  var_name="$1"
  eval "var_value=\${$var_name:-}"
  if [ -z "$var_value" ]; then
    error "$var_name is required"
  fi
}

reject_values() {
  var_name="$1"
  shift
  eval "var_value=\${$var_name:-}"
  if [ -z "$var_value" ]; then
    return 0
  fi
  for bad in "$@"; do
    if [ "$var_value" = "$bad" ]; then
      error "$var_name still uses placeholder/default value: $bad"
      return 0
    fi
  done
}

validate_url() {
  var_name="$1"
  eval "var_value=\${$var_name:-}"
  if [ -z "$var_value" ]; then
    return 0
  fi
  case "$var_value" in
    http://*|https://*) ;;
    *) error "$var_name must start with http:// or https://" ;;
  esac
}

validate_ipv6_literal() {
  printf '%s\n' "$1" | awk '
    function is_hextet(value) {
      return value ~ /^[0-9A-Fa-f]+$/ && length(value) <= 4
    }
    function is_ipv4(value, octets, count, position) {
      count = split(value, octets, ".")
      if (count != 4) return 0
      for (position = 1; position <= count; position++) {
        if (octets[position] !~ /^[0-9]+$/ || length(octets[position]) > 3) return 0
        if (length(octets[position]) > 1 && substr(octets[position], 1, 1) == "0") return 0
        if (octets[position] + 0 > 255) return 0
      }
      return 1
    }
    {
      address = $0
      collapsed = address
      compression_count = gsub(/::/, "", collapsed)
      if (compression_count > 1 || address ~ /:::/) exit 1

      has_compression = compression_count == 1
      if (!has_compression && (address ~ /^:/ || address ~ /:$/)) exit 1

      count = split(address, parts, ":")
      units = 0
      for (position = 1; position <= count; position++) {
        if (parts[position] == "") continue
        if (index(parts[position], ".")) {
          if (position != count || !is_ipv4(parts[position])) exit 1
          units += 2
        } else {
          if (!is_hextet(parts[position])) exit 1
          units++
        }
      }

      if (has_compression) {
        if (units >= 8) exit 1
      } else if (units != 8) {
        exit 1
      }
    }
  '
}

validate_hostname() {
  printf '%s\n' "$1" | awk '
    {
      hostname = $0
      if (substr(hostname, length(hostname), 1) == ".") {
        hostname = substr(hostname, 1, length(hostname) - 1)
      }
      if (length(hostname) > 253) exit 1
      if (hostname == "") exit 1

      count = split(hostname, labels, ".")
      for (position = 1; position <= count; position++) {
        label = labels[position]
        if (label == "" || length(label) > 63 || label !~ /^[A-Za-z0-9-]+$/ || substr(label, 1, 1) == "-" || substr(label, length(label), 1) == "-") exit 1
      }
    }
  '
}

validate_absolute_http_url() {
  var_name="$1"
  label="$2"
  eval "var_value=\${$var_name:-}"
  if [ -z "$var_value" ]; then
    return 0
  fi

  invalid=false
  case "$var_value" in
    http://*) remainder=${var_value#http://} ;;
    https://*) remainder=${var_value#https://} ;;
    *) invalid=true; remainder="" ;;
  esac
  authority=${remainder%%/*}
  case "$authority" in
    ""|*@*|*%*|*\\*|*[[:space:]]*) invalid=true ;;
  esac
  case "$var_value" in
    *\?*|*\#*|*%*|*\\*|*[[:space:]]*) invalid=true ;;
  esac

  case "$authority" in
    \[* )
      if ! printf '%s' "$authority" | grep -Eq '^\[[0-9A-Fa-f:.]+\](:[0-9]{1,5})?$'; then
        invalid=true
      else
        ipv6_literal=${authority#\[}
        ipv6_literal=${ipv6_literal%%\]*}
        if ! validate_ipv6_literal "$ipv6_literal"; then
          invalid=true
        fi
      fi
      ;;
    *)
      if ! printf '%s' "$authority" | grep -Eq '^[A-Za-z0-9.-]+(:[0-9]{1,5})?$'; then
        invalid=true
      else
        hostname=${authority%:*}
        if [ "$hostname" = "$authority" ]; then
          hostname=$authority
        fi
        if ! validate_hostname "$hostname"; then
          invalid=true
        fi
      fi
      ;;
  esac

  case "$authority" in
    \[*\]:*) port=${authority##*:} ;;
    \[*\]) port="" ;;
    *:*) port=${authority##*:} ;;
    *) port="" ;;
  esac
  case "$port" in
    "") ;;
    *[!0-9]*) invalid=true ;;
    *)
      if [ "$port" -lt 1 ] || [ "$port" -gt 65535 ]; then
        invalid=true
      fi
      ;;
  esac

  path=${remainder#"$authority"}
  if [ -n "$path" ] && ! printf '%s' "$path" | grep -Eq "^/[A-Za-z0-9._~!\$&'()*+,;=:@/-]*$"; then
    invalid=true
  fi
  if [ -n "$path" ]; then
    case "/${path#/}/" in
      *"//"*|*"/./"*|*"/../"*) invalid=true ;;
    esac
  fi

  if [ "$invalid" = "true" ]; then
    error "$label must be an absolute HTTP/HTTPS URL without credentials, query, or fragment"
  fi
}

normalized_web_base_path=""

validate_web_base_path() {
  value=${SKILLHUB_WEB_BASE_PATH:-}
  case "$value" in
    ""|"/")
      normalized_web_base_path=""
      ;;
    /*)
      if ! printf '%s' "$value" | grep -Eq '^/[A-Za-z0-9._~/-]+/?$'; then
        error "SKILLHUB_WEB_BASE_PATH is invalid"
        return 0
      fi
      normalized_web_base_path=${value%/}
      case "/${normalized_web_base_path#/}/" in
        *"//"*|*"/./"*|*"/../"*)
          error "SKILLHUB_WEB_BASE_PATH is invalid"
          ;;
      esac
      ;;
    *)
      error "SKILLHUB_WEB_BASE_PATH must be blank, /, or a root-relative path"
      ;;
  esac
}

validate_public_base_path_matches_web() {
  public_without_scheme=${SKILLHUB_PUBLIC_BASE_URL#*://}
  case "$public_without_scheme" in
    */*) public_path=/${public_without_scheme#*/} ;;
    *) public_path="" ;;
  esac
  if [ "$public_path" != "$normalized_web_base_path" ]; then
    error "SKILLHUB_PUBLIC_BASE_URL path must match SKILLHUB_WEB_BASE_PATH"
  fi
}

validate_no_trailing_slash() {
  var_name="$1"
  eval "var_value=\${$var_name:-}"
  case "$var_value" in
    */) error "$var_name must not have a trailing slash" ;;
  esac
}

validate_boolean() {
  var_name="$1"
  eval "var_value=\${$var_name:-}"
  case "$var_value" in
    ""|true|false) ;;
    *) error "$var_name must be true or false" ;;
  esac
}

validate_port() {
  var_name="$1"
  eval "var_value=\${$var_name:-}"
  if [ -z "$var_value" ]; then
    return 0
  fi
  case "$var_value" in
    *[!0-9]*|"") error "$var_name must be numeric" ;;
    *)
      if [ "$var_value" -lt 1 ] || [ "$var_value" -gt 65535 ]; then
        error "$var_name must be between 1 and 65535"
      fi
      ;;
  esac
}

require_non_empty SKILLHUB_PUBLIC_BASE_URL
validate_absolute_http_url SKILLHUB_PUBLIC_BASE_URL "SKILLHUB_PUBLIC_BASE_URL"
validate_no_trailing_slash SKILLHUB_PUBLIC_BASE_URL
validate_web_base_path
validate_public_base_path_matches_web

reject_values POSTGRES_PASSWORD "change-this-postgres-password" "skillhub_demo" "skillhub_dev"
reject_values REDIS_PASSWORD "change-this-redis-password" "skillhub_demo" "skillhub_dev"
reject_values BOOTSTRAP_ADMIN_PASSWORD "replace-this-admin-password" "ChangeMe!2026" "Admin@2026"
if [ "${BOOTSTRAP_ADMIN_ENABLED:-false}" = "true" ]; then
  require_non_empty BOOTSTRAP_ADMIN_PASSWORD
fi
reject_values SKILLHUB_STORAGE_S3_ACCESS_KEY "replace-me"
reject_values SKILLHUB_STORAGE_S3_SECRET_KEY "replace-me"

validate_boolean SESSION_COOKIE_SECURE
validate_boolean BOOTSTRAP_ADMIN_ENABLED
validate_boolean SKILLHUB_STORAGE_S3_FORCE_PATH_STYLE
validate_boolean SKILLHUB_STORAGE_S3_AUTO_CREATE_BUCKET

validate_port POSTGRES_PORT
validate_port REDIS_PORT
validate_port API_PORT
validate_port WEB_PORT

require_non_empty POSTGRES_DB
require_non_empty POSTGRES_USER
require_non_empty POSTGRES_PASSWORD

storage_provider="${SKILLHUB_STORAGE_PROVIDER:-}"
case "$storage_provider" in
  s3)
    require_non_empty SKILLHUB_STORAGE_S3_ENDPOINT
    require_non_empty SKILLHUB_STORAGE_S3_BUCKET
    require_non_empty SKILLHUB_STORAGE_S3_ACCESS_KEY
    require_non_empty SKILLHUB_STORAGE_S3_SECRET_KEY
    require_non_empty SKILLHUB_STORAGE_S3_REGION
    validate_url SKILLHUB_STORAGE_S3_ENDPOINT
    validate_url SKILLHUB_STORAGE_S3_PUBLIC_ENDPOINT
    ;;
  local)
    warn "SKILLHUB_STORAGE_PROVIDER=local is only suitable for non-production or temporary validation"
    ;;
  "")
    error "SKILLHUB_STORAGE_PROVIDER is required"
    ;;
  *)
    error "SKILLHUB_STORAGE_PROVIDER must be either local or s3"
    ;;
esac

if [ -n "${SKILLHUB_WEB_API_BASE_URL:-}" ]; then
  validate_url SKILLHUB_WEB_API_BASE_URL
  validate_no_trailing_slash SKILLHUB_WEB_API_BASE_URL
fi

if [ -n "${SKILLHUB_DEVICE_AUTH_VERIFICATION_URI:-}" ]; then
  validate_absolute_http_url SKILLHUB_DEVICE_AUTH_VERIFICATION_URI "device auth verification URI"
elif [ -n "${DEVICE_AUTH_VERIFICATION_URI:-}" ]; then
  validate_absolute_http_url DEVICE_AUTH_VERIFICATION_URI "device auth verification URI"
fi

if [ "${SESSION_COOKIE_SECURE:-false}" != "true" ]; then
  case "${SKILLHUB_PUBLIC_BASE_URL}" in
    https://*) error "SESSION_COOKIE_SECURE must be true for an HTTPS public URL" ;;
    *) warn "SESSION_COOKIE_SECURE is not true; only acceptable behind plain HTTP during temporary local verification" ;;
  esac
fi

if [ "${POSTGRES_BIND_ADDRESS:-127.0.0.1}" != "127.0.0.1" ]; then
  warn "POSTGRES_BIND_ADDRESS is not 127.0.0.1; confirm database exposure is intended"
fi

if [ "${REDIS_BIND_ADDRESS:-127.0.0.1}" != "127.0.0.1" ]; then
  warn "REDIS_BIND_ADDRESS is not 127.0.0.1; confirm Redis exposure is intended"
fi

oauth_id="${OAUTH2_GITHUB_CLIENT_ID:-}"
oauth_secret="${OAUTH2_GITHUB_CLIENT_SECRET:-}"
if [ -n "$oauth_id" ] && [ -z "$oauth_secret" ]; then
  error "OAUTH2_GITHUB_CLIENT_SECRET is required when OAUTH2_GITHUB_CLIENT_ID is set"
fi
if [ -n "$oauth_secret" ] && [ -z "$oauth_id" ]; then
  error "OAUTH2_GITHUB_CLIENT_ID is required when OAUTH2_GITHUB_CLIENT_SECRET is set"
fi

if [ "$errors" -gt 0 ]; then
  echo "Release config validation failed: $errors error(s), $warnings warning(s)." >&2
  exit 1
fi

echo "Release config validation passed with $warnings warning(s)."
