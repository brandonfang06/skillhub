from app.api.labels import build_label_response, build_skill_label_response


def test_build_label_response_sorts_visible_labels_and_uses_requested_locale() -> None:
    labels = [
        {"id": 2, "slug": "beta", "type": "RECOMMENDED", "sort_order": 20, "visible_in_filter": True},
        {"id": 1, "slug": "official", "type": "RECOMMENDED", "sort_order": 10, "visible_in_filter": True},
        {"id": 3, "slug": "hidden", "type": "PRIVILEGED", "sort_order": 5, "visible_in_filter": False},
    ]
    translations = [
        {"label_id": 1, "locale": "en", "display_name": "Official"},
        {"label_id": 1, "locale": "zh_CN", "display_name": "Official Zh"},
        {"label_id": 2, "locale": "en", "display_name": "Beta"},
    ]

    assert build_label_response(labels, translations, "zh-CN") == [
        {"slug": "official", "type": "RECOMMENDED", "displayName": "Official Zh"},
        {"slug": "beta", "type": "RECOMMENDED", "displayName": "Beta"},
    ]


def test_build_label_response_falls_back_to_slug_without_translations() -> None:
    labels = [
        {"id": 4, "slug": "internal", "type": "PRIVILEGED", "sort_order": 1, "visible_in_filter": True}
    ]

    assert build_label_response(labels, [], "en") == [
        {"slug": "internal", "type": "PRIVILEGED", "displayName": "internal"}
    ]


def test_build_label_response_falls_back_to_language_then_english_then_slug() -> None:
    labels = [
        {"id": 5, "slug": "localized", "type": "RECOMMENDED", "sort_order": 1, "visible_in_filter": True},
        {"id": 6, "slug": "english-only", "type": "RECOMMENDED", "sort_order": 2, "visible_in_filter": True},
        {"id": 7, "slug": "slug-only", "type": "RECOMMENDED", "sort_order": 3, "visible_in_filter": True},
    ]
    translations = [
        {"label_id": 5, "locale": "zh", "display_name": "Chinese"},
        {"label_id": 6, "locale": "en", "display_name": "English"},
        {"label_id": 6, "locale": "fr", "display_name": "French"},
    ]

    assert build_label_response(labels, translations, "zh-TW") == [
        {"slug": "localized", "type": "RECOMMENDED", "displayName": "Chinese"},
        {"slug": "english-only", "type": "RECOMMENDED", "displayName": "English"},
        {"slug": "slug-only", "type": "RECOMMENDED", "displayName": "slug-only"},
    ]


def test_build_skill_label_response_sorts_by_type_then_slug_and_localizes() -> None:
    labels = [
        {"id": 3, "slug": "team", "type": "RECOMMENDED"},
        {"id": 1, "slug": "verified", "type": "PRIVILEGED"},
        {"id": 2, "slug": "official", "type": "PRIVILEGED"},
    ]
    translations = [
        {"label_id": 1, "locale": "en", "display_name": "Verified"},
        {"label_id": 2, "locale": "en", "display_name": "Official"},
        {"label_id": 3, "locale": "en", "display_name": "Team"},
    ]

    assert build_skill_label_response(labels, translations, "en") == [
        {"slug": "official", "type": "PRIVILEGED", "displayName": "Official"},
        {"slug": "verified", "type": "PRIVILEGED", "displayName": "Verified"},
        {"slug": "team", "type": "RECOMMENDED", "displayName": "Team"},
    ]
