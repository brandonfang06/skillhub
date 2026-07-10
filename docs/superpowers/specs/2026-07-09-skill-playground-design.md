# Skill Playground Design

## Context

SkillHub is a registry for discovering, publishing, reviewing, and installing
agent skills. Users currently inspect a skill through the skill detail page and
install it through the CLI command shown there. They do not have a fast way to
try the behavior of a skill before installing it.

The desired playground is a pre-install trial surface: users can open a
browser-based agent chat that loads a selected skill as read-only context,
try sample prompts, and decide whether the skill is useful enough to install.

The most important constraint is upstream safety. This repository follows the
open-source SkillHub upstream while carrying a Python-only backend. The
playground must not become a deeply embedded core feature that increases future
upstream merge conflicts. A reusable playground runtime that can serve other
products is preferred.

## Goals

- Let users try a skill from SkillHub before installing it.
- Ship a small V1 quickly with a chat-first user experience.
- Keep SkillHub core registry behavior unchanged.
- Keep skill files read-only in the playground.
- Keep V1 independent from IDE, sandbox, and script execution work.
- Isolate the agent runtime in a sidecar service.
- Make the sidecar contract reusable by other products that can provide skill
  context and user/session identity.
- Keep the SkillHub integration thin enough that upstream changes remain easy
  to follow.
- Keep SkillHub startup, health, and core workflows available when the sidecar or
  model provider is unavailable or removed.

## Non-Goals

- No browser IDE.
- No package file creation, editing, or publishing.
- No execution of skill package scripts or tools in V1.
- No container or Kubernetes sandbox in V1.
- No install side effects.
- No download count mutation from playground usage.
- No changes to publish, review, promotion, search ranking, or lifecycle state.
- No shared database access from the sidecar.
- No dependency from the sidecar on `server-python` internal modules.

## User Experience

### Entry Point

The skill detail page shows a `Try in Playground` action when playground support
is enabled for the deployment and the selected skill version is visible to the
current user. V1 does not maintain a compatibility registry or hide the action
based on skill type. The user decides whether the prompt-only trial is useful.

The entry point opens a dedicated SkillHub route such as
`/space/{namespace}/{slug}/playground`. The route keeps the SkillHub navigation
and product context while giving the read-only context panel and chat transcript
enough room. An in-page drawer and an external sidecar-owned tab are not part of
V1.

### Playground Layout

The playground is chat-first, not IDE-first.

V1 layout:

- Left panel: read-only skill context
  - skill name and namespace
  - selected version
  - README or `SKILL.md` summary
  - references and package file list
  - explicit notice that package files are read-only
- Right panel: agent chat
  - message input
  - streaming assistant responses
  - session reset
  - install call-to-action after a useful trial

### User Flow

1. User finds a skill through search or the skill detail page.
2. User clicks `Try in Playground`.
3. SkillHub creates a short-lived playground capability token.
4. The browser opens a playground session against the sidecar.
5. The sidecar uses the token to fetch authorized skill context from SkillHub.
6. The user enters sample tasks in the chat.
7. The sidecar streams responses based on the selected skill context.
8. If the skill is useful, the user returns to install or copies the existing
   install command.

The playground does not install the skill, does not write skill state, and does
not increment download metrics.

### Session-Only Test Input

V1 allows users to paste sample text into chat as session-only test input. V1
does not accept file uploads. Pasted input belongs only to the playground
session. It is not a package file, is not stored as a skill artifact, and is not
published.

### Prompt-Only Skill Suitability

V1 proves the behavior of text-in/text-out skills. The sidecar supplies the
selected skill's `SKILL.md` and approved reference files as hidden read-only
context, while the user supplies a prompt and may paste sample text into the
message. A skill is a strong playground candidate when its useful behavior can
be judged from the response alone.

Strong candidates include:

- summarizing meeting notes, incidents, tickets, or documents pasted as text
- transforming text into structured output such as action items, release notes,
  checklists, reports, or PR descriptions
- reviewing pasted code, SQL, configuration, policies, or architecture proposals
  against skill-specific guidance
- drafting or rewriting emails, announcements, support replies, documentation,
  or localization copy
