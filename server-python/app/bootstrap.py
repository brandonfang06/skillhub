from __future__ import annotations

import os
from collections.abc import Callable, Mapping
from dataclasses import dataclass

from sqlalchemy import text

from app.auth.password_reset import bcrypt_value


TRUE_VALUES = {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class BootstrapAdminConfig:
    enabled: bool
    user_id: str = "docker-admin"
    username: str = "admin"
    password: str = "ChangeMe!2026"
    display_name: str = "Admin"
    email: str = "admin@skillhub.local"


def bootstrap_admin_config(environ: Mapping[str, str] | None = None) -> BootstrapAdminConfig:
    env = os.environ if environ is None else environ
    return BootstrapAdminConfig(
        enabled=str(env.get("BOOTSTRAP_ADMIN_ENABLED", "false")).strip().lower() in TRUE_VALUES,
        user_id=env.get("BOOTSTRAP_ADMIN_USER_ID", "docker-admin"),
        username=env.get("BOOTSTRAP_ADMIN_USERNAME", "admin"),
        password=env.get("BOOTSTRAP_ADMIN_PASSWORD", "ChangeMe!2026"),
        display_name=env.get("BOOTSTRAP_ADMIN_DISPLAY_NAME", "Admin"),
        email=env.get("BOOTSTRAP_ADMIN_EMAIL", "admin@skillhub.local"),
    )


async def initialize_bootstrap_admin(
    engine: object,
    *,
    environ: Mapping[str, str] | None = None,
    password_hasher: Callable[[str], str] = bcrypt_value,
) -> None:
    config = bootstrap_admin_config(environ)
    if not config.enabled:
        return

    async with engine.begin() as connection:
        existing_credential = (
            await connection.execute(
                text(
                    """
                    SELECT user_id, username, password_hash
                    FROM local_credential
                    WHERE LOWER(username) = LOWER(:username)
                    LIMIT 1
                    """
                ),
                {"username": config.username},
            )
        ).mappings().one_or_none()
        if existing_credential is not None and str(existing_credential["user_id"]) != config.user_id:
            return

        admin = (
            await connection.execute(
                text(
                    """
                    SELECT id, display_name, email, avatar_url, status
                    FROM user_account
                    WHERE id = :user_id
                    LIMIT 1
                    """
                ),
                {"user_id": config.user_id},
            )
        ).mappings().one_or_none()
        if admin is None:
            await connection.execute(
                text(
                    """
                    INSERT INTO user_account (id, display_name, email, avatar_url, status)
                    VALUES (:id, :display_name, :email, :avatar_url, :status)
                    """
                ),
                {
                    "id": config.user_id,
                    "display_name": config.display_name,
                    "email": config.email,
                    "avatar_url": None,
                    "status": "ACTIVE",
                },
            )
        elif existing_credential is None:
            await connection.execute(
                text(
                    """
                    UPDATE user_account
                    SET display_name = :display_name,
                        email = :email
                    WHERE id = :user_id
                    """
                ),
                {"user_id": config.user_id, "display_name": config.display_name, "email": config.email},
            )

        if existing_credential is None:
            await connection.execute(
                text(
                    """
                    INSERT INTO local_credential (user_id, username, password_hash)
                    VALUES (:user_id, :username, :password_hash)
                    """
                ),
                {
                    "user_id": config.user_id,
                    "username": config.username,
                    "password_hash": password_hasher(config.password),
                },
            )

        role = (
            await connection.execute(
                text(
                    """
                    SELECT id, code
                    FROM role
                    WHERE code = :code
                    LIMIT 1
                    """
                ),
                {"code": "SUPER_ADMIN"},
            )
        ).mappings().one_or_none()
        if role is None:
            raise RuntimeError("Missing built-in role: SUPER_ADMIN")

        role_id = role["id"]
        existing_role_binding = (
            await connection.execute(
                text(
                    """
                    SELECT id
                    FROM user_role_binding
                    WHERE user_id = :user_id
                      AND role_id = :role_id
                    LIMIT 1
                    """
                ),
                {"user_id": config.user_id, "role_id": role_id},
            )
        ).mappings().one_or_none()
        if existing_role_binding is None:
            await connection.execute(
                text(
                    """
                    INSERT INTO user_role_binding (user_id, role_id)
                    VALUES (:user_id, :role_id)
                    """
                ),
                {"user_id": config.user_id, "role_id": role_id},
            )

        global_namespace = (
            await connection.execute(
                text(
                    """
                    SELECT id, slug
                    FROM namespace
                    WHERE slug = 'global'
                    LIMIT 1
                    """
                )
            )
        ).mappings().one_or_none()
        if global_namespace is None:
            raise RuntimeError("Missing built-in global namespace")

        namespace_id = global_namespace["id"]
        existing_membership = (
            await connection.execute(
                text(
                    """
                    SELECT id
                    FROM namespace_member
                    WHERE namespace_id = :namespace_id
                      AND user_id = :user_id
                    LIMIT 1
                    """
                ),
                {"namespace_id": namespace_id, "user_id": config.user_id},
            )
        ).mappings().one_or_none()
        if existing_membership is None:
            await connection.execute(
                text(
                    """
                    INSERT INTO namespace_member (namespace_id, user_id, role)
                    VALUES (:namespace_id, :user_id, :role)
                    """
                ),
                {"namespace_id": namespace_id, "user_id": config.user_id, "role": "OWNER"},
            )
