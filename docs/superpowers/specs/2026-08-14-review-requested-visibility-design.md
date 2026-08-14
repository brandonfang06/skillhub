# Review Requested Visibility Design

## Goal

Show namespace reviewers the visibility requested for the skill version under review. The value must represent the publish submission intent, not the skill's mutable current visibility.

## Scope

- Add the version-bound `requestedVisibility` field to the review detail response.
- Display the field in the existing review metadata card for every user authorized to view that review.
- Support `PUBLIC` and `NAMESPACE_ONLY`, the two visibility targets that enter review.
- Display a neutral "Not recorded" value for legacy review data where the requested visibility is null.
- Keep the review page read-only for visibility. Approval, rejection, visibility mutation, and lifecycle behavior remain unchanged.

Review list rows, publish controls, skill detail visibility controls, and archived review schema changes are out of scope.

## Data Contract

The review detail query will select `skill_version.requested_visibility` for the review-bound version and expose it as the optional `requestedVisibility` field on `ReviewTaskResponse`.

The value is sourced from `skill_version`, because that row records the target selected when the version entered review. The UI must not fall back to `skill.visibility`: that value can change after submission and can therefore misrepresent what the reviewer is approving.

Archived attempts may not have a version row or a visibility snapshot in `review_attempt_archive`. Their response keeps `requestedVisibility` null and the UI renders the neutral fallback.

## User Interface

The review detail metadata grid will include a "Requested visibility" label and a compact badge:

- `PUBLIC`: "Public"
- `NAMESPACE_ONLY`: "Namespace Only" for non-global namespaces and the existing organization-oriented label for the global namespace
- Missing or unknown values: "Not recorded"

The field appears on both platform and namespace review routes because they share `ReviewDetailScreen`. It is informational only and introduces no edit control.

## Compatibility And Errors

`requestedVisibility` is optional in the API contract so older or archived review records remain readable. Unknown values fail closed to the neutral fallback rather than being presented as a known visibility.

No database migration is required. The existing `skill_version.requested_visibility` column remains the source of truth.

## Verification

- Backend query test proves detail responses return `requestedVisibility` from the review-bound version.
- Authorization tests retain namespace owner/admin access behavior.
- OpenAPI contract test proves the optional field is exported, followed by regeneration of the frontend review schema and types.
- Frontend rendering tests cover `PUBLIC`, `NAMESPACE_ONLY`, and missing values on the namespace review route.
- A real PostgreSQL scenario creates a review whose current skill visibility differs from its requested visibility and verifies that the API returns the requested value.
- Logged-in browser verification confirms the requested visibility is visible on desktop and mobile review detail layouts without changing review actions.

## Non-Goals

- Changing visibility from the review page.
- Changing approval-time visibility resolution.
- Showing current and requested visibility side by side.
- Backfilling requested visibility for archived or legacy reviews.
