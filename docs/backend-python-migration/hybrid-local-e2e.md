# Hybrid Local E2E

Use this workflow when Java, Python, and the Vite frontend must run together.

The hybrid stack starts:

- dependency services through Docker Compose
- Java backend on `http://localhost:8080`
- Python backend on `http://localhost:8081`
- Vite frontend on `http://localhost:3000`
- scanner on `http://localhost:8000`

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

Prerequisites:

- Docker Engine with Compose plugin
- Java 21
- Node.js 22 with Corepack
- Python 3.12
- `uv`
- `make`

Install missing basics when needed:

```bash
sudo apt-get update
sudo apt-get install -y make curl ca-certificates openjdk-21-jdk python3.12
```

Install Docker Engine using Docker's official instructions, then verify:

```bash
docker compose version
```

Install Node.js 22 and enable Corepack:

```bash
corepack enable
```

Install `uv` if it is missing:

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
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

