# Mock Auth Flow Scenarios

Date: 2026-06-20

This plan tracks product-level backend flow coverage after the Python cutover.
The first pass uses mock/session auth so the routes can be validated without
depending on organization OIDC, browser state, or external Keycloak setup.

## Order

1. User discovery and download flow
   - Login with mock local session.
   - Search the catalog.
   - Open skill detail.
   - List versions.
   - List version files.
   - Read one file.
   - Download the latest package.
   - Verify: the same session user reaches auth-aware readers and download
     returns the expected attachment bytes.

2. Publisher and review flow
   - Login as publisher and reviewer.
   - Publish a skill package.
   - Inspect pending review detail and files.
   - Approve the review.
   - Verify: the approved skill can be downloaded by the publisher/user flow.

3. Scanner and review evidence flow
   - Publish with scanner enabled through a route-level fake write result.
   - Inspect scan task/audit state.
   - Review the resulting security evidence.
   - Verify: scanner payload shape and review visibility match the Python
     backend contract.

4. CLI install/search/publish flow
   - Exercise CLI search, resolve, install/download, dry-run publish, and
     publish against the Python CLI endpoints.
   - Verify: CLI-visible contracts stay compatible with the backend flow.

5. Browser smoke flow
   - Keep this thin: login, search, detail, publish/review/download happy path.
   - Verify: frontend route wiring matches the backend contracts already covered
     by the deeper backend and CLI tests.

## Current Milestone

Implement scenarios 1-4 as route-level backend regression tests using mock auth
and injected readers. This establishes the user-facing order of operations
without requiring real OIDC, external Keycloak setup, Redis, or scanner services.

Scenario 5 is intentionally deferred until the backend and CLI flow coverage is
stable, because browser smoke tests should stay thin and depend on the contracts
covered here.

## Progress

- Scenario 1 is covered by `tests/test_mock_auth_user_discovery_flow.py`.
- Scenario 2 is covered by the expanded
  `tests/test_publish_review_download_session_flow.py`.
- Scenario 3 is covered at the route-flow level by
  `tests/test_mock_auth_scanner_evidence_flow.py`; lower-level Redis stream and
  scan worker details remain covered by the existing scanner unit tests.
- Scenario 4 is covered at the backend CLI contract level by
  `tests/test_mock_auth_cli_flow.py`; the TypeScript CLI command integration
  tests remain the process-level guard for install/publish commands.
- Scenario 5 is covered for the public search/detail/download browser path by
  `web/e2e/browser-flow-mock-api.spec.ts`. It uses Playwright API mocks because
  the existing Real API smoke suite requires a live backend on port 8080.
