from __future__ import annotations

import argparse
import json
from pathlib import Path

from fastapi import FastAPI

from app.api.reviews import router as review_router


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("output", type=Path)
    args = parser.parse_args()

    app = FastAPI(title="SkillHub Review API")
    app.include_router(review_router)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(app.openapi(), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
