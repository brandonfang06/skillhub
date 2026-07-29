"""Run the scanner adapter CLI directly from the project checkout."""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scanner_adapter.cli import main  # noqa: E402, I001


if __name__ == "__main__":
    raise SystemExit(main())
