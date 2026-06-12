# Lifecycle/Governance Deferred Audit Result

Date: 2026-06-12

Milestone: 118 - Deferred Lifecycle/Governance Semantic Audit

## Summary

No broad lifecycle/governance deferred bucket remains. The current Python route table and
`docs/backend-python-migration/route-registry.md` are now checked by
`server-python/tests/test_final_lifecycle_governance_audit.py` for representative lifecycle and
governance routes that previously carried broad deferred wording.

The audit found stale current-registry notes rather than missing Python route ownership. Those notes
were updated to describe the current Python-owned review, promotion, namespace lifecycle, and SSE
fanout state.

## Publish Side Effects

Python-owned publish and post-publish side effects are covered by the existing publish, lifecycle,
review, promotion, report, notification, and admin governance tests. Review approval publishes the
reviewed version, updates latest-version visibility metadata, and writes the migrated audit record.
Promotion approval materializes the target skill/version/file records and emits migrated governance
notifications.

Remaining product-scope follow-up: none for broad Java ownership. Fine-grained route-policy
enumeration remains tracked separately by milestone 116.

## Review And Promotion Transitions

Review submit, list, detail, skill-detail, file, download, approve, reject, and withdraw routes are
Python-owned for both `/api/v1` and `/api/web` surfaces. Promotion submit, list, pending list,
detail, approve, and reject routes are Python-owned for both surfaces.

The audit test locks these routes against the FastAPI app route table and the route registry using
route-shape matching, so registry placeholder names such as `{id}` do not drift from FastAPI
parameter names such as `{review_task_id}`.

## Admin Governance Actions

Admin hide/unhide, version yank, skill report resolve/dismiss, and profile review approve/reject
routes are Python-owned. Existing route tests cover platform-role checks, bearer-token rejection on
unsupported admin routes, pending-only transitions, audit logs, and Java-compatible response
behavior.

Remaining product-scope follow-up: none for broad Java ownership.

## Skill Tag Label Report Social Delete Flows

Skill tags, skill labels, report submit, star, subscription, rating, archive/unarchive, hard delete,
CLI delete, version delete, submit-review, confirm-publish, withdraw-review, and rerelease flows are
Python-owned in the current registry and covered by targeted Python route tests plus hybrid gates
from their migration slices.

Remaining product-scope follow-up: no broad lifecycle/governance bucket. Python schema ownership
and default Java runtime deprecation remain separate milestones 119 and 120.

## Governance Summary Inbox Activity Notifications

Governance summary, inbox, activity, legacy notification reads, notification read-state mutations,
preferences, and SSE connection/fanout are Python-owned. SSE fanout is complete for the single
Python backend runtime path and report-submit publishes committed `REPORT_SUBMITTED` notifications
to connected users.

Remaining product-scope follow-up: a Redis-backed cross-replica SSE fanout bridge is an operational
scaling enhancement if pre-launch deployment uses more than one Python backend replica. It is not a
Java dependency and does not block the Java-to-Python cutover.

## Verification

Completed verification:

- `uv run pytest tests/test_final_lifecycle_governance_audit.py tests/test_route_registry.py -q`
- `uv run pytest tests/test_final_lifecycle_governance_audit.py tests/test_route_registry.py tests/test_governance_workbench.py tests/test_review_list.py tests/test_review_detail.py tests/test_review_skill_detail.py tests/test_review_file_content.py tests/test_review_download.py tests/test_review_approve.py tests/test_review_reject_withdraw.py tests/test_review_submit.py tests/test_promotion_read.py tests/test_promotion_write.py tests/test_admin_skill_governance.py tests/test_admin_review_reports.py tests/test_admin_review_report_mutations.py tests/test_skill_report_submit.py tests/test_notification_sse_fanout.py tests/test_namespace_profile_lifecycle.py tests/test_namespace_member_mutation.py tests/test_skill_lifecycle_archive.py tests/test_skill_lifecycle_delete_version.py tests/test_skill_lifecycle_withdraw_review.py tests/test_skill_lifecycle_confirm_publish.py tests/test_skill_lifecycle_submit_review.py tests/test_skill_lifecycle_rerelease.py tests/test_skill_tags.py tests/test_labels.py tests/test_skill_label_mutations.py tests/test_skill_star.py tests/test_skill_subscription.py tests/test_skill_rating.py -q`
- `.\scripts\dev-hybrid.ps1 -Action verify-governance-workbench-smoke`
- `.\scripts\dev-hybrid.ps1 -Action status`
