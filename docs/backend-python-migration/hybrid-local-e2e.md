# Hybrid Local E2E

Use this workflow when Java, Python, and the Vite frontend must run together.

On Windows and macOS, the hybrid stack starts:

- dependency services through Docker Compose
- Java backend on `http://localhost:8080`
- Python backend on `http://localhost:8081`
- Vite frontend on `http://localhost:3000`
- scanner on `http://localhost:8000`

On Ubuntu, dependency services are organization-managed instead of Docker-managed.

## Windows

Recommended shell: PowerShell.

Prerequisites:

- Docker Desktop
- Git for Windows
- Java 21
- Node.js 22 with Corepack
- Python 3.12
- `uv`

Start the hybrid stack:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts\dev-hybrid.ps1 up
```

Check status:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts\dev-hybrid.ps1 status
```

Run smoke E2E:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts\dev-hybrid.ps1 e2e-smoke
```

Run full E2E:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts\dev-hybrid.ps1 e2e
```

Stop everything:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts\dev-hybrid.ps1 down
```

## macOS

Recommended shell: zsh or bash.

Prerequisites:

- Docker Desktop or Colima
- Java 21
- Node.js 22 with Corepack
- Python 3.12
- `uv`
- `make`

Install missing basics with Homebrew when needed:

```bash
brew install make openjdk@21 node python@3.12 uv
```

If using Colima instead of Docker Desktop:

```bash
brew install colima docker docker-compose
colima start
```

Start the hybrid stack:

```bash
make dev-all-hybrid
```

Run smoke E2E:

```bash
make test-e2e-smoke-hybrid
```

Run full E2E:

```bash
make test-e2e-hybrid
```

Stop everything:

```bash
make dev-all-down
```

## Ubuntu

Recommended shell: bash.

Ubuntu does not use Docker for dependency services. This environment is intended for development
inside the organization network, where Java connects to organization-managed PostgreSQL,
organization-managed Redis, and organization-managed MinIO.

Prerequisites:

- Java 21
- Node.js 22 with Corepack
- Python 3.12
- `uv`
- `make`
- `curl`

Install missing basics when needed:

```bash
sudo apt-get update
sudo apt-get install -y make curl ca-certificates openjdk-21-jdk python3.12
```

Before starting Java, manually adjust this local-only file so the Java backend points at the
organization-managed PostgreSQL, Redis, and MinIO endpoints:

```bash
server/skillhub-app/src/main/resources/application-local.yml
```

Do not commit that local environment change unless the project owner explicitly approves it. Agents
must not edit any file under `server/`.

Install Node.js 22 and enable Corepack:

```bash
corepack enable
```

Install `uv` if it is missing:

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

Start Java in one terminal after `application-local.yml` points to the organization services:

```bash
cd server
./scripts/run-dev-app.sh
```

Start Python in a second terminal:

```bash
cd server-python
UV_CACHE_DIR=.uv-cache uv run uvicorn app.main:app --host 0.0.0.0 --port 8081 --reload
```

Start the Vite frontend in a third terminal:

```bash
cd web
corepack pnpm install --frozen-lockfile
corepack pnpm run dev -- --host 0.0.0.0 --strictPort
```

Run smoke E2E:

```bash
cd web
corepack pnpm run test:e2e:smoke
```

Run full E2E:

```bash
cd web
corepack pnpm run test:e2e
```

## Health Checks

Direct Python:

```bash
curl -i http://localhost:8081/api/v1/health
```

Vite proxy to Python:

```bash
curl -i http://localhost:3000/api/v1/health
```

Both should return the SkillHub envelope with `data.message` set to `UP`.

## Logs

Logs are written under `.dev/`:

- `.dev/server.log`
- `.dev/python.log`
- `.dev/web.log`

For Makefile users:

```bash
SERVICE=backend make dev-logs
SERVICE=python make dev-logs
SERVICE=frontend make dev-logs
```

For Windows PowerShell users, inspect the `.dev/*.log` files directly.