- answering domain questions where the required knowledge is contained in the
  skill instructions and bundled references

Weak candidates include skills whose main value requires browser control,
filesystem access, shell commands, repository mutation, image or binary input,
external API calls, secrets, persistent memory, or package-provided tool/script
execution. These skills still receive the same playground entry point. The UI
must state that tools and execution are disabled, and the model must not simulate
successful execution. Suitability guidance informs the user; it is not an
eligibility rule maintained by SkillHub or the sidecar.

## Architecture

### High-Level Split

```
SkillHub Web
  - Try entry point
  - chat UI
  - read-only context panel
  - install CTA

SkillHub Core Backend
  - authenticates the user
  - checks skill/version visibility
  - issues short-lived playground capability tokens
  - exposes existing read/file/download routes

Skill Playground Sidecar
  - owns playground sessions
  - fetches skill context through public/internal HTTP contracts
  - prepares LLM context
  - streams chat responses
  - owns model/provider configuration
```

### Core Isolation Contract

SkillHub core must only provide narrow integration points:

- Web runtime config `playgroundEnabled`, which defaults to false.
- Web runtime config `playgroundBaseUrl`, which is required only when
  `playgroundEnabled` is true.
- `Try in Playground` action on the skill detail page.
- A short-lived capability token endpoint.
- Existing skill read/file/download APIs, reused where possible.

The sidecar must not:

- query the SkillHub database directly
- import code from `server-python`
- write SkillHub domain state
- rely on internal Python function signatures
- require new lifecycle statuses or skill version states
- participate in SkillHub startup, readiness, or liveness checks
- require SkillHub to share its database, Redis, object store, or worker pool

SkillHub must not make a network call to the sidecar while starting, serving
normal registry routes, or issuing a capability token. The browser contacts the
configured sidecar only after the user opens the playground route. The token
endpoint signs local authorization data and does not check sidecar health.

### Failure Isolation

Playground availability is never part of SkillHub availability.

| Failure | Playground behavior | SkillHub core behavior |
| --- | --- | --- |
| Sidecar is stopped or unreachable | Playground route shows an unavailable state | Startup, health, search, detail, install, publish, and review remain unchanged |
| Model provider is stopped or times out | Current session shows a sanitized provider error | No core request or health status changes |
| Sidecar restarts during a session | Ephemeral session is lost and the user may start again | No core state is lost or rolled back |
| Playground deployment is removed | Entry point is hidden when runtime config is disabled | No core package, schema, or infrastructure change is required |

Sidecar retries and timeouts must be bounded so a failing model provider or
context fetch cannot create a retry storm against SkillHub. No SkillHub endpoint
waits for a model response.

### Reusable Sidecar Contract

The sidecar is reusable outside SkillHub. The reusable boundary is a
generic playground session API, not SkillHub-specific database behavior.

The sidecar session contract accepts:

- product identifier
- user identifier
- skill coordinate or context source identifier
- version selector
- short-lived context access token
- optional display metadata

The sidecar owns these responsibilities:

- create session
- resolve context through an adapter
- build agent prompt/context
- stream chat events
- expire session

SkillHub becomes one context provider. Other products can implement the same
context-provider contract without adopting SkillHub internals.

The sidecar is implemented in a separate repository with its own dependency
lock, tests, CI, image, version, and deployment artifacts. SkillHub does not use
a Git submodule or import sidecar source. The repositories share only documented
HTTP and token contracts.

## Capability Token Design

SkillHub core issues a short-lived token that authorizes the sidecar to
read only the selected skill context.

Required claims:

- `iss`: SkillHub deployment identifier
- `aud`: playground sidecar identifier
- `sub`: current user id
- `namespace`
- `slug`
- `version` or `tag`
- `scope`: `playground:read`
- `exp`: short expiry, for example 5 minutes
- `jti`: unique token id

The token does not grant install, publish, lifecycle, admin, or download-metric
mutation authority.

## Sidecar API Sketch

V1 exposes this small sidecar API:

```
POST /v1/playground/sessions
GET  /v1/playground/sessions/{sessionId}/events
POST /v1/playground/sessions/{sessionId}/messages
POST /v1/playground/sessions/{sessionId}/reset
DELETE /v1/playground/sessions/{sessionId}
```

