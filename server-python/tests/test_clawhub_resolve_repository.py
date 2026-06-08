from app.api.skills import build_clawhub_resolve_response, from_clawhub_canonical_slug


def test_from_clawhub_canonical_slug_maps_global_and_namespace() -> None:
    assert from_clawhub_canonical_slug("demo") == ("global", "demo")
    assert from_clawhub_canonical_slug("team-ai--demo") == ("team-ai", "demo")


def test_from_clawhub_canonical_slug_splits_on_first_separator_only() -> None:
    assert from_clawhub_canonical_slug("team--demo--extra") == ("team", "demo--extra")


def test_build_clawhub_resolve_response_maps_plain_version_info() -> None:
    assert build_clawhub_resolve_response({"version": "1.2.0"}) == {
        "match": {"version": "1.2.0"},
        "latestVersion": {"version": "1.2.0"},
    }


def test_build_clawhub_resolve_response_handles_missing_version() -> None:
    assert build_clawhub_resolve_response({"version": None}) == {
        "match": None,
        "latestVersion": None,
    }
