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
