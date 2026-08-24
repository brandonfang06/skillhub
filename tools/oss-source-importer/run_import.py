from __future__ import annotations

import sys
from importlib import import_module
from pathlib import Path

SOURCE_ROOT = Path(__file__).resolve().parent / "src"
sys.path.insert(0, str(SOURCE_ROOT))

main = import_module("skillhub_oss_importer.cli").main


if __name__ == "__main__":
    raise SystemExit(main())
