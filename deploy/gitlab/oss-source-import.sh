#!/bin/sh
set -eu

: "${CI_PROJECT_DIR:?CI_PROJECT_DIR is required}"

report_path="${SKILLHUB_IMPORT_REPORT_PATH:-skillhub-oss-import-report.json}"

command -v python >/dev/null 2>&1 || {
  echo "Python is required by the SkillHub import stage" >&2
  exit 2
}
command -v git >/dev/null 2>&1 || {
  echo "Git is required by the SkillHub import stage" >&2
  exit 2
}

exec python "$CI_PROJECT_DIR/tools/oss-source-importer/run_import.py" \
  --json-report "$report_path"