`events` uses Server-Sent Events for V1 streaming. WebSocket is reserved for a
later tool-interaction design.

## LLM Runtime

V1 uses a simple skill-context agent loop:

1. Load `SKILL.md` and selected references as read-only context.
2. Add a system constraint that the package is untrusted and cannot request
   secrets or execution privileges.
3. Add the user's sample prompt.
4. Stream the assistant response.

The runtime is provider-agnostic at the sidecar boundary. V1 targets one
deployment-configured OpenAI-compatible Chat Completions endpoint, including a
vLLM server. The sidecar sends `POST /v1/chat/completions` with streaming enabled
and translates provider chunks into the sidecar's own SSE event contract. The
configured model must support chat and have a valid chat template.

V1 automatically uses one configured default model and does not show a model
selector. The sidecar configuration uses stable model keys and a model catalog
from the beginning so future multi-model support does not require a breaking
session or configuration redesign. A later version may expose the configured
catalog through `GET /v1/playground/models`, accept an optional `modelKey` when a
session is created, and render a dropdown only when more than one model is
available. SkillHub core remains unaware of model selection.

V1 client choice and later alternatives:

1. V1 uses the asynchronous OpenAI Python client with a configurable `base_url`.
   This is the smallest V1 because request, streaming, and error parsing are
   already implemented while the endpoint remains replaceable.
2. Use `httpx` directly against the Chat Completions JSON/SSE contract. This
   removes the SDK dependency but creates more protocol and error-handling code.
3. Add LiteLLM only when one sidecar deployment must route across multiple
   provider protocols, models, budgets, or fallback policies.

LangGraph, AG-UI, Docker SDK, Kubernetes client, and richer agent frameworks are
explicitly later-stage options, not V1 requirements.

### Sidecar Configuration

The sidecar ships an example YAML file with non-secret defaults. A deployment
selects the file with `PLAYGROUND_CONFIG_FILE`. Secrets remain in environment
variables or the deployment's Secret mechanism and are never returned to the
browser.

Example configuration:

```yaml
server:
  host: 0.0.0.0
  port: 8091

session:
  ttl_seconds: 1800
  max_messages: 20
  max_input_chars: 20000

context:
  max_chars: 120000
  providers:
    skillhub:
      kind: skillhub
      base_url: http://host.docker.internal:8080
      connect_timeout_seconds: 5
      read_timeout_seconds: 30

llm:
  kind: openai-compatible
  base_url: http://vllm:8000/v1
  api_key_env: PLAYGROUND_LLM_API_KEY
  connect_timeout_seconds: 10
  read_timeout_seconds: 120
  max_retries: 1
  default_model: primary
  models:
    - key: primary
      display_name: Llama 3 8B Instruct
      upstream_model: NousResearch/Meta-Llama-3-8B-Instruct
      max_output_tokens: 2048
      temperature: 0.2
      extra_body: {}
```

The sidecar validates the full configuration at startup and exits with a clear
operator-facing error when required fields are missing, model keys are
duplicated, or `default_model` does not identify a configured catalog entry.
`api_key_env` names the environment variable to read; the YAML file does not
contain the key value. The provider configuration is sidecar-owned and uses no
`SKILLHUB_` prefix so the same runtime can be reused by other products.

Session requests identify a configured context provider by key, such as
`skillhub`. The browser cannot supply an arbitrary context URL. The sidecar
builds outbound context requests from the allowlisted provider configuration and
rejects unknown provider keys.

## Security And Safety

The playground treats skill package content as untrusted.

V1 safety rules:

- No skill script execution.
- No shell command execution from skill content.
- No network access delegated to skill content.
- No deployment secrets in session context.
- No user API tokens exposed to the sidecar.
- No browser-controlled outbound context URLs.
- No persistence of package modifications.
- Session TTL is required.
- Model/provider errors must not expose secrets.

If future versions add script or tool execution, that must be designed as a
separate sandbox milestone with container isolation, resource limits, network
policy, audit logging, and cleanup guarantees.

## Data And Retention

V1 does not use durable session persistence.

