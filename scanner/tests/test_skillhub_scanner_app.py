import asyncio
import importlib.util
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch


class _FakeRouter:
    def __init__(self): self.handlers = []
    def add_event_handler(self, event, handler): self.handlers.append((event, handler))


class _FakeApp:
    def __init__(self): self.router = _FakeRouter()
    def middleware(self, _kind): return lambda function: function


class _FakeResponse:
    def __init__(self, status_code, content, headers):
        self.status_code, self.content, self.headers = status_code, content, headers


class _Request:
    method = "POST"
    url = types.SimpleNamespace(path="/scan-upload")


def _load_module():
    fastapi = types.ModuleType("fastapi"); fastapi.Request = object
    responses = types.ModuleType("fastapi.responses"); responses.JSONResponse = _FakeResponse
    api = types.ModuleType("skill_scanner.api.api"); api.app = _FakeApp()
    stubs = {"fastapi": fastapi, "fastapi.responses": responses, "skill_scanner": types.ModuleType("skill_scanner"), "skill_scanner.api": types.ModuleType("skill_scanner.api"), "skill_scanner.api.api": api}
    with patch.dict(sys.modules, stubs):
        path = Path(__file__).parents[1] / "skillhub_scanner_app.py"
        spec = importlib.util.spec_from_file_location("skillhub_scanner_app_under_test", path)
        module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
        return module


class SkillHubScannerAppTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self): self.module = _load_module()

    async def test_excess_scan_is_rejected(self):
        self.module._active_scans = 1
        response = await self.module.limit_concurrent_scans(_Request(), lambda _request: None)
        self.assertEqual(503, response.status_code); self.assertEqual("30", response.headers["Retry-After"])

    async def test_client_disconnect_keeps_slot_until_scan_finishes(self):
        release = asyncio.Event()
        async def scan(_request): await release.wait(); return "done"
        task = asyncio.create_task(self.module.limit_concurrent_scans(_Request(), scan)); await asyncio.sleep(0); task.cancel(); await asyncio.sleep(0)
        self.assertEqual(1, self.module._active_scans)
        self.assertEqual(503, (await self.module.limit_concurrent_scans(_Request(), scan)).status_code)
        release.set()
        with self.assertRaises(asyncio.CancelledError): await task
        self.assertEqual(0, self.module._active_scans)

    async def test_hard_timeout_requests_process_restart(self):
        self.module._HARD_TIMEOUT_SECONDS = 0.01
        async def stuck(_request): await asyncio.Event().wait()
        with patch.object(self.module, "_restart_after_hard_timeout", side_effect=RuntimeError("restart requested")) as restart:
            with self.assertRaisesRegex(RuntimeError, "restart requested"): await self.module.limit_concurrent_scans(_Request(), stuck)
        restart.assert_called_once_with("/scan-upload")

    async def test_cleanup_is_scanner_owned_and_registered(self):
        with tempfile.TemporaryDirectory() as root_value:
            root = Path(root_value); (root / "skill_scanner_old").mkdir(); (root / "skillhub-data").mkdir()
            self.module._cleanup_stale_scan_directories(root)
            self.assertFalse((root / "skill_scanner_old").exists()); self.assertTrue((root / "skillhub-data").exists())
        self.assertEqual([("startup", self.module._cleanup_stale_scan_directories)], self.module.app.router.handlers)
