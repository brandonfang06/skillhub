from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import text

from app.admin.search import upsert_skill_search_document
from app.db.unit_of_work import transaction_connection
from app.notifications.publisher import NotificationFanout, publish_notification_rows
from app.social.subscription_access import (
    SubscriptionAccessFacts,
    can_access_subscription_metadata,
)

logger = logging.getLogger("uvicorn.error")


@dataclass(frozen=True)
class PublicationOutcomeInput:
    skill_id: int
    version_id: int
    publisher_id: str
    created_at: datetime


async def _read_publication_context(
    connection: Any,
    outcome: PublicationOutcomeInput,
) -> dict[str, Any]:
    row = (
        (
            await connection.execute(
                text(
                    """
                SELECT s.id AS skill_id,
                       s.namespace_id,
                       s.owner_id,
                       s.slug,
                       s.display_name,
                       s.visibility,
                       s.hidden,
                       s.latest_version_id,
                       sv.id AS published_version_id,
                       n.slug AS namespace_slug,
                       n.status AS namespace_status,
                       sv.version
                FROM skill s
                JOIN namespace n ON n.id = s.namespace_id
                JOIN skill_version sv ON sv.skill_id = s.id
                WHERE s.id = :skill_id
                  AND sv.id = :version_id
                  AND sv.status = 'PUBLISHED'
                FOR UPDATE OF s
                """
                ),
                {"skill_id": outcome.skill_id, "version_id": outcome.version_id},
            )
        )
        .mappings()
        .one_or_none()
    )
    if row is None:
        raise RuntimeError(
            "Published skill version is unavailable for publication outcomes"
        )
    return dict(row)


async def _in_app_publish_notifications_enabled(connection: Any, owner_id: str) -> bool:
    row = (
        (
            await connection.execute(
                text(
                    """
                SELECT COALESCE(np.enabled, TRUE) AS enabled
                FROM (SELECT :owner_id AS user_id) target
                LEFT JOIN notification_preference np
                  ON np.user_id = target.user_id
                 AND np.category = 'PUBLISH'
                 AND np.channel = 'IN_APP'
                """
                ),
                {"owner_id": owner_id},
            )
        )
        .mappings()
        .one_or_none()
    )
    return True if row is None else bool(row["enabled"])


async def _read_subscribers(
    connection: Any,
    *,
    context: dict[str, Any],
    publisher_id: str,
) -> list[str]:
    rows = (
        (
            await connection.execute(
                text(
                    """
                SELECT DISTINCT ss.user_id,
                                account.status AS account_status,
                                member.role AS namespace_role
                FROM skill_subscription ss
                JOIN user_account account ON account.id = ss.user_id
                LEFT JOIN namespace_member member
                  ON member.namespace_id = :namespace_id
                 AND member.user_id = ss.user_id
                LEFT JOIN notification_preference np
                  ON np.user_id = ss.user_id
                 AND np.category = 'PUBLISH'
                 AND np.channel = 'IN_APP'
                WHERE ss.skill_id = :skill_id
                  AND ss.user_id <> :publisher_id
                  AND COALESCE(np.enabled, TRUE) = TRUE
                ORDER BY ss.user_id
                """
                ),
                {
                    "skill_id": int(context["skill_id"]),
                    "namespace_id": int(context["namespace_id"]),
                    "publisher_id": publisher_id,
                },
            )
        )
        .mappings()
        .all()
    )
    subscriber_ids: list[str] = []
    for row in rows:
        user_id = str(row["user_id"])
        facts = SubscriptionAccessFacts.from_row(
            {
                **context,
                "account_status": row["account_status"],
                "namespace_role": row["namespace_role"],
            }
        )
        if can_access_subscription_metadata(facts, user_id=user_id):
            subscriber_ids.append(user_id)
    return subscriber_ids


