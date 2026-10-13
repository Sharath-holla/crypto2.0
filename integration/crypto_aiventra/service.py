"""Private loopback adapter service, isolated from Aiventra's Python environment."""

from __future__ import annotations

import argparse
import hmac
import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit

from . import runtime
from .adapter import Crypto2Adapter, redact
from .config import require_branch
from .jobs import JobRequest, preview


class Handler(BaseHTTPRequestHandler):
    adapter: Crypto2Adapter

    def log_message(self, *_args):
        pass  # Neither query strings nor authentication headers go to access logs.

    def reply(self, status, payload):
        content = json.dumps(redact(payload), sort_keys=True, default=str, allow_nan=False).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Content-Length", str(len(content)))
        self.end_headers()
        self.wfile.write(content)

    def authorized(self):
        configured = os.environ.get("CRYPTO_ADAPTER_TOKEN", "")
        return len(configured) >= 32 and hmac.compare_digest(
            self.headers.get("Authorization", ""), "Bearer " + configured
        )

    def dispatch(self):
        if not self.authorized():
            return self.reply(401, {"detail": "Private adapter authentication required"})
        url = urlsplit(self.path)
        query = {key: values[0] for key, values in parse_qs(url.query).items()}
        try:
            if self.command == "GET":
                if url.path == "/snapshot":
                    result = self.adapter.snapshot()
                elif url.path == "/health":
                    result = {"status": "PASS", "identity": self.adapter.get_project_identity()}
                elif url.path == "/models":
                    result = self.adapter.get_model_results(query.get("fold_id"))
                elif url.path == "/artifacts":
                    result = self.adapter.get_artifacts(
                        query.get("category", "reports"), query.get("path", ".")
                    )
                elif url.path == "/document":
                    result = self.adapter.get_logs(
                        query.get("category", "logs"),
                        query.get("path", ""),
                        tail=query.get("tail") == "true",
                    )
                elif url.path.startswith("/job-logs/"):
                    result = runtime.job_log(self.adapter, url.path.removeprefix("/job-logs/"))
                elif url.path.startswith("/jobs/"):
                    result = runtime.status(self.adapter, url.path.removeprefix("/jobs/"))
                else:
                    return self.reply(404, {"detail": "Unknown adapter operation"})
            elif self.command == "POST":
                size = int(self.headers.get("Content-Length", "0"))
                if not 0 < size <= 65536:
                    raise ValueError("Request body exceeds bounds")
                data = json.loads(self.rfile.read(size))
                if url.path == "/preview":
                    result = preview(JobRequest.model_validate(data), self.adapter)
                elif url.path == "/submit" and set(data) == {"job_id", "scope", "approval"}:
                    result = runtime.submit(
                        self.adapter, data["job_id"], data["scope"], data["approval"]
                    )
                elif url.path == "/stop" and set(data) == {"job_id", "approval"}:
                    result = runtime.stop(self.adapter, data["job_id"], data["approval"])
                else:
                    return self.reply(404, {"detail": "Unknown adapter operation"})
            else:
                return self.reply(405, {"detail": "Unsupported method"})
            self.reply(200, result)
        except PermissionError:
            self.reply(
                403,
                {"detail": "Operation blocked by branch, approval or scientific execution policy"},
            )
        except (ValueError, KeyError, TypeError):
            self.reply(422, {"detail": "Invalid or inconsistent typed scope/evidence"})
        except FileNotFoundError:
            self.reply(404, {"detail": "Evidence is not available"})
        except Exception:
            self.reply(503, {"detail": "Adapter evidence unavailable; no success inferred"})

    do_GET = dispatch
    do_POST = dispatch


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8011)
    args = parser.parse_args()
    runtime.signing_key()
    Handler.adapter = Crypto2Adapter()
    require_branch(Handler.adapter.paths.repo)
    server = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    print(
        f"Private Crypto adapter on loopback port {args.port}; no scientific job started",
        flush=True,
    )
    server.serve_forever()


if __name__ == "__main__":
    main()