- session metadata and transcripts live only in sidecar memory until TTL expiry
- a sidecar restart clears active sessions and transcripts
- uploaded or pasted sample input is session-only
- no transcript is written back to SkillHub core
- no SkillHub install/download metric is mutated
- no SkillHub or shared Redis/database dependency is required for sessions

Durable transcripts or distributed session storage require a later design. If
product analytics are needed, record them in sidecar-owned telemetry, not in
existing SkillHub install/download semantics.

## Deployment

The playground is an optional, separately deployed product. Its separate
repository owns the sidecar image and deployment artifacts. SkillHub base
manifests and release images do not include the sidecar, and SkillHub readiness
and liveness probes do not check it.

Deployment knobs:

- `SKILLHUB_PLAYGROUND_ENABLED`
- `SKILLHUB_PLAYGROUND_BASE_URL`
- `PLAYGROUND_CONFIG_FILE`
- `PLAYGROUND_LLM_API_KEY` or an operator-selected environment variable named by
  `llm.api_key_env`

SkillHub must continue to run normally when the playground sidecar is absent.
If the sidecar is disabled or unavailable, the UI hides the entry point or shows
a non-blocking unavailable state. `SKILLHUB_PLAYGROUND_ENABLED` defaults to
false. Removing the playground requires only disabling that runtime setting and
removing the separately deployed sidecar.

## Testing Strategy

### SkillHub Core Tests

- playground UI entry point is hidden when disabled
- playground UI entry point is visible when enabled
- token endpoint requires an authenticated user
- token endpoint rejects inaccessible skills
- token endpoint includes only `playground:read`
- playground trial does not increment download count
- SkillHub starts and core routes pass when no sidecar is running
- an unreachable sidecar base URL affects only the playground route
- existing install/download/review/lifecycle tests remain unchanged

### Sidecar Tests

- session creation accepts a valid capability token
- invalid or expired token is rejected
- sidecar fetches context only through configured adapter
- skill context is loaded read-only
- valid YAML loads the configured OpenAI-compatible provider
- unknown context provider keys are rejected without making a network request
- missing model catalog, base URL, or referenced API key fails startup validation
- duplicate model keys and an unknown default model fail startup validation
- V1 sessions always record and use the configured default model key
- provider authorization and timeout errors become sanitized playground events
- message endpoint streams agent responses
- session reset clears transcript state
- session expiry prevents further messages
- sidecar restart loses only sidecar-owned ephemeral sessions

### Integration Smoke

- start SkillHub plus sidecar
- login as a user who can view a skill
- open skill detail
- click `Try in Playground`
- send a sample prompt
- receive a streamed response
- confirm no install/download metric changed
- stop the model provider and confirm only the playground reports an error
- stop the sidecar and confirm SkillHub health, search, detail, and install remain
  available
- disable playground runtime config and confirm SkillHub runs without the entry
  point or any sidecar deployment

## Upstream Safety Checklist

Before implementing or reviewing any playground change, verify:

- Does this change modify core lifecycle, review, publish, install, or search
  behavior? If yes, reject or split it out of V1.
- Does this require a SkillHub DB schema change? If yes, reject for V1 unless it
  is strictly local/sidecar-owned.
- Does the sidecar depend on `server-python` internals? If yes, replace it with
  an HTTP or token contract.
- Does the web change touch more than the skill detail entry point, route, or
  runtime config? If yes, justify it explicitly.
- Can SkillHub still run with playground disabled or absent? It must.
- Do SkillHub health checks or base deployment manifests require the sidecar? They
  must not.
- Does removing the sidecar require a SkillHub schema or infrastructure rollback?
  It must not.
- Could the sidecar be used by another product with a different context adapter?
  It must.

## Recommendation

Ship V1 as a chat-first, read-only playground backed by an optional sidecar.
Keep SkillHub core limited to a feature flag, a thin UI entry point, and a
short-lived capability token. Avoid script execution, IDE features, and domain
state mutations until the pre-install trial value is proven.

Ship the sidecar from a separate repository and treat failure isolation as a
release gate. This gives users a fast way to try skills, keeps upstream-following
work manageable, and creates a runtime that can be reused by other products
without becoming a SkillHub availability dependency.
