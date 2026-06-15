from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, Integer, JSON, Numeric, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class UserAccount(Base):
    __tablename__ = "user_account"

    id: Mapped[str] = mapped_column(String(128), primary_key=True)
    display_name: Mapped[str] = mapped_column(String(128))
    email: Mapped[str | None] = mapped_column(String(256))
    avatar_url: Mapped[str | None] = mapped_column(String(512))
    status: Mapped[str] = mapped_column(String(32), default="ACTIVE")
    merged_to_user_id: Mapped[str | None] = mapped_column(String(128))
    system_account: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class Namespace(Base):
    __tablename__ = "namespace"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    slug: Mapped[str] = mapped_column(String(64))
    display_name: Mapped[str] = mapped_column(String(128))
    type: Mapped[str] = mapped_column(String(32))
    description: Mapped[str | None] = mapped_column(Text)
    avatar_url: Mapped[str | None] = mapped_column(String(512))
    status: Mapped[str] = mapped_column(String(32), default="ACTIVE")
    created_by: Mapped[str | None] = mapped_column(String(128), ForeignKey("user_account.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class NamespaceMember(Base):
    __tablename__ = "namespace_member"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    namespace_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("namespace.id"))
    user_id: Mapped[str] = mapped_column(String(128), ForeignKey("user_account.id"))
    role: Mapped[str] = mapped_column(String(32))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class Skill(Base):
    __tablename__ = "skill"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    namespace_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("namespace.id"))
    slug: Mapped[str] = mapped_column(String(128))
    display_name: Mapped[str | None] = mapped_column(String(256))
    summary: Mapped[str | None] = mapped_column(Text)
    owner_id: Mapped[str] = mapped_column(String(128), ForeignKey("user_account.id"))
    source_skill_id: Mapped[int | None] = mapped_column(BigInteger)
    visibility: Mapped[str] = mapped_column(String(32), default="PUBLIC")
    status: Mapped[str] = mapped_column(String(32), default="ACTIVE")
    latest_version_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("skill_version.id"))
    download_count: Mapped[int] = mapped_column(BigInteger, default=0)
    star_count: Mapped[int] = mapped_column(Integer, default=0)
    rating_avg: Mapped[Decimal] = mapped_column(Numeric(3, 2), default=Decimal("0.00"))
    rating_count: Mapped[int] = mapped_column(Integer, default=0)
    created_by: Mapped[str | None] = mapped_column(String(128), ForeignKey("user_account.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_by: Mapped[str | None] = mapped_column(String(128), ForeignKey("user_account.id"))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    hidden: Mapped[bool] = mapped_column(Boolean, default=False)
    hidden_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    hidden_by: Mapped[str | None] = mapped_column(String(128), ForeignKey("user_account.id"))
    subscription_count: Mapped[int] = mapped_column(Integer, default=0)


class SkillVersion(Base):
    __tablename__ = "skill_version"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    skill_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("skill.id"))
    version: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(32), default="DRAFT")
    changelog: Mapped[str | None] = mapped_column(Text)
    parsed_metadata_json: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    manifest_json: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    file_count: Mapped[int] = mapped_column(Integer, default=0)
    total_size: Mapped[int] = mapped_column(BigInteger, default=0)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_by: Mapped[str | None] = mapped_column(String(128), ForeignKey("user_account.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    yanked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    yanked_by: Mapped[str | None] = mapped_column(String(128), ForeignKey("user_account.id"))
    yank_reason: Mapped[str | None] = mapped_column(Text)
    bundle_ready: Mapped[bool] = mapped_column(Boolean, default=False)
    download_ready: Mapped[bool] = mapped_column(Boolean, default=False)
    requested_visibility: Mapped[str | None] = mapped_column(String(20))


class ReviewTask(Base):
    __tablename__ = "review_task"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    skill_version_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("skill_version.id"))
    namespace_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("namespace.id"))
    status: Mapped[str] = mapped_column(String(32), default="PENDING")
    version: Mapped[int] = mapped_column(Integer, default=1)
    submitted_by: Mapped[str] = mapped_column(String(128), ForeignKey("user_account.id"))
    reviewed_by: Mapped[str | None] = mapped_column(String(128), ForeignKey("user_account.id"))
    review_comment: Mapped[str | None] = mapped_column(Text)
    submitted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class PromotionRequest(Base):
    __tablename__ = "promotion_request"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    source_skill_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("skill.id"))
    source_version_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("skill_version.id"))
    target_namespace_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("namespace.id"))
    target_skill_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("skill.id"))
    status: Mapped[str] = mapped_column(String(32), default="PENDING")
    version: Mapped[int] = mapped_column(Integer, default=1)
    submitted_by: Mapped[str] = mapped_column(String(128), ForeignKey("user_account.id"))
    reviewed_by: Mapped[str | None] = mapped_column(String(128), ForeignKey("user_account.id"))
    review_comment: Mapped[str | None] = mapped_column(Text)
    submitted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ApiToken(Base):
    __tablename__ = "api_token"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    subject_type: Mapped[str] = mapped_column(String(32), default="USER")
    subject_id: Mapped[str] = mapped_column(String(128))
    user_id: Mapped[str] = mapped_column(String(128), ForeignKey("user_account.id"))
    name: Mapped[str] = mapped_column(String(128))
    token_prefix: Mapped[str] = mapped_column(String(16))
    token_hash: Mapped[str] = mapped_column(String(64))
    scope_json: Mapped[dict[str, Any]] = mapped_column(JSON)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class AuditLog(Base):
    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    actor_user_id: Mapped[str | None] = mapped_column(String(128), ForeignKey("user_account.id"))
    action: Mapped[str] = mapped_column(String(64))
    target_type: Mapped[str | None] = mapped_column(String(64))
    target_id: Mapped[int | None] = mapped_column(BigInteger)
    request_id: Mapped[str | None] = mapped_column(String(64))
    client_ip: Mapped[str | None] = mapped_column(String(64))
    user_agent: Mapped[str | None] = mapped_column(String(512))
    detail_json: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
