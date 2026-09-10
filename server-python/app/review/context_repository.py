from __future__ import annotations

from typing import Any

from sqlalchemy import text

from app.auth.policy import NAMESPACE_MANAGER_ROLES, namespace_role_allows
from app.review.approval import PLATFORM_REVIEW_ROLES
from app.review.query import ReviewQueryError


def _waiting_reason(row: Any) -> str:
    if row['version_status'] in {'DRAFT', 'UPLOADED'}:
        return 'NOT_SUBMITTED'
    if row['version_status'] in {'SCANNING', 'SCAN_FAILED'}:
        return str(row['version_status'])
    if row['task_status'] in {'APPROVED', 'REJECTED'}:
        return str(row['task_status'])
    if row['task_status'] != 'PENDING' or row['version_status'] != 'PENDING_REVIEW':
        return 'NOT_SUBMITTED'
    if row['namespace_status'] != 'ACTIVE':
        return 'NAMESPACE_UNAVAILABLE'
    if row['scan_status'] == 'PENDING':
        return 'SCANNING'
    if row['scan_status'] == 'FAILED':
        return 'SCAN_FAILED'
    if row['scan_status'] not in {None, 'COMPLETE'}:
        return 'SCAN_PARTIAL'
    return 'HUMAN_REVIEW'


async def read_version_review_context(
    connection: Any, *, skill_id: int, version: str, user_id: str, page: int = 0, size: int = 20,
) -> dict[str, Any]:
    row = (await connection.execute(text('''
        SELECT s.owner_id, n.id AS namespace_id, n.slug AS namespace_slug,
               n.type AS namespace_type, n.status AS namespace_status,
               sv.status AS version_status, sv.created_by AS version_created_by,
               rt.id AS task_id, rt.status AS task_status, rt.submitted_by,
               rt.submitted_at, rt.reviewed_at, rt.review_comment,
               reviewer.display_name AS reviewed_by_name,
               viewer.status AS viewer_status,
               (SELECT nm.role FROM namespace_member nm
                WHERE nm.namespace_id=n.id AND nm.user_id=:user_id) AS viewer_namespace_role,
               scan.scan_status
        FROM skill s JOIN namespace n ON n.id=s.namespace_id
        JOIN skill_version sv ON sv.skill_id=s.id AND sv.version=:version
        LEFT JOIN LATERAL (
            SELECT * FROM review_task WHERE skill_version_id=sv.id
            ORDER BY submitted_at DESC, id DESC LIMIT 1
        ) rt ON TRUE
        LEFT JOIN user_account reviewer ON reviewer.id=rt.reviewed_by
        LEFT JOIN user_account viewer ON viewer.id=:user_id
        LEFT JOIN LATERAL (
            SELECT COALESCE(execution.scan_status,
                   CASE WHEN sa.scanned_at IS NOT NULL THEN 'COMPLETE' ELSE 'PENDING' END) AS scan_status
            FROM security_audit sa LEFT JOIN local_security_scan_execution execution
              ON execution.security_audit_id=sa.id
            WHERE sa.skill_version_id=sv.id AND sa.scanner_type='SKILL_SCANNER' AND sa.deleted_at IS NULL
            ORDER BY sa.created_at DESC, sa.id DESC LIMIT 1
        ) scan ON TRUE
        WHERE s.id=:skill_id
    '''), {'skill_id': skill_id, 'version': version, 'user_id': user_id})).mappings().one_or_none()
    if row is None:
        raise ReviewQueryError('error.skill.version.notFound', status_code=404)
    roles = set((await connection.execute(text('''
        SELECT r.code FROM user_role_binding urb JOIN role r ON r.id=urb.role_id
        WHERE urb.user_id=:user_id
    '''), {'user_id': user_id})).scalars().all())
    is_manager = row['namespace_type'] != 'GLOBAL' and namespace_role_allows(row['viewer_namespace_role'], NAMESPACE_MANAGER_ROLES)
    if row['viewer_status'] != 'ACTIVE' or not (
        user_id == row['owner_id'] or user_id == row['submitted_by']
        or (row['task_id'] is None and user_id == row['version_created_by'])
        or is_manager or bool(roles & PLATFORM_REVIEW_ROLES)
    ):
        raise ReviewQueryError('review.no_permission', status_code=403)
    reason = _waiting_reason(row)
    reviewers: list[dict[str, Any]] = []
    total = 0
    if row['namespace_type'] != 'GLOBAL' and reason not in {'APPROVED', 'REJECTED', 'NOT_SUBMITTED'}:
        params = {'namespace_id': row['namespace_id'], 'limit': size, 'offset': page * size}
        total = int((await connection.execute(text('''
            SELECT COUNT(*) FROM namespace_member nm JOIN user_account ua ON ua.id=nm.user_id
            WHERE nm.namespace_id=:namespace_id AND nm.role='ADMIN' AND ua.status='ACTIVE'
        '''), params)).scalar_one())
        reviewers = [dict(person) for person in (await connection.execute(text('''
            SELECT ua.id AS "userId", ua.display_name AS "displayName",
                   (SELECT ib.login_name FROM identity_binding ib
                    WHERE ib.user_id=ua.id AND ib.provider_code='keycloak'
                    ORDER BY ib.login_name LIMIT 1) AS "loginName"
            FROM namespace_member nm JOIN user_account ua ON ua.id=nm.user_id
            WHERE nm.namespace_id=:namespace_id AND nm.role='ADMIN' AND ua.status='ACTIVE'
            ORDER BY lower(ua.display_name), ua.id LIMIT :limit OFFSET :offset
        '''), params)).mappings().all()]
    return {
        'skillId': skill_id, 'version': version, 'namespace': row['namespace_slug'],
        'namespaceType': row['namespace_type'], 'versionStatus': row['version_status'],
        'reviewTaskId': row['task_id'], 'reviewStatus': row['task_status'], 'waitingReason': reason,
        'submittedAt': row['submitted_at'], 'reviewedAt': row['reviewed_at'],
        'reviewedByName': row['reviewed_by_name'], 'reviewComment': row['review_comment'],
        'reviewers': reviewers, 'total': total, 'page': page, 'size': size,
    }
