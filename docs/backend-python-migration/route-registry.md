# Backend Route Registry

This registry is the human-readable source of truth for Java/Python route
ownership during backend migration. Vite proxy config must stay in sync with
Python-owned local development routes.

## Ownership Legend

| Owner | Meaning |
| --- | --- |
| `java` | Active implementation is the existing Spring Boot backend on port 8080. |
| `python` | Active implementation is the FastAPI backend on port 8081. |
| `planned-python` | Planned for Python, but not active until tests and proxy changes land. |

## Routes

| Method | Path | Owner | Notes |
| --- | --- | --- | --- |
| GET | `/.well-known/clawhub.json` | python | ClawHub compatibility discovery metadata. No DB/auth dependency. |
| GET | `/api/v1/health` | python | First milestone route. Mirrors Java `data.message = "UP"` envelope. |
| GET | `/api/v1/labels` | python | Public visible label filters. First PostgreSQL-backed Python route. |
| GET | `/api/web/labels` | python | Frontend alias for public visible label filters. |
| GET | `/api/v1/search` | python | ClawHub compatibility search. Plain ClawHub response, not `ApiResponse`. |
| GET | `/api/web/skills` | python | Public portal skill search. `/api/v1/skills` remains Java-owned ClawHub compatibility. |
| GET | `/api/v1/skills/{namespace}/{slug}/labels` | python | Public anonymous skill labels list. Label mutations remain Java-owned. |
| GET | `/api/web/skills/{namespace}/{slug}/labels` | python | Frontend alias for public anonymous skill labels list. Label mutations remain Java-owned. |
| GET | `/api/v1/skills/{namespace}/{slug}` | python | Public anonymous skill detail. Search/list, mutations, downloads, and auth preview remain Java-owned. |
| GET | `/api/web/skills/{namespace}/{slug}` | python | Frontend alias for public anonymous skill detail. Search/list, mutations, downloads, and auth preview remain Java-owned. |
| GET | `/api/v1/skills/{namespace}/{slug}/resolve` | python | Public anonymous version selector resolution. Download remains Java-owned. |
| GET | `/api/web/skills/{namespace}/{slug}/resolve` | python | Frontend alias for public anonymous version selector resolution. Download remains Java-owned. |
| GET | `/api/v1/skills/{namespace}/{slug}/versions` | python | Public anonymous published version list. Version detail and files are Python-owned; compare and downloads remain Java-owned. |
| GET | `/api/web/skills/{namespace}/{slug}/versions` | python | Frontend alias for public anonymous published version list. Version detail and files are Python-owned; compare and downloads remain Java-owned. |
| GET | `/api/v1/skills/{namespace}/{slug}/versions/{version}` | python | Public anonymous published version detail. Files is Python-owned; compare, downloads, and DELETE remain Java-owned. |
| GET | `/api/web/skills/{namespace}/{slug}/versions/{version}` | python | Frontend alias for public anonymous published version detail. Files is Python-owned; compare, downloads, and DELETE remain Java-owned. |
| GET | `/api/v1/skills/{namespace}/{slug}/versions/{version}/files` | python | Public anonymous skill version files metadata list. Content and downloads remain Java-owned. |
| GET | `/api/web/skills/{namespace}/{slug}/versions/{version}/files` | python | Frontend alias for public anonymous skill version files metadata list. Content and downloads remain Java-owned. |
| GET | `/api/v1/skills/{namespace}/{slug}/tags/{tagName}/files` | python | Public anonymous skill tag files metadata list. Content and downloads remain Java-owned. |
| GET | `/api/web/skills/{namespace}/{slug}/tags/{tagName}/files` | python | Frontend alias for public anonymous skill tag files metadata list. Content and downloads remain Java-owned. |
| * | `/api/**` | java | Default owner for all routes not listed as Python-owned. |
| * | `/oauth2/**` | java | OAuth remains Java-owned. |
