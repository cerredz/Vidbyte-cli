"""Offline verification for context-provider OAuth, storage, status, and bounded reads.

The script uses loopback HTTP servers, a fake keyring, and a browser callback harness. It never
contacts GitHub, Slack, Google, or the developer's real credential store.
"""

from __future__ import annotations

import io
import json
import shutil
import sys
import tempfile
import threading
import time
import webbrowser
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlencode, urlparse

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from pydantic import SecretStr, ValidationError  # noqa: E402

import vidbyte_cli.cli  # noqa: E402, F401
from vidbyte_cli.lib.config.models import ConfigField, ConfigSource, ResolvedConfig  # noqa: E402
from vidbyte_cli.lib.config.paths import VidbytePaths  # noqa: E402
from vidbyte_cli.lib.connections.manager import ConnectionManager  # noqa: E402
from vidbyte_cli.lib.connections.providers import github, google_drive, slack  # noqa: E402
from vidbyte_cli.lib.connections.store import ConnectionKeyringStore, ConnectionStore  # noqa: E402
from vidbyte_cli.lib.errors.cli_error import CliError  # noqa: E402
from vidbyte_cli.lib.errors.codes import CliErrorCode  # noqa: E402
from vidbyte_cli.lib.io import IOStreams  # noqa: E402
from vidbyte_cli.lib.output.formats import ColorMode, OutputFormat  # noqa: E402
from vidbyte_cli.lib.runtime.application import CliApplication  # noqa: E402
from vidbyte_cli.lib.runtime.context import ApplicationContext, InvocationOptions  # noqa: E402
from vidbyte_cli.types.connection import (  # noqa: E402
    ConnectionProvider,
    ConnectionResource,
    ConnectionToken,
)


@dataclass
class FakeResponse:
    """One response queued for a method/path pair."""

    status: int = 200
    body: bytes = b"{}"
    headers: dict[str, str] = field(default_factory=dict)

    @classmethod
    def json(cls, payload: object, status: int = 200) -> FakeResponse:
        # Encodes a deterministic JSON response for the adapter under test.
        return cls(
            status=status,
            body=json.dumps(payload).encode(),
            headers={"Content-Type": "application/json"},
        )


@dataclass
class RequestRecord:
    """One request captured by the loopback fake provider."""

    method: str
    path: str
    query: str
    headers: dict[str, str]
    body: bytes


class FakeHTTPServer(ThreadingHTTPServer):
    """HTTP server carrying its test router."""

    router: FakeProviderServer


class FakeHandler(BaseHTTPRequestHandler):
    """Dispatches requests to the owning fake provider router."""

    def do_GET(self) -> None:
        # Routes one GET without logging query values.
        self._dispatch()

    def do_POST(self) -> None:
        # Routes one POST without logging request bodies.
        self._dispatch()

    def do_DELETE(self) -> None:
        # Routes one DELETE without logging request bodies.
        self._dispatch()

    def log_message(self, format: str, *args: object) -> None:
        # Standard HTTP logs could expose authorization URLs or request details.
        return

    def _dispatch(self) -> None:
        # Reads a bounded request body and serves the next scripted response.
        length = int(self.headers.get("Content-Length", "0"))
        body = self.rfile.read(min(length, 1_000_000))
        parsed = urlparse(self.path)
        record = RequestRecord(
            method=self.command,
            path=parsed.path,
            query=parsed.query,
            headers={key.lower(): value for key, value in self.headers.items()},
            body=body,
        )
        response = self.server.router.take(record)
        self.send_response(response.status)
        for key, value in response.headers.items():
            self.send_header(key, value)
        self.send_header("Content-Length", str(len(response.body)))
        self.end_headers()
        self.wfile.write(response.body)


