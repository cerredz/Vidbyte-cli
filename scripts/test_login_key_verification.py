"""Verification for login's verify-before-persist path and the whoami identity check.

Run with `python scripts/test_login_key_verification.py`. Every case drives the real
`ApiClient` over a real socket against a loopback HTTP server, which is possible because
`ApiOrigin` permits cleartext HTTP on loopback origins. Nothing here reaches the internet and
nothing is added to `src/` to make it testable.

The whole point of these cases is the negative space: a rejected key, an unreachable host, and
an undecodable answer must each leave the credential stores exactly as they were.
"""

from __future__ import annotations

import json
import os

# The null backend must be selected before `keyring` is imported anywhere, so the suites that
# assert "nothing was written" cannot touch a developer's real keychain.
os.environ["PYTHON_KEYRING_BACKEND"] = "keyring.backends.null.Keyring"

import io  # noqa: E402
import shutil  # noqa: E402
import sys  # noqa: E402
import tempfile  # noqa: E402
import threading  # noqa: E402
import time  # noqa: E402
from collections.abc import Callable  # noqa: E402
from dataclasses import dataclass, field  # noqa: E402
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer  # noqa: E402
from pathlib import Path  # noqa: E402
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from vidbyte_cli.commands.auth.login import LoginCommand  # noqa: E402
from vidbyte_cli.commands.auth.whoami import WhoamiCommand  # noqa: E402
from vidbyte_cli.lib.api.client import ApiClient  # noqa: E402
from vidbyte_cli.lib.api.endpoints.auth import AUTH_VALIDATE_PATH  # noqa: E402
from vidbyte_cli.lib.auth.credentials import Credentials, CredentialStore  # noqa: E402
from vidbyte_cli.lib.auth.keyring_store import KeyringCredentialStore  # noqa: E402
from vidbyte_cli.lib.auth.verifier import ApiCredentialVerifier  # noqa: E402
from vidbyte_cli.lib.config.models import (  # noqa: E402
    ConfigField,
    ConfigSource,
    ResolvedConfig,
)
from vidbyte_cli.lib.config.paths import VidbytePaths  # noqa: E402
from vidbyte_cli.lib.errors.cli_error import CliError  # noqa: E402
from vidbyte_cli.lib.errors.codes import CliErrorCode, ExitCode  # noqa: E402
from vidbyte_cli.lib.io import IOStreams  # noqa: E402
from vidbyte_cli.lib.output.formats import ColorMode, OutputFormat  # noqa: E402
from vidbyte_cli.lib.runtime.context import ApplicationContext, InvocationOptions  # noqa: E402
from vidbyte_cli.types.api import KeyIdentity  # noqa: E402

LIVE_KEY = "vb_live_" + "a" * 32
OTHER_KEY = "vb_live_" + "b" * 32
VALID_BODY = {
    "success": True,
    "session_token": "sess_" + "z" * 40,
    "username": "user_abc123",
    "email": "user_abc123",
    "account_tier": "free",
}


@dataclass
class ScriptedResponse:
    """One canned reply the fake backend serves for the next request."""

    status: int = 200
    body: bytes = b""
    content_type: str | None = "application/json"
    headers: dict[str, str] = field(default_factory=dict)
    delay_seconds: float = 0.0

    @classmethod
    def json_body(cls, payload: object, status: int = 200, **extra: str) -> ScriptedResponse:
        # Serializes a payload and tags it as JSON, which is the common case.
        return cls(status=status, body=json.dumps(payload).encode(), headers=dict(extra))


@dataclass
class RecordedRequest:
    """What the fake backend actually received, for assertions about the wire."""

    method: str
    path: str
    headers: dict[str, str]
    body: bytes


