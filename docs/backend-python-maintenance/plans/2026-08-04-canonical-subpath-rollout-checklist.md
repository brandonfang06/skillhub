# Canonical Subpath One-Week Rollout Checklist

**Canonical URL:** `https://ai-coding-platform.tsmc.com/skillhub`

**DNS:** `ai-coding-platform.tsmc.com` CNAME to
`skillhub-test.ftest.tsmc.com`

## Ownership Boundary

- Organization DNS owns the CNAME.
- The Istio ingress platform owns TLS termination, the Gateway listener, and
  the `ai-coding-platform-tls` Secret.
- SkillHub owns the canonical VirtualService, runtime ConfigMap values,
  application images, and Keycloak client settings.
- The certificate covers `ai-coding-platform.tsmc.com`; URL paths are not part
  of a certificate SAN.
- The private key and certificate chain must not be committed to this repo or
  mounted into SkillHub web/backend Pods.

## D-7 To D-6: Certificate And Gateway

- Request a server certificate whose SAN contains exactly
  `ai-coding-platform.tsmc.com` and whose issuing CA is trusted by organization
  browsers.
- Confirm the existing Gateway resource name, namespace, selector, and the
  ingress gateway workload namespace from the platform team.
- Confirm whether the platform team creates the TLS Secret or permits this
  command in the gateway credential namespace:

```text
kubectl -n <gateway-credential-namespace> create secret tls ai-coding-platform-tls --cert=fullchain.pem --key=private-key.pem --dry-run=client -o yaml
```

- Deliver the resulting manifest through the organization's secret-management
  process. Do not redirect it into a repository file.
- Preserve the existing `skillhub-test.ftest.tsmc.com` server and add a new
  HTTPS server for `ai-coding-platform.tsmc.com` with `tls.mode: SIMPLE` and
  `credentialName: ai-coding-platform-tls`.

## D-5: TLS And Host Routing Preflight

- Confirm the Secret contains `tls.crt` and `tls.key` and the full chain is in
  the order required by the organization ingress platform.
- Confirm the leaf certificate SAN and validity window.
- Run Istio analysis and check ingress gateway logs for missing/invalid
  credential errors.
- Verify SNI before application cutover:

```text
openssl s_client -connect skillhub-test.ftest.tsmc.com:443 -servername ai-coding-platform.tsmc.com -showcerts
```

The returned leaf certificate must cover `ai-coding-platform.tsmc.com`.

## D-4: Identity And Runtime Configuration

- Add the exact Keycloak redirect URI:
  `https://ai-coding-platform.tsmc.com/skillhub/login/oauth2/code/keycloak`.
- Set Keycloak Root URL and Home URL to the canonical URL.
- Set Keycloak Web Origins to `https://ai-coding-platform.tsmc.com` without a
  path.
- Configure:

```text
SKILLHUB_PUBLIC_BASE_URL=https://ai-coding-platform.tsmc.com/skillhub
SKILLHUB_WEB_BASE_PATH=/skillhub
SKILLHUB_WEB_API_BASE_URL=
SKILLHUB_DEVICE_AUTH_VERIFICATION_URI=
SKILLHUB_SESSION_COOKIE_SECURE=true
```

- Preserve the independent `SKILLHUB_WEB_CLI_REGISTRY_URL` value.
- Set forwarded-proto trust only if the Gateway sanitizes the header and web
  Pods cannot be accessed directly.

## D-3: Application And VirtualService

- Deploy the reviewed subpath-aware web/backend images.
- Apply the canonical VirtualService with host
  `ai-coding-platform.tsmc.com`, exact `/skillhub`, prefix `/skillhub/`, rewrite
  `/`, and route to `skillhub-web:80`.
- Keep the old test-host VirtualService separate and operations-only.
- Run release validation, Kustomize rendering, and Pod readiness checks.

## D-2: User Scenarios And Rollback Drill

- Verify landing, login, OAuth callback, dashboard, skill detail, review lazy
  chunk, download, CSV export, SSE, CLI browser auth, logout, and deep-link
  refresh at desktop and mobile viewports.
- Confirm all browser requests remain under `/skillhub` and no redirect reaches
  the old host.
- Confirm the session cookie is Secure and has `Path=/skillhub`.
- Confirm authenticated downloads remain required and no new anonymous
  analytics records are created.
- Drill rollback: remove or disable the canonical VirtualService, restore the
  previous application ConfigMap/images, and keep the old operations endpoint
  available. The certificate Secret may remain installed.

## D-1 And Cutover

- Freeze unrelated deployment changes.
- Record image digests, ConfigMap values, Gateway/VirtualService revisions,
  Keycloak settings, and rollback owner.
- Re-run TLS, OAuth, authenticated browser, and viewport checks.
- Publish the canonical URL only after all checks pass.
- Monitor ingress TLS errors, OAuth failures, 404/5xx rates, lazy chunk errors,
  SSE reconnects, and download authorization for the first rollout window.

## Go/No-Go Gates

- Certificate SAN, chain, expiry, and organization trust are verified.
- Gateway accepts canonical TLS SNI and HTTP Host.
- VirtualService matches only the intended canonical host and `/skillhub`
  paths.
- Runtime URL/base-path validation passes.
- Keycloak callback and origin are exact.
- Authenticated production-like E2E passes at both viewports.
- Named rollback owner and tested rollback steps are available.