class FakeProviderServer:
    """Threaded response queue that acts like three provider APIs."""

    def __init__(self) -> None:
        # The router is local-only and each response is explicitly queued by the test.
        self._server = FakeHTTPServer(("127.0.0.1", 0), FakeHandler)
        self._server.router = self
        self._responses: list[tuple[str, str, FakeResponse]] = []
        self.records: list[RequestRecord] = []
        self._lock = threading.Lock()
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)

    @property
    def origin(self) -> str:
        # Returns the loopback origin used by patched provider endpoints.
        return f"http://127.0.0.1:{self._server.server_port}"

    def start(self) -> None:
        # Starts the local provider process before any adapter request.
        self._thread.start()

    def stop(self) -> None:
        # Shuts down the local provider process after all tests.
        self._server.shutdown()
        self._server.server_close()
        self._thread.join(timeout=2)

    def enqueue(self, method: str, path: str, response: FakeResponse) -> None:
        # Appends one exact method/path response to the queue.
        with self._lock:
            self._responses.append((method, path, response))

    def take(self, record: RequestRecord) -> FakeResponse:
        # Removes the first matching response and records the request metadata.
        with self._lock:
            self.records.append(record)
            for index, (method, path, response) in enumerate(self._responses):
                if method == record.method and path == record.path:
                    self._responses.pop(index)
                    return response
        return FakeResponse.json({"error": "unexpected test request"}, status=500)


class FakeKeyring:
    """In-memory keyring backend with the same surface as keyring backends."""

    priority = 5.0

    def __init__(self) -> None:
        # Values are kept as serialized keyring strings.
        self.entries: dict[tuple[str, str], str] = {}

    def get_password(self, service: str, username: str) -> str | None:
        # Reads one fake keyring account.
        return self.entries.get((service, username))

    def set_password(self, service: str, username: str, password: str) -> None:
        # Writes one fake keyring account.
        self.entries[(service, username)] = password

    def delete_password(self, service: str, username: str) -> None:
        # Deletes one fake keyring account.
        self.entries.pop((service, username), None)


class BrowserHarness:
    """Completes local OAuth callbacks without opening a real browser."""

    def __init__(self) -> None:
        # Codes are consumed in authorization URL order.
        self.codes: list[str] = []

    def enqueue_code(self, code: str) -> None:
        # Queues the code the next callback flow should receive.
        self.codes.append(code)

    def open(self, url: str, new: int, autoraise: bool) -> bool:
        # Returns true and asynchronously sends a code to a loopback redirect.
        del new, autoraise
        query = parse_qs(urlparse(url).query)
        redirect = query.get("redirect_uri", [None])[0]
        state = query.get("state", [None])[0]
        if redirect is not None and state is not None and self.codes:
            code = self.codes.pop(0)
            threading.Thread(
                target=self._send_callback,
                args=(redirect, code, state),
                daemon=True,
            ).start()
        return True

    def _send_callback(self, redirect: str, code: str, state: str) -> None:
        # Waits for the callback server to enter its accept loop, then sends one code.
        time.sleep(0.05)
        httpx.get(f"{redirect}?{urlencode({'code': code, 'state': state})}", timeout=2)


