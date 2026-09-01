FROM python:3.12-slim AS build

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_LINK_MODE=copy

WORKDIR /workspace/server-python

RUN apt-get update && \
    apt-get install -y --no-install-recommends build-essential cargo && \
    rm -rf /var/lib/apt/lists/*
RUN pip install --no-cache-dir uv

COPY server-python/pyproject.toml server-python/uv.lock ./
RUN uv sync --frozen --no-dev

FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

RUN groupadd --system --gid 101 app && \
    useradd --system --uid 100 --gid app --create-home app

WORKDIR /workspace/server-python

COPY --from=build /workspace/server-python/.venv ./.venv
COPY server-python/alembic.ini ./alembic.ini
COPY server-python/alembic ./alembic
COPY server-python/app ./app

RUN mkdir -p /var/lib/skillhub/storage && \
    chown -R app:app /workspace/server-python /var/lib/skillhub/storage

USER app

EXPOSE 8080

CMD ["sh", "-c", ".venv/bin/python -m app.migrations upgrade && exec .venv/bin/python -m uvicorn app.main:app --host 0.0.0.0 --port 8080"]
