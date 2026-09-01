from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class SubscriptionAccessFacts:
    owner_id: str
    visibility: str
    hidden: bool
    latest_version_id: int | None
    published_version_id: int | None
    namespace_status: str
    account_status: str | None
    namespace_role: str | None

    @classmethod
    def from_row(cls, row: dict[str, Any]) -> SubscriptionAccessFacts:
        latest_version_id = row.get("latest_version_id")
        published_version_id = row.get("published_version_id")
        return cls(
            owner_id=str(row["owner_id"]),
            visibility=str(row["visibility"]),
            hidden=bool(row["hidden"]),
            latest_version_id=(
                int(latest_version_id) if latest_version_id is not None else None
            ),
            published_version_id=(
                int(published_version_id)
                if published_version_id is not None
                else None
            ),
            namespace_status=str(row["namespace_status"]),
            account_status=(
                str(row["account_status"])
                if row.get("account_status") is not None
                else None
            ),
            namespace_role=(
                str(row["namespace_role"])
                if row.get("namespace_role") is not None
                else None
            ),
        )


def can_access_subscription_metadata(
    facts: SubscriptionAccessFacts,
    *,
    user_id: str,
) -> bool:
    if facts.account_status != "ACTIVE":
        return False

    owner = facts.owner_id == user_id
    manager = facts.namespace_role in {"OWNER", "ADMIN"}
    member = facts.namespace_role in {"OWNER", "ADMIN", "MEMBER"}
    if facts.namespace_status == "ARCHIVED" and not (owner or manager):
        return False
    if facts.hidden:
        return owner or manager
    if facts.visibility == "PRIVATE":
        return facts.latest_version_id is not None and (owner or manager)
    if facts.published_version_id is None:
        return owner
    if facts.visibility == "PUBLIC":
        return True
    if facts.visibility == "NAMESPACE_ONLY":
        return member
    return False


__all__ = [
    "SubscriptionAccessFacts",
    "can_access_subscription_metadata",
]
