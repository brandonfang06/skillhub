from decimal import Decimal

from app.api.skills import build_skill_detail_response


def test_build_skill_detail_response_maps_java_fields() -> None:
    row = {
        "id": 31,
        "slug": "demo-skill",
        "display_name": "Demo Skill",
        "owner_id": "owner-1",
        "owner_display_name": "Owner One",
        "summary": "Demo summary",
        "visibility": "PUBLIC",
        "status": "ACTIVE",
        "download_count": 7,
        "star_count": 3,
        "subscription_count": 2,
        "rating_avg": Decimal("4.50"),
        "rating_count": 4,
        "hidden": False,
        "namespace": "global",
        "published_version_id": 41,
        "published_version": "1.2.0",
        "published_version_status": "PUBLISHED",
        "resolution_mode": "PUBLISHED",
    }
    labels = [
        {"slug": "featured", "type": "RECOMMENDED", "displayName": "Featured"},
    ]

    assert build_skill_detail_response(row, labels) == {
        "id": 31,
        "slug": "demo-skill",
        "displayName": "Demo Skill",
        "ownerId": "owner-1",
        "ownerDisplayName": "Owner One",
        "summary": "Demo summary",
        "visibility": "PUBLIC",
        "status": "ACTIVE",
        "downloadCount": 7,
        "starCount": 3,
        "subscriptionCount": 2,
        "ratingAvg": 4.5,
        "ratingCount": 4,
        "hidden": False,
        "namespace": "global",
        "labels": labels,
        "canManageLifecycle": False,
        "canSubmitPromotion": False,
        "canInteract": True,
        "canReport": True,
        "headlineVersion": {"id": 41, "version": "1.2.0", "status": "PUBLISHED"},
        "publishedVersion": {"id": 41, "version": "1.2.0", "status": "PUBLISHED"},
        "ownerPreviewVersion": None,
        "ownerPreviewReviewComment": None,
        "resolutionMode": "PUBLISHED",
    }


def test_build_skill_detail_response_handles_no_published_projection() -> None:
    row = {
        "id": 32,
        "slug": "draft-only",
        "display_name": "Draft Only",
        "owner_id": "owner-1",
        "owner_display_name": None,
        "summary": None,
        "visibility": "PUBLIC",
        "status": "ACTIVE",
        "download_count": 0,
        "star_count": 0,
        "subscription_count": 0,
        "rating_avg": Decimal("0.00"),
        "rating_count": 0,
        "hidden": False,
        "namespace": "global",
        "published_version_id": None,
        "published_version": None,
        "published_version_status": None,
        "resolution_mode": "NONE",
    }

    response = build_skill_detail_response(row, [])

    assert response["ownerDisplayName"] is None
    assert response["summary"] is None
    assert response["ratingAvg"] == 0.0
    assert response["headlineVersion"] is None
    assert response["publishedVersion"] is None
    assert response["ownerPreviewVersion"] is None
    assert response["ownerPreviewReviewComment"] is None
    assert response["resolutionMode"] == "NONE"


def test_build_skill_detail_response_preserves_label_order() -> None:
    row = {
        "id": 33,
        "slug": "labeled",
        "display_name": "Labeled",
        "owner_id": "owner-1",
        "owner_display_name": "",
        "summary": "",
        "visibility": "PUBLIC",
        "status": "ACTIVE",
        "download_count": 1,
        "star_count": 0,
        "subscription_count": 0,
        "rating_avg": Decimal("0.00"),
        "rating_count": 0,
        "hidden": False,
        "namespace": "global",
        "published_version_id": 51,
        "published_version": "1.0.0",
        "published_version_status": "PUBLISHED",
        "resolution_mode": "PUBLISHED",
    }
    labels = [
        {"slug": "a", "type": "RECOMMENDED", "displayName": "A"},
        {"slug": "b", "type": "PRIVILEGED", "displayName": "B"},
    ]

    assert build_skill_detail_response(row, labels)["labels"] == labels


def detail_row(**overrides: object) -> dict[str, object]:
    row: dict[str, object] = {
        "id": 40,
        "slug": "viewer-skill",
        "display_name": "Viewer Skill",
        "owner_id": "owner-1",
        "owner_display_name": "Owner One",
        "summary": "Viewer summary",
        "visibility": "PUBLIC",
        "status": "ACTIVE",
        "download_count": 1,
        "star_count": 0,
        "subscription_count": 0,
        "rating_avg": Decimal("0.00"),
        "rating_count": 0,
        "hidden": False,
        "namespace": "team-alpha",
        "namespace_type": "TEAM",
        "namespace_status": "ACTIVE",
        "published_version_id": 70,
        "published_version": "1.0.0",
        "published_version_status": "PUBLISHED",
        "resolution_mode": "PUBLISHED",
        "current_user_id": None,
        "namespace_role": None,
        "promotion_blocked": False,
    }
    row.update(overrides)
    return row


def test_build_skill_detail_response_grants_owner_lifecycle_and_disables_report() -> None:
    response = build_skill_detail_response(
        detail_row(current_user_id="owner-1"),
        [],
    )

    assert response["canManageLifecycle"] is True
    assert response["canReport"] is False


def test_build_skill_detail_response_grants_namespace_admin_lifecycle() -> None:
    response = build_skill_detail_response(
        detail_row(current_user_id="manager-1", namespace_role="ADMIN"),
        [],
    )

    assert response["canManageLifecycle"] is True
    assert response["canReport"] is True


def test_build_skill_detail_response_allows_team_promotion_for_manager_when_not_blocked() -> None:
    response = build_skill_detail_response(
        detail_row(current_user_id="manager-1", namespace_role="OWNER"),
        [],
    )

    assert response["canSubmitPromotion"] is True


def test_build_skill_detail_response_disables_promotion_for_global_namespace() -> None:
    response = build_skill_detail_response(
        detail_row(
            namespace="global",
            namespace_type="GLOBAL",
            current_user_id="owner-1",
        ),
        [],
    )

    assert response["canManageLifecycle"] is True
    assert response["canSubmitPromotion"] is False


def test_build_skill_detail_response_disables_promotion_when_request_exists() -> None:
    response = build_skill_detail_response(
        detail_row(
            current_user_id="manager-1",
            namespace_role="OWNER",
            promotion_blocked=True,
        ),
        [],
    )

    assert response["canManageLifecycle"] is True
    assert response["canSubmitPromotion"] is False