class Workspace:
    """Isolated application context, keyring, paths, and fake provider server."""

    def __init__(self, server: FakeProviderServer) -> None:
        # Every test workspace has independent disk state and connection names.
        self.root = Path(tempfile.mkdtemp(prefix="vidbyte-connection-test-"))
        self.paths = VidbytePaths(
            config_root=self.root / "config",
            cache_root=self.root / "cache",
            state_root=self.root / "state",
            data_root=self.root / "data",
            legacy_root=self.root / "legacy",
        )
        self.keyring = FakeKeyring()
        self.stdout = io.StringIO()
        self.stderr = io.StringIO()
        environment = {
            "VIDBYTE_GITHUB_CLIENT_ID": "github-test-client",
            "VIDBYTE_SLACK_CLIENT_ID": "slack-test-client",
            "VIDBYTE_GOOGLE_CLIENT_SECRETS": str(self.root / "client.json"),
        }
        self.context = ApplicationContext(
            IOStreams(stdin=io.StringIO(), stdout=self.stdout, stderr=self.stderr),
            environment=environment,
            paths=self.paths,
        )
        config = ResolvedConfig(
            profile="default",
            api_url="https://vidbyte.test",
            output_format=OutputFormat.HUMAN,
            color=ColorMode.NEVER,
            request_timeout_seconds=3.0,
            provenance={field: ConfigSource.BUILT_IN for field in ConfigField},
        )
        self.context.configure(
            InvocationOptions(
                output_format=OutputFormat.HUMAN,
                profile="default",
                api_url=config.api_url,
                request_timeout_seconds=3.0,
                color=ColorMode.NEVER,
            ),
            config,
        )
        self.manager = ConnectionManager(self.context)
        self.manager._store = ConnectionStore(  # type: ignore[attr-defined]
            self.paths,
            ConnectionKeyringStore(self.keyring),  # type: ignore[arg-type]
        )
        self.context._connections = self.manager  # type: ignore[attr-defined]
        self.server = server

    def write_google_client(self, server: FakeProviderServer) -> None:
        # Writes a standard installed-app client document pointing at the fake OAuth server.
        payload = {
            "installed": {
                "client_id": "google-test-client",
                "client_secret": "google-test-secret",
                "auth_uri": "https://accounts.google.com/o/oauth2/v2/auth",
                "token_uri": f"{server.origin}/google/token",
            }
        }
        self.root.joinpath("client.json").write_text(json.dumps(payload), encoding="utf-8")

    def close(self) -> None:
        # Removes only this test's temporary directory.
        shutil.rmtree(self.root, ignore_errors=True)


class Results:
    """Prints one labeled result per test and a final count."""

    def __init__(self) -> None:
        # Counts are kept separate so a failing test cannot hide later failures.
        self.passed = 0
        self.failed = 0

    def check(self, name: str, condition: bool, detail: str = "") -> None:
        # Prints a machine-searchable label for each design-plan case.
        if condition:
            self.passed += 1
            print(f"PASS: {name}")
        else:
            self.failed += 1
            print(f"FAIL: {name}{f' - {detail}' if detail else ''}", file=sys.stderr)

    def raises(self, name: str, action: Any, code: CliErrorCode) -> None:
        # Asserts a typed failure without rendering its private cause.
        try:
            action()
        except CliError as error:
            self.check(name, error.code is code, f"got {error.code.value}")
        except Exception as error:
            self.check(name, False, f"unclassified {type(error).__name__}")
        else:
            self.check(name, False, "no failure")

    def validation_raises(self, name: str, action: Any) -> None:
        # Asserts that a pure Pydantic boundary rejects malformed model input.
        try:
            action()
        except ValidationError:
            self.check(name, True)
        except Exception as error:
            self.check(name, False, f"unclassified {type(error).__name__}")
        else:
            self.check(name, False, "no validation failure")

    def summary(self) -> int:
        # Returns a shell failure when any planned case failed.
        total = self.passed + self.failed
        print(f"\n{self.passed}/{total} tests passed")
        return 1 if self.failed else 0


