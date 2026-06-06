from fastapi import APIRouter

router = APIRouter()


@router.get("/.well-known/clawhub.json")
def clawhub_config() -> dict[str, str]:
    return {"apiBase": "/api/v1"}
