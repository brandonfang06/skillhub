from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from fastapi import FastAPI

from app.skills.compliance_contract import ComplianceProjection


def build_openapi_schema() -> dict[str, Any]:
    app = FastAPI(title="SkillHub Compliance Projection API")

    @app.get(
        "/contracts/compliance-projection",
        response_model=ComplianceProjection,
        tags=["Compliance Contract"],
    )
    def get_compliance_projection_contract() -> ComplianceProjection:
        return ComplianceProjection()

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
