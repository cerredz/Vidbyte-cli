"""Shared OAuth primitives for local provider connections.

This module handles unpredictable state, PKCE, loopback callbacks, browser guidance, and bounded
HTTP responses. Provider adapters remain responsible for their URLs, scopes, and token shapes.
"""

from __future__ import annotations

import base64
import hashlib
import secrets
import time
import webbrowser
from collections.abc import Mapping
from http.server import BaseHTTPRequestHandler, HTTPServer
from threading import Lock
from typing import TYPE_CHECKING, cast
from urllib.parse import parse_qs, urlparse

from ..errors.failures import (
    ConnectionApiUnavailable,
    ConnectionAuthenticationRequired,
    ConnectionOAuthFailed,
    ConnectionProtocolError,
    ConnectionRateLimited,
)
from ..io.streams import IOStreams

if TYPE_CHECKING:
    import httpx

_MAX_JSON_BYTES = 1_048_576
_MAX_RESOURCE_BYTES = 10 * 1_048_576
_MAX_CALLBACK_SECONDS = 600
_CALLBACK_PATH = "/callback"


class PkceChallenge:
    """An OAuth state value and S256 PKCE verifier/challenge pair."""

    def __init__(self, verifier: str, challenge: str, state: str) -> None:
        # Values are generated together so an adapter cannot accidentally mix sessions.
        self.verifier = verifier
        self.challenge = challenge
        self.state = state

    @classmethod
    def generate(cls) -> PkceChallenge:
        # RFC 7636 allows a high-entropy URL-safe verifier with an S256 challenge.
        verifier = cls._random_url_value(32)
        challenge = cls._s256(verifier)
        state = cls._random_url_value(32)
        return cls(verifier, challenge, state)

    @staticmethod
    def _random_url_value(byte_count: int) -> str:
        # URL-safe values avoid quoting surprises in authorization query strings.
        return base64.urlsafe_b64encode(secrets.token_bytes(byte_count)).rstrip(b"=").decode()

    @staticmethod
    def _s256(value: str) -> str:
        # The challenge is a base64url SHA-256 digest of the verifier.
        digest = hashlib.sha256(value.encode("ascii")).digest()
        return base64.urlsafe_b64encode(digest).rstrip(b"=").decode()


class _CallbackHTTPServer(HTTPServer):
    """HTTPServer carrying one parsed OAuth callback."""

    query: dict[str, str] | None = None
    callback_path = _CALLBACK_PATH
    query_lock = Lock()


class _OAuthCallbackHandler(BaseHTTPRequestHandler):
    """Accepts exactly the callback path and stores only its query fields."""

    def do_GET(self) -> None:
        # Authorization codes are captured in memory and never written to output.
        server = cast(_CallbackHTTPServer, self.server)
        parsed = urlparse(self.path)
        if parsed.path != server.callback_path:
            self._write_page(404, "Not found.")
            return
        values = parse_qs(parsed.query, keep_blank_values=True)
        with server.query_lock:
            server.query = {key: value[-1] for key, value in values.items() if value}
        self._write_page(200, "Authorization received. You may close this window.")

    def log_message(self, format: str, *args: object) -> None:
        # The standard handler would log callback query values, including authorization codes.
        return

    def _write_page(self, status: int, message: str) -> None:
        # Return a minimal generic response without reflecting provider query values.
        body = (
            "<!doctype html><html><head><title>Vidbyte</title></head><body>"
            f"<p>{message}</p></body></html>"
        ).encode()
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


class OAuthCallbackServer:
    """One-shot loopback server for authorization-code callbacks."""

    def __init__(self, provider: str = "oauth", redirect_host: str = "127.0.0.1") -> None:
        # Ephemeral ports avoid conflicts when multiple profiles authorize concurrently.
        self._provider = provider
        try:
            self._server = _CallbackHTTPServer(("127.0.0.1", 0), _OAuthCallbackHandler)
        except OSError as error:
            raise ConnectionOAuthFailed(provider, error) from error
        self._server.timeout = 0.25
        self.redirect_uri = f"http://{redirect_host}:{self._server.server_port}{_CALLBACK_PATH}"

    def __enter__(self) -> OAuthCallbackServer:
        # Returning the active server makes the dynamic redirect URI available to an adapter.
        return self

    def __exit__(self, exc_type: object, exc_value: object, traceback: object) -> None:
        # Closing the listening socket releases the ephemeral port on success and failure.
        self._server.server_close()

    def wait(self, timeout_seconds: float) -> dict[str, str]:
        # Serves harmless wrong paths until the callback arrives or the bounded deadline passes.
        deadline = time.monotonic() + min(timeout_seconds, _MAX_CALLBACK_SECONDS)
        while time.monotonic() < deadline:
            self._server.handle_request()
            with self._server.query_lock:
                if self._server.query is not None:
                    return dict(self._server.query)
        raise ConnectionOAuthFailed(self._provider, TimeoutError("callback timed out"))


