# Review Requested Visibility Design

## Goal

Show namespace reviewers the visibility requested for the skill version under review. The value must represent the publish submission intent, not the skill's mutable current visibility.

## Scope

- Add the version-bound `requestedVisibility` field to the review detail response.
- Add `approvalVisibility`, calculated with the existing approval-time audit rule, to prevent the review UI from implying an outdated outcome.
- Display the field in the existing review metadata card for every user authorized to view that review.
- Support `PUBLIC` and `NAMESPACE_ONLY`, the two visibility targets that enter review. Also render `PRIVATE` when a post-submission visibility update makes it the effective approval value.
- Display a neutral "Not recorded" value for legacy review data where the requested visibility is null.
- Keep the review page read-only for visibility. Approval, rejection, visibility mutation, and lifecycle behavior remain unchanged.

Review list rows, publish controls, skill detail visibility controls, and archived review persistence changes are out of scope.

## Data Contract

The review detail query will select `skill_version.requested_visibility` for the review-bound version and expose it as the optional `requestedVisibility` field on `ReviewTaskResponse`.

The value is sourced from `skill_version`, because that row records the target selected when the version entered review. The UI must not fall back to `skill.visibility`: that value can change after submission and can therefore misrepresent what the reviewer is approving.

`approvalVisibility` follows the same rule as approval execution: use `skill.visibility` only when an `UPDATE_SKILL_VISIBILITY` audit entry exists after the review submission time; otherwise use `skill_version.requested_visibility`. This calculation is detail-only and does not change the review list contract.

Archived attempts may not have a version row or a visibility snapshot in `review_attempt_archive`. Their response keeps `requestedVisibility` null and the UI renders the neutral fallback.
Their `approvalVisibility` is also null because an archived attempt can no longer be approved.

## User Interface

The review detail metadata grid will include a "Requested visibility" label and a compact badge:

- `PUBLIC`: "Public"
- `NAMESPACE_ONLY`: "Namespace Only" for non-global namespaces and the existing organization-oriented label for the global namespace
- Missing or unknown values: "Not recorded"

The field appears on both platform and namespace review routes because they share `ReviewDetailScreen`. It is informational only and introduces no edit control.

When `approvalVisibility` differs from `requestedVisibility`, the metadata card also shows the approval value with a warning that approval will use the newer visibility. The extra field remains hidden when both values match.

## Compatibility And Errors

`requestedVisibility` is optional in the API contract so older or archived review records remain readable. Unknown values fail closed to the neutral fallback rather than being presented as a known visibility.

No database migration is required. The existing `skill_version.requested_visibility` column remains the source of truth.

## Verification

- Backend query test proves detail responses return `requestedVisibility` from the review-bound version.
- Authorization tests prove a namespace owner who did not submit the skill can read the detail.
- Backend tests prove the approval visibility follows the existing post-submission audit rule and review list rows remain unchanged.
- OpenAPI contract test proves the optional field is exported, followed by regeneration of the frontend review schema and types.
- Frontend rendering tests cover `PUBLIC`, `NAMESPACE_ONLY`, and missing values on the namespace review route.
- A real PostgreSQL scenario creates a review whose current skill visibility differs from its requested visibility and verifies that the API returns the requested value.
- Logged-in browser verification confirms the requested visibility is visible on desktop and mobile review detail layouts without changing review actions.

## Non-Goals

- Changing visibility from the review page.
- Changing approval-time visibility resolution.
- Showing mutable current visibility when it is not the value approval will use.
- Backfilling requested visibility for archived or legacy reviews.
