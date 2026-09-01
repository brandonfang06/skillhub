from pathlib import Path
import tempfile
import unittest

from skillhub_client import SkillHubClient


class FakeResponse:
    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict[str, object]:
        return {"code": 0, "msg": "ok", "data": {"ok": True}}


class RecordingSession:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str, dict[str, object]]] = []

    def get(self, url: str, **kwargs: object) -> FakeResponse:
        self.calls.append(("GET", url, kwargs))
        return FakeResponse()

    def post(self, url: str, **kwargs: object) -> FakeResponse:
        files = kwargs.get("files")
        if isinstance(files, dict):
            archive = files["file"]
            kwargs = {**kwargs, "archive_name": archive[0], "archive_bytes": archive[1].read()}
        self.calls.append(("POST", url, kwargs))
        return FakeResponse()

    def put(self, url: str, **kwargs: object) -> FakeResponse:
        self.calls.append(("PUT", url, kwargs))
        return FakeResponse()


class SkillHubClientTest(unittest.TestCase):
    def setUp(self) -> None:
        self.session = RecordingSession()
        self.client = SkillHubClient(
            "https://example.test/skillhub/",
            token="secret",
            session=self.session,
        )

    def test_search_preserves_subpath_and_uses_zero_based_page(self) -> None:
        self.client.search(keyword="email")

        method, url, kwargs = self.session.calls[-1]
        self.assertEqual((method, url), ("GET", "https://example.test/skillhub/api/v1/skills"))
        self.assertEqual(kwargs["params"]["page"], 0)
        self.assertEqual(kwargs["headers"]["Authorization"], "Bearer secret")

    def test_star_and_rate_use_fastapi_skill_id_put_routes(self) -> None:
        self.client.star("skill-123")
        self.client.rate("skill-123", 4)

        self.assertEqual(
            [(method, url) for method, url, _ in self.session.calls],
            [
                ("PUT", "https://example.test/skillhub/api/v1/skills/skill-123/star"),
                ("PUT", "https://example.test/skillhub/api/v1/skills/skill-123/rating"),
            ],
        )
        self.assertEqual(self.session.calls[-1][2]["json"], {"score": 4})

    def test_publish_sends_namespace_archive_and_request_id(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            archive = Path(temporary_directory) / "skill.zip"
            archive.write_bytes(b"PK\x03\x04example")
            self.client.publish(str(archive), "team-a", request_id="request-1")

        method, url, kwargs = self.session.calls[-1]
        self.assertEqual((method, url), ("POST", "https://example.test/skillhub/api/v1/publish"))
        self.assertEqual(kwargs["data"], {"namespace": "team-a"})
        self.assertEqual(kwargs["headers"]["X-Request-Id"], "request-1")
        self.assertEqual(kwargs["archive_name"], "skill.zip")
        self.assertEqual(kwargs["archive_bytes"], b"PK\x03\x04example")

    def test_rate_rejects_out_of_range_score_before_network(self) -> None:
        with self.assertRaisesRegex(ValueError, "between 1 and 5"):
            self.client.rate("skill-123", 6)
        self.assertEqual(self.session.calls, [])


if __name__ == "__main__":
    unittest.main()