async def _insert_publication_notification(
    connection: Any,
    *,
    recipient_id: str,
    event_type: str,
    title: str,
    body_json: str,
    skill_id: int,
    version_id: int,
    created_at: datetime,
) -> list[dict[str, Any]]:
    rows = (
        (
            await connection.execute(
                text(
                    """
                INSERT INTO notification (
                    recipient_id, category, event_type, title, body_json,
                    entity_type, entity_id, status, created_at
                )
                SELECT CAST(:recipient_id AS VARCHAR(128)), 'PUBLISH',
                       CAST(:event_type AS VARCHAR(64)), CAST(:title AS VARCHAR(200)),
                       CAST(:body_json AS TEXT), 'SKILL', CAST(:entity_id AS BIGINT),
                       'UNREAD', CAST(:created_at AS TIMESTAMPTZ)
                WHERE NOT EXISTS (
                    SELECT 1
                    FROM notification
                    WHERE recipient_id = CAST(:recipient_id AS VARCHAR(128))
                      AND category = 'PUBLISH'
                      AND event_type = CAST(:event_type AS VARCHAR(64))
                      AND entity_type = 'SKILL'
                      AND entity_id = CAST(:entity_id AS BIGINT)
                      AND CAST(body_json AS JSONB) ->> 'versionId' = CAST(:version_id_text AS TEXT)
                )
                RETURNING id, recipient_id, category, event_type, title, body_json,
                          entity_type, entity_id, created_at
                """
                ),
                {
                    "recipient_id": recipient_id,
                    "event_type": event_type,
                    "title": title,
                    "body_json": body_json,
                    "entity_id": skill_id,
                    "version_id_text": str(version_id),
                    "created_at": created_at,
                },
            )
        )
        .mappings()
        .all()
    )
    return [dict(row) for row in rows]


async def apply_publication_outcomes(
    engine: Any,
    outcome: PublicationOutcomeInput,
    notification_fanout: NotificationFanout | None,
) -> None:
    """Persist authoritative outcomes, then attempt at-most-once in-process SSE fanout."""
    async with transaction_connection(engine) as connection:
        notification_rows = await write_publication_outcomes(connection, outcome)

    await publish_publication_notifications(
        notification_fanout,
        notification_rows,
        outcome,
    )


async def write_publication_outcomes(
    connection: Any,
    outcome: PublicationOutcomeInput,
) -> list[dict[str, Any]]:
    context = await _read_publication_context(connection, outcome)
    await upsert_skill_search_document(connection, outcome.skill_id)

    notification_rows: list[dict[str, Any]] = []
    display_name = str(context.get("display_name") or context["slug"])
    body_json = json.dumps(
        {
            "skillId": outcome.skill_id,
            "versionId": outcome.version_id,
            "namespace": str(context["namespace_slug"]),
            "slug": str(context["slug"]),
            "skillName": display_name,
            "version": str(context["version"]),
        },
        separators=(",", ":"),
    )
    owner_id = str(context["owner_id"])
    if (
        owner_id == outcome.publisher_id
        and await _in_app_publish_notifications_enabled(
            connection,
            owner_id,
        )
    ):
        notification_rows.extend(
            await _insert_publication_notification(
                connection,
                recipient_id=owner_id,
                event_type="SKILL_PUBLISHED",
                title=f"Skill published: {display_name}",
                body_json=body_json,
                skill_id=outcome.skill_id,
                version_id=outcome.version_id,
                created_at=outcome.created_at,
            )
        )

    for subscriber_id in await _read_subscribers(
        connection,
        context=context,
        publisher_id=outcome.publisher_id,
    ):
        notification_rows.extend(
            await _insert_publication_notification(
                connection,
                recipient_id=subscriber_id,
                event_type="SUBSCRIPTION_NEW_VERSION",
                title=f"Skill updated: {display_name}",
                body_json=body_json,
                skill_id=outcome.skill_id,
                version_id=outcome.version_id,
                created_at=outcome.created_at,
            )
        )

    return notification_rows


async def publish_publication_notifications(
    notification_fanout: NotificationFanout | None,
    notification_rows: list[dict[str, Any]],
    outcome: PublicationOutcomeInput,
) -> None:

    try:
        await publish_notification_rows(notification_fanout, notification_rows)
    except Exception:
        logger.exception(
            "Publication SSE fanout failed after durable commit; "
            "durable publication notifications remain authoritative "
            "skill_id=%s version_id=%s notification_count=%s",
            outcome.skill_id,
            outcome.version_id,
            len(notification_rows),
        )
