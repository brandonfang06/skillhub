# SkillHub Python Backend

FastAPI backend used for gradual migration from the Java `server/` backend.

## Local Development

```powershell
uv venv .venv
uv sync
uv run pytest
uv run uvicorn app.main:app --host 0.0.0.0 --port 8081 --reload
```

