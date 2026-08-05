FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_LINK_MODE=copy

WORKDIR /workspace/server-python

RUN pip install --no-cache-dir uv

COPY server-python/pyproject.toml server-python/uv.lock ./
RUN uv sync --frozen --no-dev

COPY server-python/alembic.ini ./alembic.ini
COPY server-python/alembic ./alembic
COPY server-python/app ./app

EXPOSE 8080

CMD ["sh", "-c", ".venv/bin/python -m app.migrations upgrade && exec .venv/bin/python -m uvicorn app.main:app --host 0.0.0.0 --port 8080"]
