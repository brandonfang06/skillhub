from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from fastapi import FastAPI

from app.api.source_imports import router as source_import_router


def build_openapi_schema() -> dict[str, Any]:
    app = FastAPI(title="SkillHub OSS Source Import API")
    app.include_router(source_import_router)
    return app.openapi()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(build_openapi_schema(), ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