class VerificationSuite:
    """Runs storage, OAuth, refresh, and bounded-read cases."""

    def __init__(self, results: Results, server: FakeProviderServer, browser: BrowserHarness) -> None:  # fmt: skip  # noqa: E501
        # Shared fixtures keep provider request assertions easy to inspect.
        self.results = results
        self.server = server
        self.browser = browser
        self.workspace = Workspace(server)
        self._original_open = webbrowser.open

    def run(self) -> None:
        # Every group is isolated by clearing queued responses and temporary workspaces.
        self.check_type_boundaries()
        self.check_keyring_and_metadata()
        self.check_github_login()
        self.check_google_login()
        self.check_slack_login()
        self.check_refresh_and_status()
        self.check_bounded_reads()
        self.check_state_rejection()
        self.check_keyring_unavailable()
        self.check_list_is_offline()
        self.check_logout()
        self.check_cli_command_wrapper()

    def close(self) -> None:
        # Restores process-global URL constants and browser behavior.
        webbrowser.open = self._original_open
        self.workspace.close()

    def check_type_boundaries(self) -> None:
        # [Edge Case] Validates token, limit, and identifier boundaries.
        r = self.results
        r.validation_raises(
            "[Edge Case] negative expiry is rejected",
            lambda: ConnectionToken(access_token=SecretStr("token"), expires_at=-1),
        )
        r.validation_raises(
            "[Hidden Assumption] string expiry is rejected",
            lambda: ConnectionToken(access_token=SecretStr("token"), expires_at="60"),
        )
        r.validation_raises(
            "[Edge Case] oversized access token is rejected",
            lambda: ConnectionToken(access_token=SecretStr("x" * 16_385)),
        )
        r.check(
            "[Edge Case] google CLI alias uses Drive provider",
            ConnectionProvider.from_cli("google") is ConnectionProvider.GOOGLE_DRIVE,
        )
        resource = ConnectionResource(
            provider=ConnectionProvider.SLACK,
            resource_type="channel",
            identifier="C123",
            limit=100,
        )
        r.check("[Edge Case] limit 100 is accepted", resource.limit == 100)
        r.validation_raises(
            "[Edge Case] limit 101 is rejected",
            lambda: ConnectionResource(
                provider=ConnectionProvider.SLACK,
                resource_type="channel",
                identifier="C123",
                limit=101,
            ),
        )

    def check_keyring_and_metadata(self) -> None:
        # [Silent Failure] A token write must read back and metadata must contain no secret.
        r = self.results
        token = ConnectionToken(
            access_token=SecretStr("secret-access"),
            refresh_token=SecretStr("secret-refresh"),
        )
        metadata = self.workspace.manager._metadata(  # type: ignore[attr-defined]
            "default",
            ConnectionProvider.GITHUB,
            "stored",
            type(
                "Auth",
                (),
                {
                    "token": token,
                    "identity": type(
                        "Identity",
                        (),
                        {
                            "account_id": "1",
                            "account_label": "octocat",
                            "workspace_id": None,
                            "workspace_label": None,
                            "scopes": ("read:user",),
                        },
                    )(),
                },
            )(),
        )
        self.workspace.manager._store.save("default", token, metadata)  # type: ignore[attr-defined]
        raw = self.workspace.paths.connection_metadata_file().read_text(encoding="utf-8")
        r.check("[Silent Failure] metadata excludes access token", "secret-access" not in raw)
        r.check("[Silent Failure] metadata excludes refresh token", "secret-refresh" not in raw)
        loaded, _ = self.workspace.manager._store.load(
            "default", ConnectionProvider.GITHUB, "stored"
        )  # type: ignore[attr-defined]
        r.check("[Edge Case] keyring round trip preserves both tokens", loaded == token)

    def check_github_login(self) -> None:
        # [Edge Case] Device flow handles authorization_pending then persists only after /user.
        server = self.server
        self._patch_github(server)
        server.enqueue(
            "POST",
            "/github/device",
            FakeResponse.json(
                {
                    "device_code": "device-secret",
                    "user_code": "ABCD-EFGH",
                    "verification_uri": f"{server.origin}/github/verify",
                    "expires_in": 10,
                    "interval": 1,
                }
            ),
        )
        server.enqueue(
            "POST", "/github/token", FakeResponse.json({"error": "authorization_pending"})
        )
        server.enqueue(
            "POST",
            "/github/token",
            FakeResponse.json(
                {
                    "access_token": "github-access",
                    "token_type": "bearer",
                    "scope": "read:user repo",
                }
            ),
        )
        server.enqueue("GET", "/github/user", FakeResponse.json({"id": 42, "login": "octocat"}))
        webbrowser.open = self.browser.open
        metadata = self.workspace.manager.login(ConnectionProvider.GITHUB, "work-github", (), None)
        self.results.check(
            "[Edge Case] GitHub device login saves verified identity",
            metadata.account_label == "octocat",
        )
        self.results.check(
            "[Silent Failure] GitHub sends bearer identity header",
            any(
                record.path == "/github/user"
                and record.headers.get("authorization") == "Bearer github-access"
                and record.headers.get("x-github-api-version") == "2022-11-28"
                for record in server.records
            ),
        )

    def check_google_login(self) -> None:
        # [Edge Case] Loopback PKCE flow exchanges the exact state/verifier-bearing callback.
        server = self.server
        self._patch_google(server)
        self.workspace.write_google_client(server)
        server.enqueue(
            "POST",
            "/google/token",
            FakeResponse.json(
                {
                    "access_token": "google-access",
                    "refresh_token": "google-refresh",
                    "token_type": "Bearer",
                    "expires_in": 3600,
                    "scope": "https://www.googleapis.com/auth/drive.readonly",
                }
            ),
        )
        server.enqueue(
            "GET",
            "/google/drive/v3/about",
            FakeResponse.json(
                {"user": {"permissionId": "perm-1", "emailAddress": "person@example.com"}}
            ),
        )
        self.browser.enqueue_code("google-code")
        webbrowser.open = self.browser.open
        metadata = self.workspace.manager.login(
            ConnectionProvider.GOOGLE_DRIVE,
            "work-drive",
            (),
            self.workspace.root / "client.json",
        )
        self.results.check(
            "[Edge Case] Google login saves Drive identity",
            metadata.account_label == "person@example.com",
        )
        token_request = next(record for record in server.records if record.path == "/google/token")
        body = token_request.body.decode()
        self.results.check(
            "[Silent Failure] Google token request includes PKCE verifier", "code_verifier=" in body
        )
        self.results.check(
            "[Silent Failure] Google token request uses authorization code", "google-code" in body
        )
        loaded, _ = self.workspace.manager._store.load(  # type: ignore[attr-defined]
            "default", ConnectionProvider.GOOGLE_DRIVE, "work-drive"
        )
        self.results.check(
            "[Silent Failure] Google client details stay in the keyring envelope",
            loaded.provider_data.get("client_id") == "google-test-client"
            and loaded.provider_data.get("client_secret") == "google-test-secret",
        )
        metadata_raw = self.workspace.paths.connection_metadata_file().read_text(encoding="utf-8")
        self.results.check(
            "[Silent Failure] Google client secret stays out of metadata",
            "google-test-secret" not in metadata_raw,
        )

    def check_slack_login(self) -> None:
        # [Edge Case] Slack PKCE user-scope flow verifies workspace identity.
        server = self.server
        self._patch_slack(server)
        server.enqueue(
            "POST",
            "/slack/token",
            FakeResponse.json(
                {
                    "ok": True,
                    "authed_user": {
                        "access_token": "slack-access",
                        "refresh_token": "slack-refresh",
                        "token_type": "bearer",
                        "expires_in": 3600,
                        "scope": "channels:history",
                    },
                }
            ),
        )
        server.enqueue(
            "POST",
            "/slack/auth.test",
            FakeResponse.json(
                {
                    "ok": True,
                    "user_id": "U1",
                    "team_id": "T1",
                    "user": "alice",
                    "team": "Acme",
                }
            ),
        )
        self.browser.enqueue_code("slack-code")
        webbrowser.open = self.browser.open
        metadata = self.workspace.manager.login(
            ConnectionProvider.SLACK,
            "work-slack",
            ("channels:history",),
            None,
        )
        self.results.check(
            "[Edge Case] Slack login saves workspace identity", metadata.workspace_label == "Acme"
        )
        token_request = next(record for record in server.records if record.path == "/slack/token")
        body = token_request.body.decode()
        self.results.check(
            "[Silent Failure] Slack token request includes PKCE verifier", "code_verifier=" in body
        )
        auth_request = next(
            record for record in server.records if record.path == "/slack/auth.test"
        )
        self.results.check(
            "[Silent Failure] Slack auth test sends bearer token",
            auth_request.headers.get("authorization") == "Bearer slack-access",
        )

    def check_refresh_and_status(self) -> None:
        # [Hidden Failure] Expiring tokens refresh once, preserve rotation, and verify identity.
        server = self.server
        token = ConnectionToken(
            access_token=SecretStr("expiring-access"),
            refresh_token=SecretStr("refresh-old"),
            expires_at=int(time.time()) + 1,
            provider_data={"scopes": "read:user repo"},
        )
        metadata = self.workspace.manager._store.metadata.read(
            "default", ConnectionProvider.GITHUB, "work-github"
        )  # type: ignore[attr-defined]
        assert metadata is not None
        replacement = metadata.model_copy(update={"expires_at": token.expires_at})
        self.workspace.manager._store.save("default", token, replacement)  # type: ignore[attr-defined]
        self._patch_github(server)
        server.enqueue(
            "POST",
            "/github/token",
            FakeResponse.json(
                {
                    "access_token": "github-refreshed",
                    "token_type": "bearer",
                    "expires_in": 3600,
                    "scope": "read:user repo",
                }
            ),
        )
        server.enqueue("GET", "/github/user", FakeResponse.json({"id": 42, "login": "octocat"}))
        server.enqueue("GET", "/github/user", FakeResponse.json({"id": 42, "login": "octocat"}))
        status = self.workspace.manager.status("default", ConnectionProvider.GITHUB, "work-github")
        self.results.check(
            "[Hidden Failure] status uses refreshed identity", status.account_id == "42"
        )
        loaded, _ = self.workspace.manager._store.load(
            "default", ConnectionProvider.GITHUB, "work-github"
        )  # type: ignore[attr-defined]
        self.results.check(
            "[Silent Failure] refreshed access token is persisted",
            loaded.access_secret() == "github-refreshed",
        )
        google_loaded, google_metadata = self.workspace.manager._store.load(  # type: ignore[attr-defined]
            "default", ConnectionProvider.GOOGLE_DRIVE, "work-drive"
        )
        google_expiring = google_loaded.model_copy(update={"expires_at": int(time.time()) + 1})
        assert google_metadata is not None
        google_replacement = google_metadata.model_copy(
            update={"expires_at": google_expiring.expires_at}
        )
        self.workspace.manager._store.save(  # type: ignore[attr-defined]
            "default", google_expiring, google_replacement
        )
        self.workspace.context.environment["VIDBYTE_GOOGLE_CLIENT_SECRETS"] = ""
        self._patch_google(server)
        server.enqueue(
            "POST",
            "/google/token",
            FakeResponse.json(
                {
                    "access_token": "google-refreshed",
                    "token_type": "Bearer",
                    "expires_in": 3600,
                    "scope": "https://www.googleapis.com/auth/drive.readonly",
                }
            ),
        )
        server.enqueue(
            "GET",
            "/google/drive/v3/about",
            FakeResponse.json(
                {"user": {"permissionId": "perm-1", "emailAddress": "person@example.com"}}
            ),
        )
        server.enqueue(
            "GET",
            "/google/drive/v3/about",
            FakeResponse.json(
                {"user": {"permissionId": "perm-1", "emailAddress": "person@example.com"}}
            ),
        )
        google_status = self.workspace.manager.status(
            "default", ConnectionProvider.GOOGLE_DRIVE, "work-drive"
        )
        self.results.check(
            "[Hidden Assumption] Google refresh works without the original client JSON path",
            google_status.account_id == "perm-1",
        )

    def check_bounded_reads(self) -> None:
        # [Silent Failure] Each provider read uses the exact resource path and bounded inputs.
        server = self.server
        self._patch_github(server)
        server.enqueue(
            "GET", "/github/repos/acme/api", FakeResponse.json({"full_name": "acme/api"})
        )
        github_read = self.workspace.manager.read(
            "default",
            ConnectionProvider.GITHUB,
            "work-github",
            ConnectionResource(
                provider=ConnectionProvider.GITHUB, resource_type="repo", identifier="acme/api"
            ),
        )
        self.results.check(
            "[Silent Failure] GitHub repository read returns selected data",
            github_read.data["full_name"] == "acme/api",
        )
        self._patch_slack(server)
        server.enqueue(
            "GET",
            "/slack/history",
            FakeResponse.json({"ok": True, "messages": [{"text": "hello"}]}),
        )
        slack_read = self.workspace.manager.read(
            "default",
            ConnectionProvider.SLACK,
            "work-slack",
            ConnectionResource(
                provider=ConnectionProvider.SLACK,
                resource_type="channel",
                identifier="C123",
                limit=25,
            ),
        )
        self.results.check(
            "[Silent Failure] Slack history uses requested limit",
            slack_read.data["messages"] == [{"text": "hello"}]
            and any(
                record.path == "/slack/history" and "limit=25" in record.query
                for record in server.records
            ),
        )
        self._patch_google(server)
        server.enqueue(
            "GET",
            "/google/drive/v3/files/file-1",
            FakeResponse.json(
                {
                    "id": "file-1",
                    "name": "notes",
                    "mimeType": "text/plain",
                }
            ),
        )
        server.enqueue(
            "GET", "/google/drive/v3/files/file-1", FakeResponse(status=200, body=b"hello")
        )
        google_read = self.workspace.manager.read(
            "default",
            ConnectionProvider.GOOGLE_DRIVE,
            "work-drive",
            ConnectionResource(
                provider=ConnectionProvider.GOOGLE_DRIVE, resource_type="file", identifier="file-1"
            ),
        )
        self.results.check(
            "[Silent Failure] Drive read returns content", google_read.data["content"] == "hello"
        )

    def check_state_rejection(self) -> None:
        # [Hidden Failure] A mismatched callback state never reaches token exchange or storage.
        server = self.server
        self._patch_google(server)
        self.workspace.write_google_client(server)
        self.browser.enqueue_code("wrong-state-code")
        original_open = webbrowser.open

        def wrong_state(url: str, new: int = 0, autoraise: bool = True) -> bool:
            # Sends a callback with a forged state while preserving the redirect endpoint.
            query = parse_qs(urlparse(url).query)
            redirect = query.get("redirect_uri", [None])[0]
            if redirect:
                threading.Thread(
                    target=self._send_wrong_state,
                    args=(redirect,),
                    daemon=True,
                ).start()
            return True

        webbrowser.open = wrong_state
        before = len(self.workspace.manager.list("default"))
        self.results.raises(
            "[Hidden Failure] wrong OAuth state is rejected",
            lambda: self.workspace.manager.login(
                ConnectionProvider.GOOGLE_DRIVE,
                "forged",
                (),
                self.workspace.root / "client.json",
            ),
            CliErrorCode.CONNECTION_OAUTH_STATE_INVALID,
        )
        self.results.check(
            "[Hidden Failure] forged callback does not add metadata",
            len(self.workspace.manager.list("default")) == before,
        )
        webbrowser.open = original_open

    def _send_wrong_state(self, redirect: str) -> None:
        # Sends a callback whose state cannot have been generated by this invocation.
        time.sleep(0.05)
        httpx.get(f"{redirect}?code=forged&state=not-the-generated-state", timeout=2)

    def check_keyring_unavailable(self) -> None:
        # [Hidden Assumption] OAuth tokens have no plaintext fallback when keyring is unavailable.
        class UnavailableKeyring:
            priority = 0.0

            def get_password(self, service: str, username: str) -> None:
                # Represents a null backend.
                return None

            def set_password(self, service: str, username: str, password: str) -> None:
                # A null backend cannot accept writes.
                return

            def delete_password(self, service: str, username: str) -> None:
                # A null backend has nothing to delete.
                return

        paths = self.workspace.paths
        before_metadata = (
            paths.connection_metadata_file().read_bytes()
            if paths.connection_metadata_file().exists()
            else None
        )
        store = ConnectionStore(paths, ConnectionKeyringStore(UnavailableKeyring()))  # type: ignore[arg-type]
        self.results.raises(
            "[Hidden Assumption] unavailable keyring blocks connection storage",
            lambda: store.save(
                "default",
                ConnectionToken(access_token=SecretStr("token")),
                self.workspace.manager._store.metadata.list("default")[0],  # type: ignore[attr-defined]
            ),
            CliErrorCode.CONNECTION_STORE_UNAVAILABLE,
        )
        after_metadata = (
            paths.connection_metadata_file().read_bytes()
            if paths.connection_metadata_file().exists()
            else None
        )
        self.results.check(
            "[Hidden Assumption] unavailable keyring changes no metadata",
            before_metadata == after_metadata,
        )

    def check_list_is_offline(self) -> None:
        # [Silent Failure] Listing metadata must not call a provider or unlock a keyring.
        before = len(self.server.records)
        entries = self.workspace.manager.list("default")
        self.results.check("[Silent Failure] list returns saved connections", bool(entries))
        self.results.check(
            "[Silent Failure] list makes no network call", len(self.server.records) == before
        )

    def check_cli_command_wrapper(self) -> None:
        # [Silent Failure] The real Click command emits one secret-free JSON result document.
        self.workspace.stdout.seek(0)
        self.workspace.stdout.truncate(0)
        status = CliApplication(self.workspace.context).run(
            ["vidbyte-cli", "--format", "json", "connections", "list"]
        )
        raw = self.workspace.stdout.getvalue()
        try:
            payload = json.loads(raw)
        except ValueError:
            payload = {}
        self.results.check("[Silent Failure] list command returns success", status == 0)
        self.results.check(
            "[Silent Failure] list command returns one result envelope",
            payload.get("kind") == "connections.list" and raw.count("\n") <= 1,
        )
        self.results.check(
            "[Silent Failure] list command output excludes bearer credentials",
            "github-access" not in raw and "google-access" not in raw and "slack-access" not in raw,
        )

    def check_logout(self) -> None:
        # [Edge Case] Logout revokes the Slack token and removes both local storage halves.
        self._patch_slack(self.server)
        self.server.enqueue("POST", "/slack/revoke", FakeResponse.json({"ok": True}))
        self.workspace.manager.logout_by_name("default", "work-slack")
        metadata = self.workspace.manager._store.metadata.read(  # type: ignore[attr-defined]
            "default", ConnectionProvider.SLACK, "work-slack"
        )
        self.results.check("[Edge Case] logout removes connection metadata", metadata is None)
        self.results.check(
            "[Silent Failure] logout removes keyring token",
            not any(
                "@slack@work-slack" in account for _, account in self.workspace.keyring.entries
            ),
        )
        self.results.check(
            "[Silent Failure] logout calls provider revocation",
            any(record.path == "/slack/revoke" for record in self.server.records),
        )

    def _patch_github(self, server: FakeProviderServer) -> None:
        # Redirects GitHub constants to this test server.
        github._GITHUB_DEVICE_URL = f"{server.origin}/github/device"
        github._GITHUB_TOKEN_URL = f"{server.origin}/github/token"
        github._GITHUB_API = f"{server.origin}/github"

    def _patch_google(self, server: FakeProviderServer) -> None:
        # Redirects Drive API and revoke-independent OAuth endpoints to this test server.
        google_drive._GOOGLE_AUTH_DEFAULT = "https://accounts.google.com/o/oauth2/v2/auth"
        google_drive._GOOGLE_TOKEN_DEFAULT = f"{server.origin}/google/token"
        google_drive._GOOGLE_DRIVE_API = f"{server.origin}/google/drive/v3"
        google_drive._GOOGLE_REVOKE_URL = f"{server.origin}/google/revoke"

    def _patch_slack(self, server: FakeProviderServer) -> None:
        # Redirects Slack OAuth and Web API constants to this test server.
        slack._SLACK_AUTHORIZE_URL = f"{server.origin}/slack/authorize"
        slack._SLACK_TOKEN_URL = f"{server.origin}/slack/token"
        slack._SLACK_AUTH_TEST_URL = f"{server.origin}/slack/auth.test"
        slack._SLACK_HISTORY_URL = f"{server.origin}/slack/history"
        slack._SLACK_REVOKE_URL = f"{server.origin}/slack/revoke"


def main() -> int:
    # Runs the complete offline verification suite and always closes its local resources.
    results = Results()
    server = FakeProviderServer()
    browser = BrowserHarness()
    suite = VerificationSuite(results, server, browser)
    server.start()
    try:
        suite.run()
    finally:
        suite.close()
        server.stop()
    return results.summary()


if __name__ == "__main__":
    raise SystemExit(main())
