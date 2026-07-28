# UI Runtime Resilience Design
## Context

Two production-facing frontend defects need a narrow repair:

1. The skill visibility select and save button can overflow the lifecycle sidebar.
2. An already-open SkillHub tab can fail the first navigation to a lazy route after a
   deployment because its old hashed chunk no longer exists. Refreshing succeeds because
   the browser then loads the current entry document and chunk manifest.

These defects are independent at runtime, but they share one delivery requirement: viewport
and deployed-bundle behavior must be verified in addition to component tests.

## Root Causes

### Visibility controls

The skill detail sidebar is fixed at `lg:w-80`. After card and panel padding, the visibility
controls have about 256 pixels of usable width. The control row nevertheless switches to
`sm:flex-row` based on the page viewport, not the sidebar width. The select's intrinsic
content width and the button's non-wrapping label can therefore exceed the panel.

### Lazy route chunks

Notification items use TanStack Router links and review detail is loaded through
`React.lazy()`. A deployment replaces the web image, including all `/assets` files. An old
tab still references the previous route chunk hash, so its client-side navigation requests a
file that no longer exists. The current Nginx configuration correctly caches hashed assets as
immutable, but the application has no recovery path for Vite preload failures.

## Design

### Overflow-safe visibility layout

Render the visibility select and save button as a single-column grid in the fixed-width
sidebar. Both controls remain constrained to the panel width. The button uses the full width
and allows its localized label to wrap rather than increasing the grid's intrinsic width.

This deliberately favors predictable layout over preserving a dense horizontal arrangement.
The visibility behavior, authorization, mutation, and translation text do not change.

### One-time stale chunk recovery

Install a `vite:preloadError` listener from `bootstrap.ts` before `main.tsx` is dynamically
imported. The listener:

- derives a stable fingerprint from the preload error payload;
- stores the last fingerprint and attempt timestamp in `sessionStorage`;
- prevents the first matching Vite preload error from reaching the router error boundary;
- reloads the current URL once so the browser obtains the current entry document;
- does not reload again for the same fingerprint within a short guard window.

If storage is unavailable, or the same preload failure immediately repeats, the error remains
visible instead of risking a reload loop. This recovery applies to every lazy route rather than
special-casing the notification bell.

### Cache policy

Keep fingerprinted `/assets` responses immutable for one year. Add an explicit
`Cache-Control: no-cache, must-revalidate` policy to the SPA document and fallback route so a
reload revalidates the current entry document. Keep `runtime-config.js` as `no-store`.

## Verification

- Unit-test first-attempt reload, repeated-error suppression, and unavailable storage.
- Assert the Nginx policy keeps assets immutable while revalidating SPA responses.
- Run focused skill detail and bootstrap recovery tests, then the complete frontend suite,
  typecheck, lint, and production build.
- Run authenticated Playwright coverage at desktop and mobile widths and assert the visibility
  select and save button remain within their panel.
- Simulate a Vite preload failure in a browser and confirm only one reload is requested for the
  same failed chunk fingerprint.

## Side Effects

- A stale tab loses unsaved in-memory UI state when the automatic reload occurs. The failed
  navigation cannot complete without a new bundle, so one guarded reload is preferable to a
  broken route.
- A transient preload network failure also triggers one reload. Repeated failure falls back to
  the existing error UI instead of looping.
- SPA document responses revalidate more often, while large fingerprinted assets retain their
  long immutable cache lifetime.