class FakeBackend:
    """A loopback HTTP server that serves scripted replies and records what it received."""

    def __init__(self) -> None:
        self.responses: list[ScriptedResponse] = []
        self.requests: list[RecordedRequest] = []
        self._server = self._build_server()
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()

    @property
    def origin(self) -> str:
        # ApiOrigin allows cleartext HTTP only for loopback, which is exactly this case.
        return f"http://127.0.0.1:{self._server.server_address[1]}"

    def expect(self, response: ScriptedResponse) -> FakeBackend:
        # Queues one reply; requests beyond the queue receive a 200 with an empty body.
        self.responses.append(response)
        return self

    def reset(self) -> None:
        self.responses.clear()
        self.requests.clear()

    def shutdown(self) -> None:
        self._server.shutdown()
        self._server.server_close()

    def _build_server(self) -> ThreadingHTTPServer:
        # handle_error is silenced because the timeout cases deliberately abandon a socket the
        # handler thread is still writing to, and that traceback is expected noise.
        class QuietServer(ThreadingHTTPServer):
            def handle_error(self, request: object, client_address: object) -> None:
                return

        return QuietServer(("127.0.0.1", 0), self._build_handler())

    def _build_handler(self) -> type[BaseHTTPRequestHandler]:
        # Binds the handler class to this instance's queues without module-level state.
        backend = self

        class Handler(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def do_POST(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler's naming
                length = int(self.headers.get("content-length") or 0)
                backend.requests.append(
                    RecordedRequest(
                        method=self.command,
                        path=self.path,
                        headers={key.lower(): value for key, value in self.headers.items()},
                        body=self.rfile.read(length) if length else b"",
                    )
                )
                self._reply(
                    backend.responses.pop(0) if backend.responses else ScriptedResponse(body=b"{}")
                )

            def do_GET(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler's naming
                self.do_POST()

            def _reply(self, response: ScriptedResponse) -> None:
                if response.delay_seconds:
                    time.sleep(response.delay_seconds)
                self.send_response(response.status)
                if response.content_type is not None:
                    self.send_header("Content-Type", response.content_type)
                for key, value in response.headers.items():
                    self.send_header(key, value)
                self.send_header("Content-Length", str(len(response.body)))
                self.end_headers()
                self.wfile.write(response.body)

            def log_message(self, format: str, *args: object) -> None:
                return

        return Handler


class FakeKeyringBackend:
    """An in-memory keyring backend, so the keyring write path runs without a real keychain."""

    def __init__(self, priority: float = 5.0) -> None:
        self.priority = priority
        self.entries: dict[tuple[str, str], str] = {}

    def get_password(self, service: str, username: str) -> str | None:
        return self.entries.get((service, username))

    def set_password(self, service: str, username: str, password: str) -> None:
        self.entries[(service, username)] = password

    def delete_password(self, service: str, username: str) -> None:
        self.entries.pop((service, username), None)


class Workspace:
    """One isolated temp state tree plus the config that points at the fake backend."""

    def __init__(self, api_url: str, timeout_seconds: float = 10.0) -> None:
        self.root = Path(tempfile.mkdtemp(prefix="vidbyte-cli-verify-"))
        self.paths = VidbytePaths(
            config_root=self.root / "config",
            cache_root=self.root / "cache",
            state_root=self.root / "state",
            data_root=self.root / "data",
            legacy_root=self.root / "legacy",
        )
        self.config = ResolvedConfig(
            profile="default",
            api_url=api_url,
            output_format=OutputFormat.HUMAN,
            color=ColorMode.NEVER,
            request_timeout_seconds=timeout_seconds,
            provenance={field: ConfigSource.BUILT_IN for field in ConfigField},
        )
        self.keyring = FakeKeyringBackend()
        self.stdout = io.StringIO()
        self.stderr = io.StringIO()

    def store(self) -> CredentialStore:
        # A real CredentialStore over an in-memory keyring and this workspace's temp files.
        return CredentialStore(
            keyring_store=KeyringCredentialStore(backend=self.keyring),
            paths=self.paths,
        )

    def context(
        self, stdin: str = "", environment: dict[str, str] | None = None
    ) -> ApplicationContext:
        # Builds a real ApplicationContext; the credential store is assigned directly because
        # the context has no injection point for it and a real keyring must never be touched.
        streams = IOStreams(stdin=io.StringIO(stdin), stdout=self.stdout, stderr=self.stderr)
        context = ApplicationContext(
            streams,
            environment=environment or {},
            paths=self.paths,
            verifier_factory=ApiCredentialVerifier,
        )
        context.configure(
            InvocationOptions(
                output_format=OutputFormat.HUMAN,
                api_url=self.config.api_url,
                request_timeout_seconds=self.config.request_timeout_seconds,
                color=ColorMode.NEVER,
            ),
            self.config,
        )
        context._credential_store = self.store()
        return context

    def stored_key(self) -> str | None:
        # Reads back through the real store, so a write that silently did nothing is visible.
        credential = self.store().read(self.config.profile, self.config.api_url)
        return credential.secret_value() if credential is not None else None

    def credential_file_exists(self) -> bool:
        return self.paths.credentials_file().exists()

    def cleanup(self) -> None:
        shutil.rmtree(self.root, ignore_errors=True)


class Results:
    """Collects one PASS or FAIL line per case and decides the process status."""

    def __init__(self) -> None:
        self.passed = 0
        self.failed = 0

    def check(self, name: str, condition: bool, detail: str = "") -> None:  # noqa: FBT001
        # Records one assertion outcome and prints it immediately, so a hang is locatable.
        if condition:
            self.passed += 1
            print(f"PASS: {name}")
            return
        self.failed += 1
        print(f"FAIL: {name}{f' - {detail}' if detail else ''}", file=sys.stderr)

    def raises(
        self, name: str, action: Callable[[], Any], code: CliErrorCode, exit_code: ExitCode
    ) -> None:
        # Asserts an action fails with an exact code and status, never merely that it raised.
        try:
            action()
        except CliError as error:
            matched = error.code is code and error.exit_code == int(exit_code)
            detail = f"got {error.code.value}/{error.exit_code}, want {code.value}/{int(exit_code)}"
            self.check(name, matched, detail)
        except Exception as error:  # noqa: BLE001 - an unclassified escape is itself the defect
            self.check(name, False, f"unclassified {type(error).__name__}")
        else:
            self.check(name, False, "no failure was raised")

    def summary(self) -> int:
        total = self.passed + self.failed
        print(f"\n{self.passed}/{total} tests passed")
        return 1 if self.failed else 0


class VerificationSuite:
    """Every case from the design doc's testing plan, grouped by the behavior it protects."""

    def __init__(self, results: Results) -> None:
        self.results = results
        self.backend = FakeBackend()

    def run(self) -> None:
        # Each group leaves the backend queues empty so ordering between groups cannot matter.
        for group in (
            self.check_path_safety,
            self.check_wire_format,
            self.check_transport_failures,
            self.check_response_decoding,
            self.check_status_classification,
            self.check_verifier,
            self.check_whoami,
            self.check_login_persistence,
        ):
            group()
            self.backend.reset()

    def _client(self, workspace: Workspace, key: str = LIVE_KEY) -> ApiClient:
        return ApiClient(workspace.config, Credentials.from_value(key))

    def _workspace(self, timeout_seconds: float = 10.0) -> Workspace:
        return Workspace(self.backend.origin, timeout_seconds)

    def check_path_safety(self) -> None:
        # A path that can retarget the request would carry the API key to a foreign host.
        workspace = self._workspace()
        client = self._client(workspace)
        results = self.results
        results.check(
            "_url joins a relative path onto the origin without duplication",
            client._url("/api/skills/auth/validate")
            == f"{self.backend.origin}/api/skills/auth/validate",
        )
        for label, path in (
            ("an absolute https URL", "https://evil.test/steal"),
            ("a protocol-relative path", "//evil.test/steal"),
            ("a path with no leading slash", "api/skills/auth/validate"),
            ("an embedded scheme", "/redirect?to=https://evil.test"),
        ):
            results.raises(
                f"_url rejects {label}",
                lambda p=path: client._url(p),
                CliErrorCode.INTERNAL_ERROR,
                ExitCode.SOFTWARE,
            )
        ported = Workspace("http://127.0.0.1:9")
        results.check(
            "_url preserves a non-default port from the configured origin",
            ApiClient(ported.config, Credentials.from_value(LIVE_KEY))._url("/x")
            == "http://127.0.0.1:9/x",
        )
        ported.cleanup()
        workspace.cleanup()

    def check_wire_format(self) -> None:
        # What actually leaves the machine: one header, no body, no query string.
        workspace = self._workspace()
        self.backend.expect(ScriptedResponse.json_body(VALID_BODY))
        self._client(workspace).post_direct(AUTH_VALIDATE_PATH, KeyIdentity)
        sent = self.backend.requests[-1]
        results = self.results
        results.check("the key is sent in x-api-key", sent.headers.get("x-api-key") == LIVE_KEY)
        results.check(
            "the key appears in exactly one header",
            [value for value in sent.headers.values() if LIVE_KEY in value] == [LIVE_KEY],
        )
        results.check("no Authorization header is sent", "authorization" not in sent.headers)
        results.check("the request carries no body", sent.body == b"")
        results.check("the request carries no query string", "?" not in sent.path)
        results.check("the request path is the validate route", sent.path == AUTH_VALIDATE_PATH)
        results.check("the request is a POST", sent.method == "POST")
        workspace.cleanup()

    def check_transport_failures(self) -> None:
        # A network problem must never read as a verdict on the key.
        results = self.results
        closed = Workspace("http://127.0.0.1:9", timeout_seconds=2.0)
        results.raises(
            "a closed port raises ApiUnreachable, not a credential failure",
            lambda: self._client(closed).post_direct(AUTH_VALIDATE_PATH, KeyIdentity),
            CliErrorCode.API_UNAVAILABLE,
            ExitCode.OPERATIONAL_FAILURE,
        )
        closed.cleanup()
        slow = self._workspace(timeout_seconds=1.0)
        self.backend.expect(ScriptedResponse(body=b"{}", delay_seconds=3.0))
        results.raises(
            "a server that never answers in time raises ApiUnreachable",
            lambda: self._client(slow).post_direct(AUTH_VALIDATE_PATH, KeyIdentity),
            CliErrorCode.API_UNAVAILABLE,
            ExitCode.OPERATIONAL_FAILURE,
        )
        slow.cleanup()

    def check_response_decoding(self) -> None:
        # A success status is not an approval until the body proves it.
        results = self.results
        workspace = self._workspace()
        self.backend.expect(ScriptedResponse.json_body(VALID_BODY))
        identity = self._client(workspace).post_direct(AUTH_VALIDATE_PATH, KeyIdentity)
        results.check(
            "a well-formed 200 decodes to KeyIdentity", identity.username == "user_abc123"
        )
        results.check("account_tier is carried through", identity.account_tier == "free")
        results.check(
            "session_token and email are not modelled",
            not hasattr(identity, "session_token") and not hasattr(identity, "email"),
        )
        oversized = json.dumps({**VALID_BODY, "padding": "p" * 1_100_000}).encode()
        undecodable = (
            ("an empty body", ScriptedResponse(body=b"")),
            ("a 204 with no content", ScriptedResponse(status=204, body=b"")),
            ("content-type text/html", ScriptedResponse(body=b"<html/>", content_type="text/html")),
            ("a missing content-type", ScriptedResponse(body=b"{}", content_type=None)),
            ("malformed JSON", ScriptedResponse(body=b"{not json")),
            ("a JSON array instead of an object", ScriptedResponse(body=b"[]")),
            ("a body over the size bound", ScriptedResponse(body=oversized)),
            ("a missing username", ScriptedResponse.json_body({"success": True, "x": 1})),
            (
                "an empty username",
                ScriptedResponse.json_body({**VALID_BODY, "username": ""}),
            ),
        )
        for label, response in undecodable:
            self.backend.expect(response)
            results.raises(
                f"{label} raises ApiProtocolError",
                lambda: self._client(workspace).post_direct(AUTH_VALIDATE_PATH, KeyIdentity),
                CliErrorCode.API_PROTOCOL_ERROR,
                ExitCode.OPERATIONAL_FAILURE,
            )
        self.backend.expect(
            ScriptedResponse(
                body=json.dumps(VALID_BODY).encode(),
                content_type="application/json; charset=utf-8",
            )
        )
        results.check(
            "a parameterized JSON media type is accepted",
            self._client(workspace).post_direct(AUTH_VALIDATE_PATH, KeyIdentity).success,
        )
        # Padded to land on the bound exactly, so the boundary is tested rather than approached.
        empty_pad = json.dumps({**VALID_BODY, "pad": ""}).encode()
        at_bound = json.dumps({**VALID_BODY, "pad": "x" * (1_048_576 - len(empty_pad))}).encode()
        self.backend.expect(ScriptedResponse(body=at_bound))
        results.check(
            "a body at exactly the size bound is accepted",
            len(at_bound) == 1_048_576
            and self._client(workspace).post_direct(AUTH_VALIDATE_PATH, KeyIdentity).success,
        )
        workspace.cleanup()

    def check_status_classification(self) -> None:
        # Each status must reach the failure whose wording tells the user the right thing.
        results = self.results
        workspace = self._workspace()
        cases = (
            (401, CliErrorCode.AUTH_REQUIRED, ExitCode.AUTHENTICATION),
            (403, CliErrorCode.AUTH_REQUIRED, ExitCode.AUTHENTICATION),
            (400, CliErrorCode.INVALID_ARGUMENT, ExitCode.USAGE),
            (409, CliErrorCode.INVALID_ARGUMENT, ExitCode.USAGE),
            (422, CliErrorCode.INVALID_ARGUMENT, ExitCode.USAGE),
            (404, CliErrorCode.API_UNAVAILABLE, ExitCode.OPERATIONAL_FAILURE),
            (429, CliErrorCode.API_UNAVAILABLE, ExitCode.OPERATIONAL_FAILURE),
            (500, CliErrorCode.API_UNAVAILABLE, ExitCode.OPERATIONAL_FAILURE),
            (503, CliErrorCode.API_UNAVAILABLE, ExitCode.OPERATIONAL_FAILURE),
            (418, CliErrorCode.OPERATION_FAILED, ExitCode.OPERATIONAL_FAILURE),
            (302, CliErrorCode.OPERATION_FAILED, ExitCode.OPERATIONAL_FAILURE),
        )
        for status, code, exit_code in cases:
            self.backend.expect(ScriptedResponse.json_body({"error": True}, status=status))
            results.raises(
                f"status {status} maps to {code.value}",
                lambda: self._client(workspace).post_direct(AUTH_VALIDATE_PATH, KeyIdentity),
                code,
                exit_code,
            )
        # The redirect must target the fake backend itself. Pointing it at a dead port would
        # make this pass even if redirects were followed, because the follow-up would fail on
        # its own — the assertion has to be that no second request was made at all.
        self.backend.expect(
            ScriptedResponse.json_body(
                {"error": True}, status=302, Location=f"{self.backend.origin}/followed"
            )
        ).expect(ScriptedResponse.json_body(VALID_BODY))
        before = len(self.backend.requests)
        try:
            self._client(workspace).post_direct(AUTH_VALIDATE_PATH, KeyIdentity)
        except CliError:
            pass
        results.check(
            "a redirect is not followed",
            len(self.backend.requests) == before + 1,
            f"{len(self.backend.requests) - before} requests were made",
        )
        # The follow-up reply goes unclaimed when the guard holds, so drop it before the
        # next case rather than letting it answer someone else's request.
        self.backend.responses.clear()
        self.backend.expect(
            ScriptedResponse.json_body(
                {"error": True}, status=429, **{"Retry-After": "42", "X-Request-Id": "req_xyz"}
            )
        )
        captured = self._capture(workspace)
        results.check(
            "a 429 surfaces the Retry-After value in its hint",
            captured is not None and "42" in (captured.hint or ""),
        )
        results.check(
            "a request id from the response reaches the failure",
            captured is not None and captured.request_id == "req_xyz",
        )
        results.check(
            "the 429 failure is marked retryable",
            captured is not None and captured.retryable,
        )
        self.backend.expect(
            ScriptedResponse.json_body(
                {"error": True}, status=429, **{"Retry-After": "Wed, 21 Oct"}
            )
        )
        captured = self._capture(workspace)
        results.check(
            "a non-numeric Retry-After is ignored rather than crashing",
            captured is not None and captured.code is CliErrorCode.API_UNAVAILABLE,
        )
        self.backend.expect(
            ScriptedResponse.json_body({"error": True}, status=429, **{"X-Request-Id": "r" * 200})
        )
        captured = self._capture(workspace)
        results.check(
            "an oversized request id is dropped",
            captured is not None and captured.request_id is None,
        )
        self.backend.expect(
            ScriptedResponse.json_body({"error": True, "detail": LIVE_KEY}, status=401)
        )
        captured = self._capture(workspace)
        rendered = " ".join(
            str(part)
            for part in (
                captured.message,
                captured.description,
                captured.trace,
                captured.hint,
                captured.request_id,
            )
            if captured is not None
        )
        results.check(
            "no part of the response body reaches the rendered failure",
            LIVE_KEY not in rendered,
        )
        workspace.cleanup()

    def _capture(self, workspace: Workspace) -> CliError | None:
        # Runs one request and returns the failure it raised, for field-level assertions.
        try:
            self._client(workspace).post_direct(AUTH_VALIDATE_PATH, KeyIdentity)
        except CliError as error:
            return error
        return None

    def check_verifier(self) -> None:
        # `success: false` on a 200 is the response most likely to be trusted wrongly.
        results = self.results
        workspace = self._workspace()
        verifier = ApiCredentialVerifier()
        credentials = Credentials.from_value(LIVE_KEY)
        self.backend.expect(ScriptedResponse.json_body(VALID_BODY))
        results.check(
            "a valid key verifies and returns its identity",
            verifier.verify(credentials, workspace.config).username == "user_abc123",
        )
        self.backend.expect(ScriptedResponse.json_body({**VALID_BODY, "success": False}))
        results.raises(
            "a 200 that declares success false raises ApiProtocolError",
            lambda: verifier.verify(credentials, workspace.config),
            CliErrorCode.API_PROTOCOL_ERROR,
            ExitCode.OPERATIONAL_FAILURE,
        )
        workspace.cleanup()

    def check_whoami(self) -> None:
        # whoami must be silent on the network when it has nothing to ask about.
        results = self.results
        empty = self._workspace()
        before = len(self.backend.requests)
        results.raises(
            "whoami with no stored credential raises AuthenticationRequired",
            lambda: WhoamiCommand().execute(empty.context()),
            CliErrorCode.AUTH_REQUIRED,
            ExitCode.AUTHENTICATION,
        )
        results.check(
            "whoami makes no network call when there is no credential",
            len(self.backend.requests) == before,
        )
        empty.cleanup()

        stored = self._workspace()
        stored.store().write(
            Credentials.from_value(LIVE_KEY), stored.config.profile, stored.config.api_url
        )
        self.backend.expect(ScriptedResponse.json_body(VALID_BODY))
        WhoamiCommand().execute(stored.context())
        printed = stored.stdout.getvalue()
        results.check("whoami prints the username", "user_abc123" in printed)
        results.check("whoami prints the account tier", "free" in printed)
        results.check("whoami never prints the API key", LIVE_KEY not in printed)
        results.check(
            "whoami never prints the session token",
            VALID_BODY["session_token"] not in printed,
        )
        results.check(
            "whoami reports the keyring as the credential source",
            "keyring" in printed,
        )
        stored.cleanup()

        overridden = self._workspace()
        overridden.store().write(
            Credentials.from_value(LIVE_KEY), overridden.config.profile, overridden.config.api_url
        )
        self.backend.expect(ScriptedResponse.json_body(VALID_BODY))
        WhoamiCommand().execute(overridden.context(environment={"VIDBYTE_API_KEY": OTHER_KEY}))
        sent = self.backend.requests[-1]
        results.check(
            "whoami verifies VIDBYTE_API_KEY in preference to the keyring",
            sent.headers.get("x-api-key") == OTHER_KEY,
        )
        results.check(
            "whoami reports the environment as the credential source",
            "environment" in overridden.stdout.getvalue(),
        )
        overridden.cleanup()

    def check_login_persistence(self) -> None:
        # The core requirement: a key reaches storage only after the server accepts it.
        results = self.results
        accepted = self._workspace()
        self.backend.expect(ScriptedResponse.json_body(VALID_BODY))
        LoginCommand().execute(accepted.context(stdin=LIVE_KEY), True, False)
        results.check("an accepted key is stored", accepted.stored_key() == LIVE_KEY)
        results.check(
            "login sends exactly one request",
            len(self.backend.requests) == 1,
            f"{len(self.backend.requests)} requests were made",
        )
        accepted.cleanup()

        rejections = (
            ("a rejected key", ScriptedResponse.json_body({"error": True}, status=401)),
            ("a server error", ScriptedResponse.json_body({"error": True}, status=500)),
            ("a rate limit", ScriptedResponse.json_body({"error": True}, status=429)),
            ("an undecodable 200", ScriptedResponse(body=b"<html/>", content_type="text/html")),
            (
                "a 200 declaring failure",
                ScriptedResponse.json_body({**VALID_BODY, "success": False}),
            ),
        )
        for label, response in rejections:
            workspace = self._workspace()
            self.backend.expect(response)
            try:
                LoginCommand().execute(workspace.context(stdin=LIVE_KEY), True, False)
            except CliError:
                pass
            results.check(
                f"{label} writes nothing to the keyring",
                workspace.stored_key() is None,
            )
            results.check(
                f"{label} writes no fallback credential file",
                not workspace.credential_file_exists(),
            )
            workspace.cleanup()

        unreachable = Workspace("http://127.0.0.1:9", timeout_seconds=2.0)
        try:
            LoginCommand().execute(unreachable.context(stdin=LIVE_KEY), True, False)
        except CliError:
            pass
        results.check(
            "an unreachable API writes nothing",
            unreachable.stored_key() is None and not unreachable.credential_file_exists(),
        )
        unreachable.cleanup()

        existing = self._workspace()
        existing.store().write(
            Credentials.from_value(LIVE_KEY), existing.config.profile, existing.config.api_url
        )
        self.backend.expect(ScriptedResponse.json_body({"error": True}, status=401))
        try:
            LoginCommand().execute(existing.context(stdin=OTHER_KEY), True, False)
        except CliError:
            pass
        results.check(
            "a rejected re-login leaves the working key intact",
            existing.stored_key() == LIVE_KEY,
        )
        existing.cleanup()

        shared = self._workspace()
        shared.store().write(
            Credentials.from_value(LIVE_KEY), shared.config.profile, shared.config.api_url
        )
        self.backend.expect(ScriptedResponse.json_body(VALID_BODY))
        WhoamiCommand().execute(shared.context())
        whoami_path = self.backend.requests[-1].path
        self.backend.expect(ScriptedResponse.json_body(VALID_BODY))
        LoginCommand().execute(shared.context(stdin=LIVE_KEY), True, False)
        results.check(
            "login and whoami verify through the same route",
            self.backend.requests[-1].path == whoami_path == AUTH_VALIDATE_PATH,
        )
        shared.cleanup()


def main() -> int:
    results = Results()
    suite = VerificationSuite(results)
    try:
        suite.run()
    finally:
        suite.backend.shutdown()
    return results.summary()


if __name__ == "__main__":
    raise SystemExit(main())
