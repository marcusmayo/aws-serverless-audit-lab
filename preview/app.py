from __future__ import annotations

import argparse
import json
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from audit.audit_template import audit_text
from audit.oracle import OracleDefinitionError, list_cases, run_suite

ASSET_DIR = Path(__file__).parent
CASE_ROOT = ASSET_DIR.parent / "task_cases"
DEMO_TEMPLATE = ASSET_DIR / "demo" / "template.yaml"
DEMO_SOURCE = "portfolio-demo.yaml"
MAX_TEMPLATE_BYTES = 512 * 1024
MAX_ORACLE_REQUEST_BYTES = 4096
ASSETS = {
    "/": ("index.html", "text/html; charset=utf-8"),
    "/app.js": ("app.js", "text/javascript; charset=utf-8"),
    "/styles.css": ("styles.css", "text/css; charset=utf-8"),
}


def audit_payload(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise ValueError("Request body must be a JSON object.")
    template = payload.get("template")
    source = payload.get("source", "codespaces-preview.yaml")
    if not isinstance(template, str) or not template.strip():
        raise ValueError("template must be a non-empty string.")
    if len(template.encode("utf-8")) > MAX_TEMPLATE_BYTES:
        raise ValueError("template exceeds the 512 KiB preview limit.")
    if not isinstance(source, str) or not source or len(source) > 200:
        raise ValueError("source must be a string between 1 and 200 characters.")

    # Do not resolve DefinitionUri against repository files in the browser preview.
    isolated_base = ASSET_DIR / "no-external-definitions"
    return audit_text(template, source=source, base_dir=isolated_base)


def demo_payload() -> dict[str, Any]:
    """Return the repository-owned demo input and its report as one atomic payload."""
    template = DEMO_TEMPLATE.read_text(encoding="utf-8")
    return {
        "source": DEMO_SOURCE,
        "template": template,
        "report": audit_payload({"source": DEMO_SOURCE, "template": template}),
    }


class PreviewHandler(BaseHTTPRequestHandler):
    server_version = "AuditPreview/1.2"

    def _security_headers(self) -> None:
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Security-Policy", "default-src 'self'; connect-src 'self'; img-src 'self' data:")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")

    def _send_json(self, status: HTTPStatus, payload: dict[str, Any]) -> None:
        body = json.dumps(payload, sort_keys=True).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self._security_headers()
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802
        if self.path == "/api/health":
            try:
                case_count = len(list_cases(CASE_ROOT))
            except OracleDefinitionError as exc:
                self._send_json(HTTPStatus.INTERNAL_SERVER_ERROR, {"error": str(exc)})
                return
            self._send_json(
                HTTPStatus.OK,
                {
                    "status": "ok",
                    "service": "aws-serverless-audit-lab",
                    "mode": "STATIC_ONLY",
                    "oracle_case_count": case_count,
                },
            )
            return
        if self.path == "/api/demo":
            try:
                self._send_json(HTTPStatus.OK, demo_payload())
            except OSError:
                self._send_json(
                    HTTPStatus.INTERNAL_SERVER_ERROR,
                    {"error": "repository-owned demo template is unavailable"},
                )
            return
        if self.path == "/api/oracle/cases":
            try:
                self._send_json(HTTPStatus.OK, {"cases": list_cases(CASE_ROOT)})
            except OracleDefinitionError as exc:
                self._send_json(HTTPStatus.INTERNAL_SERVER_ERROR, {"error": str(exc)})
            return
        asset = ASSETS.get(self.path)
        if asset is None:
            self._send_json(HTTPStatus.NOT_FOUND, {"error": "not found"})
            return
        filename, content_type = asset
        body = (ASSET_DIR / filename).read_bytes()
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self._security_headers()
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self) -> None:  # noqa: N802
        if self.path not in {"/api/audit", "/api/oracle/run"}:
            self._send_json(HTTPStatus.NOT_FOUND, {"error": "not found"})
            return
        if self.headers.get("Content-Type", "").split(";", 1)[0].strip() != "application/json":
            self._send_json(
                HTTPStatus.UNSUPPORTED_MEDIA_TYPE,
                {"error": "Content-Type must be application/json."},
            )
            return
        try:
            content_length = int(self.headers.get("Content-Length", "0"))
            request_limit = (
                MAX_ORACLE_REQUEST_BYTES
                if self.path == "/api/oracle/run"
                else MAX_TEMPLATE_BYTES + 4096
            )
            if content_length <= 0 or content_length > request_limit:
                raise ValueError("request size is invalid or exceeds the preview limit.")
            payload = json.loads(self.rfile.read(content_length))
            if self.path == "/api/oracle/run":
                if payload != {}:
                    raise ValueError("oracle run accepts only an empty JSON object.")
                response = run_suite(CASE_ROOT)
            else:
                response = audit_payload(payload)
        except OracleDefinitionError as exc:
            self._send_json(HTTPStatus.INTERNAL_SERVER_ERROR, {"error": str(exc)})
            return
        except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
            self._send_json(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
            return
        self._send_json(HTTPStatus.OK, response)

    def log_message(self, format: str, *args: object) -> None:
        # Keep standard request metadata while never logging submitted template bodies.
        super().log_message(format, *args)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Serve the local AWS audit browser preview")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args(argv)
    server = ThreadingHTTPServer((args.host, args.port), PreviewHandler)
    print(f"Audit preview listening on http://{args.host}:{args.port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping audit preview.")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