class OAuthBrowser:
    """Opens an authorization URL and provides a manual fallback."""

    def open(self, url: str, streams: IOStreams) -> None:
        # Browser failure is recoverable because the same URL is safe to open manually.
        streams.write_error("Opening the provider authorization page in your browser...")
        try:
            opened = webbrowser.open(url, new=2, autoraise=True)
        except webbrowser.Error:
            opened = False
        if not opened:
            streams.write_error(f"Open this authorization URL manually: {url}")


class OAuthHttpClient:
    """Bounded non-redirecting HTTP client for one provider."""

    def __init__(self, provider: str, timeout_seconds: float) -> None:
        # The provider label selects safe failure wording and never contains a secret.
        self._provider = provider
        self._timeout_seconds = timeout_seconds

    def post_form(self, url: str, values: Mapping[str, str], headers: Mapping[str, str] | None = None) -> dict[str, object]:  # fmt: skip  # noqa: E501
        # Posts a form to an OAuth endpoint and validates its bounded JSON response.
        import httpx

        try:
            with httpx.Client(timeout=self._timeout_seconds, follow_redirects=False) as client:
                response = client.post(url, data=dict(values), headers=dict(headers or {}))
        except httpx.HTTPError as error:
            raise ConnectionApiUnavailable(self._provider, error) from error
        self._classify_status(response.status_code, resource=False)
        return self._decode_json(response)

    def get_json(self, url: str, headers: Mapping[str, str], params: Mapping[str, str] | None = None) -> dict[str, object]:  # fmt: skip  # noqa: E501
        # Gets and validates a bounded JSON API response without following redirects.
        import httpx

        try:
            with httpx.Client(timeout=self._timeout_seconds, follow_redirects=False) as client:
                response = client.get(url, headers=dict(headers), params=dict(params or {}))
        except httpx.HTTPError as error:
            raise ConnectionApiUnavailable(self._provider, error) from error
        self._classify_status(response.status_code, resource=True)
        return self._decode_json(response)

    def get_bytes(self, url: str, headers: Mapping[str, str], params: Mapping[str, str] | None = None) -> bytes:  # fmt: skip  # noqa: E501
        # Gets a bounded resource body for a file read without decoding it prematurely.
        import httpx

        try:
            with httpx.Client(timeout=self._timeout_seconds, follow_redirects=False) as client:
                with client.stream(
                    "GET", url, headers=dict(headers), params=dict(params or {})
                ) as response:
                    self._classify_status(response.status_code, resource=True)
                    chunks: list[bytes] = []
                    size = 0
                    for chunk in response.iter_bytes():
                        size += len(chunk)
                        if size > _MAX_RESOURCE_BYTES:
                            raise ConnectionProtocolError(
                                self._provider, ValueError("resource is oversized")
                            )
                        chunks.append(chunk)
        except httpx.HTTPError as error:
            raise ConnectionApiUnavailable(self._provider, error) from error
        return b"".join(chunks)

    def _classify_status(self, status: int, resource: bool) -> None:
        # Maps provider HTTP status classes to stable CLI failures before decoding bodies.
        if status == 429:
            raise ConnectionRateLimited(self._provider)
        if status in (401, 403):
            raise ConnectionAuthenticationRequired(self._provider)
        if status == 404 and resource:
            from ..errors.failures import ConnectionResourceUnavailable

            raise ConnectionResourceUnavailable(self._provider)
        if status >= 500:
            raise ConnectionApiUnavailable(self._provider)
        if status >= 300:
            if resource:
                from ..errors.failures import ConnectionResourceUnavailable

                raise ConnectionResourceUnavailable(self._provider)
            raise ConnectionOAuthFailed(self._provider)

    def _decode_json(self, response: httpx.Response) -> dict[str, object]:
        # Validates body size, JSON object shape, and provider-independent protocol safety.
        if len(response.content) > _MAX_JSON_BYTES:
            raise ConnectionProtocolError(self._provider, ValueError("response is oversized"))
        try:
            payload = response.json()
        except ValueError as error:
            raise ConnectionProtocolError(self._provider, error) from error
        if not isinstance(payload, dict):
            raise ConnectionProtocolError(self._provider, ValueError("response is not an object"))
        return cast(dict[str, object], payload)
