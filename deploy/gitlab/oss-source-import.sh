#!/bin/sh
set -eu

: "${CI_PROJECT_DIR:?CI_PROJECT_DIR is required}"

importer_root="$CI_PROJECT_DIR/tools/oss-source-importer"
runtime_site="${SKILLHUB_IMPORT_RUNTIME_DIR:-$CI_PROJECT_DIR/.skillhub-import-runtime}"
report_path="${SKILLHUB_IMPORT_REPORT_PATH:-skillhub-oss-import-report.json}"

python -m pip install \
  --disable-pip-version-check \
  --no-compile \
  --require-hashes \
  --target "$runtime_site" \
  --requirement "$importer_root/requirements-runtime.txt"

export PYTHONPATH="$runtime_site${PYTHONPATH:+:$PYTHONPATH}"
exec python "$CI_PROJECT_DIR/tools/oss-source-importer/run_import.py" \
  --json-report "$report_path"
