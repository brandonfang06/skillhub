from __future__ import annotations

import json
import ssl
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread
from urllib.error import URLError
from urllib.request import urlopen

from skillhub_oss_importer.client import SkillHubClient


def run_probe(certificate: Path, private_key: Path) -> None:
    requests: list[str] = []

    class Handler(BaseHTTPRequestHandler):
        def do_PUT(self) -> None:
            requests.append(self.path)
            content = json.dumps({"code": 0, "data": {"outcome": "EXISTS"}}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(content)))
            self.end_headers()
            self.wfile.write(content)

        def log_message(self, _format: str, *_args: object) -> None:
            pass

    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(certificate, private_key)
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    server.socket = context.wrap_socket(server.socket, server_side=True)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base_url = f"https://127.0.0.1:{server.server_port}"
    try:
        try:
            urlopen(base_url, timeout=10)
        except URLError as exc:
            if not isinstance(exc.reason, ssl.SSLCertVerificationError):
                raise
        else:
            raise AssertionError("Self-signed certificate unexpectedly passed default verification")

        result = SkillHubClient(base_url, "secret", 10).ensure_namespace(
            "oss-owner-repo",
            {},
        )
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)

    assert result["outcome"] == "EXISTS"
    assert requests == ["/api/cli/v1/source-imports/namespaces/oss-owner-repo"]


if __name__ == "__main__":
    if len(sys.argv) != 3:
        raise SystemExit("usage: tls_runtime_probe.py CERTIFICATE PRIVATE_KEY")
    run_probe(Path(sys.argv[1]), Path(sys.argv[2]))
