from fastapi import APIRouter

from app.core.public_url import to_public_path

router = APIRouter()


@router.get("/.well-known/clawhub.json")
def clawhub_config() -> dict[str, str]:
    return {"apiBase": to_public_path("/api/v1")}
