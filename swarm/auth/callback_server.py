"""OAuth callback server — lightweight HTTP server to receive Feishu redirects."""

from __future__ import annotations

import asyncio
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
import threading

import structlog

logger = structlog.get_logger(__name__)


class OAuthCallbackServer:
    """Lightweight HTTP server that listens for Feishu OAuth redirects.

    Usage:
        server = OAuthCallbackServer(port=9876)
        code = await server.wait_for_code(timeout=120)  # Blocks until code received
        server.stop()
    """

    def __init__(self, port: int = 9876):
        self._port = port
        self._code: str | None = None
        self._state: str | None = None
        self._error: str | None = None
        self._received_event = threading.Event()
        self._server: HTTPServer | None = None
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        """Start the HTTP server in a background thread."""
        handler = self._make_handler()
        self._server = HTTPServer(("0.0.0.0", self._port), handler)
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()
        logger.info("oauth_callback_server_started", port=self._port)

    def stop(self) -> None:
        """Stop the HTTP server."""
        if self._server:
            self._server.shutdown()
        if self._thread:
            self._thread.join(timeout=2.0)
        logger.info("oauth_callback_server_stopped")

    async def wait_for_code(self, timeout: float = 120.0) -> tuple[str | None, str | None]:
        """Wait for the OAuth callback. Returns (code, state) or (None, error)."""
        received = await asyncio.to_thread(self._received_event.wait, timeout=timeout)
        if not received:
            self._error = "Timeout waiting for authorization"
            return None, None

        if self._error:
            return None, self._error
        return self._code, self._state

    def _make_handler(self):
        server_ref = self

        class CallbackHandler(BaseHTTPRequestHandler):
            def do_GET(self):
                parsed = urlparse(self.path)
                params = parse_qs(parsed.query)

                if parsed.path == "/oauth/callback" or parsed.path == "/":
                    code = params.get("code", [None])[0]
                    state = params.get("state", [None])[0]
                    error = params.get("error", [None])[0]

                    if error:
                        server_ref._error = error
                        server_ref._received_event.set()
                        self._send_response(400, f"Authorization failed: {error}")
                    elif code:
                        server_ref._code = code
                        server_ref._state = state
                        server_ref._received_event.set()
                        self._send_response(200,
                            "Authorization successful! You can close this window and return to Feishu.")
                    else:
                        self._send_response(400, "Missing authorization code")
                else:
                    self._send_response(404, "Not Found")

            def _send_response(self, status: int, body: str):
                self.send_response(status)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.end_headers()
                html = f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>Swarm OAuth</title></head>
<body style="font-family: sans-serif; padding: 40px; text-align: center;">
<h2>Swarm</h2>
<p>{body}</p>
</body></html>"""
                self.wfile.write(html.encode("utf-8"))

            def log_message(self, format, *args):
                pass  # Suppress default logging

        return CallbackHandler


async def run_oauth_flow(oauth, user_id: str) -> tuple[str | None, str | None]:
    """Run the complete OAuth flow for a user.

    Returns (access_token, error_message).
    """
    from swarm.auth.callback_server import OAuthCallbackServer

    server = OAuthCallbackServer(port=9876)
    server.start()

    auth_url = oauth.get_authorization_url(state=user_id)
    logger.info("oauth_flow_started", user_id=user_id, auth_url=auth_url)

    code, error = await server.wait_for_code(timeout=300.0)
    server.stop()

    if error or not code:
        return None, error or "No authorization code received"

    token = await oauth.exchange_code_for_token(code)
    if not token:
        return None, "Failed to exchange code for token"

    oauth._token_store.save(user_id, token)
    return token.access_token, None
