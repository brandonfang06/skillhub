# SkillHub Python Examples

A minimal, dependency-light (`requests`-only) Python client and runnable
examples for the SkillHub REST API. Use it to search, inspect, download, and
publish skills from Python without shelling out to the CLI.

These files are reference examples, not an officially published Python package.

## Setup

```bash
python -m pip install -r requirements.txt

export SKILLHUB_URL=https://skill.example.com
export SKILLHUB_TOKEN=<your-api-token>
```

`SKILLHUB_TOKEN` is required only for authenticated operations. Generate a token
from the Web UI under Settings → API Tokens or through `POST /api/v1/tokens`.

## Quick start

```python
from skillhub_client import SkillHubClient

client = SkillHubClient()
results = client.search(keyword="email", size=5)
detail = client.get_skill("my-namespace", "my-skill")
resolved = client.resolve("my-namespace", "my-skill", tag="stable")
path = client.download("my-namespace", "my-skill")
client.publish("./my-skill.zip", namespace="my-namespace")
```

Or run the example script:

```bash
python example_usage.py
python example_usage.py publish ./my-skill.zip my-namespace
```

The client accepts root and subpath registry URLs. Keep the subpath in
`SKILLHUB_URL`, for example `https://skill.example.com/skillhub`.

## Supported operations

| Method | Endpoint | Auth |
| --- | --- | --- |
| `search(keyword, namespace, page, size)` | `GET /api/v1/skills` | Optional |
| `get_skill(namespace, slug)` | `GET /api/v1/skills/{ns}/{slug}` | Optional |
| `list_versions(namespace, slug)` | `GET /api/v1/skills/{ns}/{slug}/versions` | Optional |
| `resolve(namespace, slug, version, tag)` | `GET /api/v1/skills/{ns}/{slug}/resolve` | Optional |
| `download(namespace, slug, version, dest)` | `GET /api/v1/skills/{ns}/{slug}[/versions/{v}]/download` | Optional |
| `whoami()` | `GET /api/v1/whoami` | Bearer |
| `publish(zip_path, namespace, request_id)` | `POST /api/v1/publish` | Bearer with `skill:publish` |
| `star(skill_id)` | `PUT /api/v1/skills/{skill_id}/star` | Bearer |
| `rate(skill_id, score)` | `PUT /api/v1/skills/{skill_id}/rating` | Bearer |

The client unwraps the unified `{code, msg, data}` response envelope when one
is present and raises `SkillHubError` for a non-zero business code.
