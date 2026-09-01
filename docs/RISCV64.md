# RISC-V (`linux/riscv64`) support

## Current scope

RISC-V support is incremental. The SkillHub Python server and web images have
`linux/riscv64` build and runtime paths. The security scanner and the complete
Docker Compose deployment are not yet supported on RISC-V.

| Component | `linux/riscv64` status | Notes |
| --- | --- | --- |
| `skillhub-server-python` | Supported by release/PR builds | Dependencies are installed on the target architecture. The builder includes C and Rust toolchains for packages that publish source distributions but no RISC-V wheel. The runtime remains Python-only. |
| `skillhub-web` | Supported by release/PR builds | Static assets are built on the Buildx host and served by a target-architecture Nginx runtime. |
| `skillhub-scanner` | Not yet verified | Its Python dependency tree still needs a separate native-extension and runtime audit. |
| PostgreSQL 16 and Redis 7 | Upstream images available | Pin versions and verify them on the target board before production use. |
| Complete Compose stack | Unsupported | `compose.release.yml` starts the unverified scanner, so do not deploy it unchanged on RISC-V. |

## Build the supported images

Register a RISC-V QEMU handler before running these commands on a non-RISC-V
host:

```bash
docker run --privileged --rm tonistiigi/binfmt --install riscv64
docker buildx create --use --name skillhub-riscv64

docker buildx build \
  --platform linux/riscv64 \
  --file server-python/Dockerfile \
  --tag skillhub-server-python:riscv64 \
  --load \
  .

docker buildx build \
  --platform linux/riscv64 \
  --file web/Dockerfile \
  --tag skillhub-web:riscv64 \
  --load \
  web
```

The release workflow publishes `linux/amd64`, `linux/arm64`, and
`linux/riscv64` variants for `skillhub-server-python` and `skillhub-web`.
The scanner remains limited to AMD64/ARM64.

## Runtime identity

The server runtime uses numeric UID `100` and GID `101`, matching the existing
storage-volume ownership contract. Before upgrading a deployment that mounts
local storage, confirm that the mounted path is writable by `100:101`. Do not
recursively change a production volume without a backup and a verified rollback
plan.

## Verification boundary

The pull-request workflow builds both target images, checks their OCI
architecture metadata, executes the application virtualenv Python as UID
`100`/GID `101`, and executes Nginx under RISC-V emulation. This is a
component-image guardrail, not a full-stack integration test.

A native RISC-V smoke with PostgreSQL, Redis, object storage, and a separately
verified scanner remains required before claiming complete deployment support.
On the Windows Docker Desktop host used for the v0.2.18 follow-up, the
containerd image store pulled the official Python RISC-V manifest but failed to
execute its binaries even with a registered QEMU/binfmt handler. A controlled
switch to Docker Desktop's classic image store made the same official Python
image report `riscv64`, proving that the host and emulator can execute RISC-V
and narrowing the local failure to the containerd snapshotter path. The
repository's CI workflow remains the authoritative emulated gate for the
actual SkillHub RISC-V images; local AMD64 image tests remain the executable
developer gate.
