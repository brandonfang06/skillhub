#!/bin/sh
set -eu

: "${SKILLHUB_WEB_BASE_PATH:=}"
: "${SKILLHUB_NGINX_BASE_PATH_CONFIG:=/etc/nginx/skillhub-base-path.conf}"

case "${SKILLHUB_WEB_BASE_PATH}" in
  ""|"/")
    normalized_base_path=""
    ;;
  /*)
    if ! printf '%s' "${SKILLHUB_WEB_BASE_PATH}" | grep -Eq '^/[A-Za-z0-9._~/-]+/?$'; then
      echo "Invalid SKILLHUB_WEB_BASE_PATH" >&2
      exit 1
    fi
    normalized_base_path=${SKILLHUB_WEB_BASE_PATH%/}
    case "/${normalized_base_path#/}/" in
      *"//"*|*"/./"*|*"/../"*)
        echo "Invalid SKILLHUB_WEB_BASE_PATH" >&2
        exit 1
        ;;
    esac
    first_segment=${normalized_base_path#/}
    first_segment=${first_segment%%/*}
    case "$first_segment" in
      api|oauth2|login|assets|registry|nginx-health|.well-known|runtime-config.js)
        echo "SKILLHUB_WEB_BASE_PATH must not start with a reserved segment: $first_segment" >&2
        exit 1
        ;;
    esac
    ;;
  *)
    echo "Invalid SKILLHUB_WEB_BASE_PATH" >&2
    exit 1
    ;;
esac

if [ -z "$normalized_base_path" ]; then
  printf '%s\n' '# Root deployment: no sub-path routing.' >"${SKILLHUB_NGINX_BASE_PATH_CONFIG}"
  exit 0
fi

# $1 is an Nginx rewrite capture, not a shell parameter.
# shellcheck disable=SC2016
printf 'location = %s {\n    absolute_redirect off;\n    return 301 %s/;\n}\n\nlocation ^~ %s/ {\n    rewrite ^%s/(.*)$ /$1 last;\n}\n' \
  "$normalized_base_path" \
  "$normalized_base_path" \
  "$normalized_base_path" \
  "$normalized_base_path" \
  >"${SKILLHUB_NGINX_BASE_PATH_CONFIG}"
