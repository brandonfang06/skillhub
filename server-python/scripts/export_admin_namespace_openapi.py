from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from fastapi import FastAPI

from app.api.admin_namespaces import router as admin_namespace_router


def build_openapi_schema() -> dict[str, Any]:
    app = FastAPI(title="SkillHub Admin Namespace API")
    app.include_router(admin_namespace_router)
    return app.openapi()


def render_openapi_schema() -> str:
    return (
        json.dumps(
            build_openapi_schema(),
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n"
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(render_openapi_schema(), encoding="utf-8")


if __name__ == "__main__":
    main()
