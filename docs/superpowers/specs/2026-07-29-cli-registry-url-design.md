# CLI Registry URL Runtime Override Design

## Context

The skill detail page currently builds its npm CLI install command from
`SKILLHUB_PUBLIC_BASE_URL`. Organization browsers can trust the private
SkillHub HTTPS certificate, but Node clients do not consistently share that
trust across Windows and Linux. The short-term organization workaround is to
show an HTTP registry URL for CLI commands while leaving the browser
application, OAuth callbacks, and web API on HTTPS.

## Decision

Add an optional frontend runtime variable:

```text
SKILLHUB_WEB_CLI_REGISTRY_URL
```

The organization deployment can set it to the complete registry origin:

```text
http://skillhub.private-host
```

The generated runtime config exposes this value as `cliRegistryUrl`. The skill
install command uses the configured value when it is a valid absolute HTTP or
HTTPS URL. It removes trailing slashes before placing the value after
`--registry`.

When the variable is absent, blank, or invalid, the command keeps the existing
behavior and uses `SKILLHUB_PUBLIC_BASE_URL` or the current page origin. This
keeps HTTPS as the default for every deployment that does not explicitly opt
in to an alternate CLI registry URL.

## Scope

The change affects only the registry argument rendered by the skill detail
install command:

```text
npx @astron-team/skillhub@latest install <slug> ... --registry <cli-registry-url>
```

It does not change:

- the browser origin or API base URL;
- OAuth and session callback URLs;
- backend route behavior or download authorization;
- the npm package or CLI TLS implementation;
- the generated skill coordinate or namespace argument.

Runtime wiring is added consistently to release Compose, Kustomize base, plain
Kubernetes manifests, the web container entrypoint, and environment-variable
documentation.

## Security And Operational Effects

An HTTP registry sends CLI bearer tokens without transport encryption. The
override is therefore explicit and opt-in rather than inferred by replacing
`https://` in application code.

The CLI stores credentials and inventory by normalized registry URL. Existing
credentials for `https://skillhub.private-host` do not apply to
`http://skillhub.private-host`; users must log in against the HTTP registry or
provide `SKILLHUB_TOKEN`. Existing HTTPS and new HTTP inventory records are
also separate registry scopes.

The HTTP listener must remain reachable without redirecting back to HTTPS, or
Node will encounter the original certificate validation problem after the
redirect.

## Validation

Tests must prove:

- an explicit HTTP runtime URL is used by the rendered SkillHub install
  command;
- trailing slashes are removed;
- an absent, blank, or invalid override preserves the existing HTTPS fallback;
- deployment manifests and the web entrypoint expose the new variable without
  changing `SKILLHUB_PUBLIC_BASE_URL`;
- frontend typecheck, lint, focused tests, Kustomize rendering, Compose config,
  and `git diff --check` pass.
