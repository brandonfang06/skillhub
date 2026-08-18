from datetime import UTC, datetime
from typing import Any

import pytest

from app.audit.writer import write_audit_log


class RecordingConnection:
    def __init__(self) -> None:
        self.params: dict[str, Any] | None = None

    async def execute(self, _statement: object, params: dict[str, Any]) -> None:
        self.params = params


@pytest.mark.anyio
async def test_audit_writer_accepts_exactly_one_discriminated_actor() -> None:
    connection = RecordingConnection()
    await write_audit_log(
        connection,
        actor_service_principal_id="svc_importer",
        action="SOURCE_IMPORT",
        target_type="SKILL_VERSION",
        target_id=1,
        request_id=None,
        client_ip=None,
        user_agent=None,
        detail={},
        created_at=datetime.now(UTC),
    )
    assert connection.params is not None
    assert connection.params["actor_user_id"] is None
    assert connection.params["actor_service_principal_id"] == "svc_importer"

    for actors in ({}, {"actor_user_id": "user", "actor_service_principal_id": "svc"}):
        with pytest.raises(ValueError, match="exactly one audit actor"):
            await write_audit_log(
                connection,
                **actors,
                action="INVALID",
                target_type="TEST",
                target_id=1,
                request_id=None,
                client_ip=None,
                user_agent=None,
                detail={},
                created_at=datetime.now(UTC),
            )
