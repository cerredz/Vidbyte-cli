"""Verification for provider BYOK login: prefix, probe, and verify-before-persist.

Run with `python scripts/test-provider-byok-login.py`. Drives the real
ProviderVerifier over a loopback HTTP server by patching PROVIDER_PROBE_URLS
to point at the fake backend. Nothing reaches the internet.
"""

from __future__ import annotations

import io
import json
import os
import shutil
import sys
import tempfile
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

# Isolate keyring for the whole run.
os.environ["PYTHON_KEYRING_BACKEND"] = "keyring.backends.null.Keyring"

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from vidbyte_cli.commands.provider.login import ProviderLoginCommand  # noqa: E402
from vidbyte_cli.commands.provider.whoami import ProviderWhoamiCommand  # noqa: E402
from vidbyte_cli.lib.auth.provider_credentials import (  # noqa: E402
    FileProviderStore,
    ProviderCredentials,
)
from vidbyte_cli.lib.auth.provider_store import (  # noqa: E402
    KeyringProviderStore,
    ProviderCredentialStore,
)
from vidbyte_cli.lib.auth.provider_verifier import (  # noqa: E402
    ClaudeVerifier,
    OpenAIVerifier,
)
from vidbyte_cli.lib.config.models import ConfigField, ConfigSource, ResolvedConfig  # noqa: E402
from vidbyte_cli.lib.config.paths import VidbytePaths  # noqa: E402
from vidbyte_cli.lib.errors.cli_error import CliError  # noqa: E402
from vidbyte_cli.lib.errors.codes import CliErrorCode, ExitCode  # noqa: E402
from vidbyte_cli.lib.io import IOStreams  # noqa: E402
from vidbyte_cli.lib.output.formats import ColorMode, OutputFormat  # noqa: E402
from vidbyte_cli.lib.runtime.context import ApplicationContext, InvocationOptions  # noqa: E402
from vidbyte_cli.types.provider import PROVIDER_PROBE_URLS, Provider  # noqa: E402

OPENAI_KEY = "sk-proj-" + "a" * 40
CLAUDE_KEY = "sk-ant-api03-" + "b" * 40
BAD_KEY = "sk-bad-" + "x" * 20


@dataclass
class ScriptedResponse:
    status: int = 200
    body: bytes = b""
    content_type: str | None = "application/json"
    headers: dict[str, str] = field(default_factory=dict)
    delay_seconds: float = 0.0

    @classmethod
    def json_body(cls, payload: object, status: int = 200, **extra: str) -> ScriptedResponse:
        return cls(status=status, body=json.dumps(payload).encode(), headers=dict(extra))


@dataclass
class RecordedRequest:
    method: str
    path: str
    headers: dict[str, str]
    body: bytes


class FakeBackend:
    def __init__(self) -> None:
        self.responses: list[ScriptedResponse] = []
        self.requests: list[RecordedRequest] = []
        self._server = self._build_server()
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()

    @property
    def origin(self) -> str:
        return f"http://127.0.0.1:{self._server.server_address[1]}"

    def expect(self, response: ScriptedResponse) -> FakeBackend:
        self.responses.append(response)
        return self

    def reset(self) -> None:
        self.responses.clear()
        self.requests.clear()

    def shutdown(self) -> None:
        self._server.shutdown()
        self._server.server_close()

    def _build_server(self) -> ThreadingHTTPServer:
        class QuietServer(ThreadingHTTPServer):
            def handle_error(self, request: object, client_address: object) -> None:
                return

        return QuietServer(("127.0.0.1", 0), self._build_handler())

    def _build_handler(self) -> type[BaseHTTPRequestHandler]:
        backend = self

        class Handler(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def do_GET(self) -> None:  # noqa: N802
                length = int(self.headers.get("content-length") or 0)
                backend.requests.append(
                    RecordedRequest(
                        method=self.command,
                        path=self.path,
                        headers={k.lower(): v for k, v in self.headers.items()},
                        body=self.rfile.read(length) if length else b"",
                    )
                )
                self._reply(
                    backend.responses.pop(0) if backend.responses else ScriptedResponse(body=b"{}")
                )

            def do_POST(self) -> None:  # noqa: N802
                self.do_GET()

            def _reply(self, response: ScriptedResponse) -> None:
                if response.delay_seconds:
                    time.sleep(response.delay_seconds)
                self.send_response(response.status)
                if response.content_type is not None:
                    self.send_header("Content-Type", response.content_type)
                for k, v in response.headers.items():
                    self.send_header(k, v)
                self.send_header("Content-Length", str(len(response.body)))
                self.end_headers()
                self.wfile.write(response.body)

            def log_message(self, format: str, *args: object) -> None:
                return

        return Handler


class FakeKeyringBackend:
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
    def __init__(self, api_url: str, keyring_priority: float = 5.0) -> None:
        self.root = Path(tempfile.mkdtemp(prefix="vidbyte-provider-verify-"))
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
            request_timeout_seconds=10.0,
            provenance={f: ConfigSource.BUILT_IN for f in ConfigField},
        )
        self.keyring = FakeKeyringBackend(keyring_priority)
        self.stdout = io.StringIO()
        self.stderr = io.StringIO()

    def provider_store(self) -> ProviderCredentialStore:
        return ProviderCredentialStore(
            keyring_store=KeyringProviderStore(backend=self.keyring),  # type: ignore[arg-type]
            file_store=FileProviderStore(self.paths),
            paths=self.paths,
        )

    def context(
        self,
        stdin: str = "",
        environment: dict[str, str] | None = None,
        provider: Provider = Provider.OPENAI,
        no_input: bool = False,
    ) -> ApplicationContext:
        streams = IOStreams(stdin=io.StringIO(stdin), stdout=self.stdout, stderr=self.stderr)
        ctx = ApplicationContext(streams, environment=environment or {}, paths=self.paths)
        ctx.configure(
            InvocationOptions(
                output_format=OutputFormat.HUMAN,
                api_url=self.config.api_url,
                request_timeout_seconds=self.config.request_timeout_seconds,
                no_input=no_input,
                color=ColorMode.NEVER,
            ),
            self.config,
        )
        # Inject provider store to avoid real keyring.
        ctx._provider_store = self.provider_store()  # type: ignore[attr-defined]
        return ctx

    def stored(self, provider: Provider) -> str | None:
        cred = self.provider_store().read(self.config.profile, provider)
        return cred.secret_value() if cred is not None else None

    def file_exists(self) -> bool:
        return self.paths.provider_credentials_file().exists()

    def cleanup(self) -> None:
        shutil.rmtree(self.root, ignore_errors=True)


class Results:
    def __init__(self) -> None:
        self.passed = 0
        self.failed = 0

    def check(self, name: str, condition: bool, detail: str = "") -> None:
        if condition:
            self.passed += 1
            print(f"PASS: {name}")
            return
        self.failed += 1
        print(f"FAIL: {name}{f' - {detail}' if detail else ''}", file=sys.stderr)

    def raises(
        self, name: str, action: Callable[[], Any], code: CliErrorCode, exit_code: ExitCode
    ) -> None:
        try:
            action()
        except CliError as error:
            matched = error.code is code and error.exit_code == int(exit_code)
            detail = f"got {error.code.value}/{error.exit_code}, want {code.value}/{int(exit_code)}"
            self.check(name, matched, detail)
        except Exception as error:  # noqa: BLE001
            self.check(name, False, f"unclassified {type(error).__name__}: {error}")
        else:
            self.check(name, False, "no failure was raised")

    def summary(self) -> int:
        total = self.passed + self.failed
        print(f"\n{self.passed}/{total} tests passed")
        return 1 if self.failed else 0


class Suite:
    def __init__(self, results: Results) -> None:
        self.results = results
        self.backend = FakeBackend()
        # Patch probe URLs to loopback.
        PROVIDER_PROBE_URLS[Provider.OPENAI] = f"{self.backend.origin}/v1/models"
        PROVIDER_PROBE_URLS[Provider.CLAUDE] = f"{self.backend.origin}/v1/models"

    def run(self) -> None:
        for group in (
            self.check_prefix_validation,
            self.check_verifier_headers,
            self.check_verifier_classification,
            self.check_verifier_protocol,
            self.check_login_persistence,
            self.check_resolver_precedence,
            self.check_whoami,
        ):
            group()
            self.backend.reset()

    def check_prefix_validation(self) -> None:
        r = self.results
        r.check(
            "openai sk- prefix is live",
            ProviderCredentials.is_live_format(Provider.OPENAI, OPENAI_KEY),
        )
        r.check(
            "openai sk-ant is not live for openai",
            not ProviderCredentials.is_live_format(Provider.OPENAI, CLAUDE_KEY),
        )
        r.check(
            "claude sk-ant is live", ProviderCredentials.is_live_format(Provider.CLAUDE, CLAUDE_KEY)
        )
        r.check(
            "claude sk-proj is not live for claude",
            not ProviderCredentials.is_live_format(Provider.CLAUDE, OPENAI_KEY),
        )
        # Input path: wrong prefix should fail without network.
        ws = Workspace("http://127.0.0.1:9")
        before = len(self.backend.requests)
        r.raises(
            "openai prefix mismatch raises ProviderKeyNotLiveFormat",
            lambda: ProviderLoginCommand().execute(
                ws.context(stdin=CLAUDE_KEY, provider=Provider.OPENAI), "openai", True, False
            ),
            CliErrorCode.INVALID_ARGUMENT,
            ExitCode.USAGE,
        )
        r.check("no network call on prefix mismatch", len(self.backend.requests) == before)
        r.check("nothing stored on prefix mismatch", ws.stored(Provider.OPENAI) is None)
        ws.cleanup()
        # Empty / oversized input
        ws2 = Workspace("http://127.0.0.1:9")
        r.raises(
            "empty token raises InvalidProviderApiKeyInput",
            lambda: ProviderLoginCommand().execute(
                ws2.context(stdin="   ", provider=Provider.OPENAI), "openai", True, False
            ),
            CliErrorCode.INVALID_ARGUMENT,
            ExitCode.USAGE,
        )
        ws2.cleanup()

    def check_verifier_headers(self) -> None:
        r = self.results
        # OpenAI sends Authorization: Bearer, not x-api-key
        ws = Workspace(self.backend.origin)
        self.backend.expect(ScriptedResponse.json_body({"data": [{"id": "gpt-4"}]}))
        OpenAIVerifier().verify(ProviderCredentials(provider=Provider.OPENAI, api_key=OPENAI_KEY))  # type: ignore[arg-type]
        sent = self.backend.requests[-1]
        r.check(
            "openai sends Authorization Bearer",
            sent.headers.get("authorization") == f"Bearer {OPENAI_KEY}",
        )
        r.check("openai does not send x-api-key", "x-api-key" not in sent.headers)
        r.check("openai probe is GET", sent.method == "GET")
        r.check("openai probe path is /v1/models", sent.path == "/v1/models")
        self.backend.reset()
        # Claude sends x-api-key + anthropic-version
        self.backend.expect(ScriptedResponse.json_body({"data": [{"id": "claude-3"}]}))
        ClaudeVerifier().verify(ProviderCredentials(provider=Provider.CLAUDE, api_key=CLAUDE_KEY))  # type: ignore[arg-type]
        sent = self.backend.requests[-1]
        r.check("claude sends x-api-key", sent.headers.get("x-api-key") == CLAUDE_KEY)
        r.check(
            "claude sends anthropic-version 2023-06-01",
            sent.headers.get("anthropic-version") == "2023-06-01",
        )
        r.check(
            "claude does not send Authorization Bearer",
            sent.headers.get("authorization") is None
            or "Bearer" not in sent.headers.get("authorization", ""),
        )
        ws.cleanup()

    def check_verifier_classification(self) -> None:
        r = self.results
        cases: list[tuple[int, CliErrorCode, ExitCode]] = [
            (401, CliErrorCode.AUTH_REQUIRED, ExitCode.AUTHENTICATION),
            (403, CliErrorCode.AUTH_REQUIRED, ExitCode.AUTHENTICATION),
            (400, CliErrorCode.INVALID_ARGUMENT, ExitCode.USAGE),
            (429, CliErrorCode.API_UNAVAILABLE, ExitCode.OPERATIONAL_FAILURE),
            (500, CliErrorCode.API_UNAVAILABLE, ExitCode.OPERATIONAL_FAILURE),
        ]
        for status, code, exit_code in cases:
            self.backend.expect(ScriptedResponse.json_body({"error": True}, status=status))
            r.raises(
                f"status {status} maps to {code.value}",
                lambda: OpenAIVerifier().verify(
                    ProviderCredentials(provider=Provider.OPENAI, api_key=OPENAI_KEY)
                ),  # type: ignore[arg-type]
                code,
                exit_code,
            )
        # 429 Retry-After
        self.backend.expect(
            ScriptedResponse.json_body({"error": True}, status=429, **{"Retry-After": "60"})
        )
        try:
            OpenAIVerifier().verify(
                ProviderCredentials(provider=Provider.OPENAI, api_key=OPENAI_KEY)
            )  # type: ignore[arg-type]
        except CliError as e:
            r.check("429 surfaces Retry-After in hint", "60" in (e.hint or ""))
            r.check("429 is retryable", e.retryable)
        # Transport failure
        closed = Workspace("http://127.0.0.1:9")
        orig = PROVIDER_PROBE_URLS[Provider.OPENAI]
        PROVIDER_PROBE_URLS[Provider.OPENAI] = "http://127.0.0.1:9/v1/models"
        r.raises(
            "closed port raises ProviderApiUnreachable",
            lambda: OpenAIVerifier().verify(
                ProviderCredentials(provider=Provider.OPENAI, api_key=OPENAI_KEY)
            ),  # type: ignore[arg-type]
            CliErrorCode.API_UNAVAILABLE,
            ExitCode.OPERATIONAL_FAILURE,
        )
        PROVIDER_PROBE_URLS[Provider.OPENAI] = orig
        closed.cleanup()
        # Redirect not followed
        self.backend.expect(
            ScriptedResponse.json_body(
                {"error": True}, status=302, Location=f"{self.backend.origin}/followed"
            )
        )
        self.backend.expect(ScriptedResponse.json_body({"data": []}))
        before = len(self.backend.requests)
        try:
            OpenAIVerifier().verify(
                ProviderCredentials(provider=Provider.OPENAI, api_key=OPENAI_KEY)
            )  # type: ignore[arg-type]
        except CliError:
            pass
        r.check("redirect is not followed", len(self.backend.requests) == before + 1)
        self.backend.responses.clear()
        # Never echo body
        self.backend.expect(ScriptedResponse.json_body({"error": OPENAI_KEY}, status=401))
        try:
            OpenAIVerifier().verify(
                ProviderCredentials(provider=Provider.OPENAI, api_key=OPENAI_KEY)
            )  # type: ignore[arg-type]
        except CliError as e:
            rendered = " ".join([str(p) for p in (e.message, e.description, e.trace, e.hint) if p])
            r.check("failure never echoes key from body", OPENAI_KEY not in rendered)

    def check_verifier_protocol(self) -> None:
        r = self.results
        # Valid 200
        self.backend.expect(ScriptedResponse.json_body({"data": [{"id": "x"}]}))
        ident = OpenAIVerifier().verify(
            ProviderCredentials(provider=Provider.OPENAI, api_key=OPENAI_KEY)
        )  # type: ignore[arg-type]
        r.check("valid 200 returns verified identity", ident.verified is True)
        # Invalid bodies
        for label, resp in (
            ("empty body", ScriptedResponse(body=b"")),
            ("non-JSON", ScriptedResponse(body=b"<html/>")),
            ("no data list", ScriptedResponse.json_body({"object": "list"})),
            ("oversized", ScriptedResponse(body=b"x" * (1_048_577))),
        ):
            self.backend.expect(resp)
            r.raises(
                f"{label} raises ProviderApiProtocolError",
                lambda: OpenAIVerifier().verify(
                    ProviderCredentials(provider=Provider.OPENAI, api_key=OPENAI_KEY)
                ),  # type: ignore[arg-type]
                CliErrorCode.API_PROTOCOL_ERROR,
                ExitCode.OPERATIONAL_FAILURE,
            )

    def check_login_persistence(self) -> None:
        r = self.results
        # Accepted writes
        ws = Workspace(self.backend.origin)
        self.backend.expect(ScriptedResponse.json_body({"data": [{"id": "gpt-4"}]}))
        ProviderLoginCommand().execute(
            ws.context(stdin=OPENAI_KEY, provider=Provider.OPENAI), "openai", True, False
        )
        r.check("accepted openai key is stored", ws.stored(Provider.OPENAI) == OPENAI_KEY)
        r.check("exactly one probe per login", len(self.backend.requests) == 1)
        ws.cleanup()
        # Rejected writes nothing
        for label, status in (("401 rejected", 401), ("500 server error", 500)):
            w = Workspace(self.backend.origin)
            self.backend.expect(ScriptedResponse.json_body({"error": True}, status=status))
            try:
                ProviderLoginCommand().execute(
                    w.context(stdin=OPENAI_KEY, provider=Provider.OPENAI), "openai", True, False
                )
            except CliError:
                pass
            r.check(f"{label} writes nothing", w.stored(Provider.OPENAI) is None)
            r.check(f"{label} creates no file", not w.file_exists())
            w.cleanup()
        # Existing key survives failed re-login
        w = Workspace(self.backend.origin)
        w.provider_store().write(
            ProviderCredentials(provider=Provider.OPENAI, api_key=OPENAI_KEY),
            w.config.profile,
            Provider.OPENAI,
        )  # type: ignore[arg-type]
        self.backend.expect(ScriptedResponse.json_body({"error": True}, status=401))
        try:
            ProviderLoginCommand().execute(
                w.context(stdin=BAD_KEY, provider=Provider.OPENAI), "openai", True, False
            )
        except CliError:
            pass
        # BAD_KEY fails prefix before network; second case uses valid prefix but bad auth
        w2 = Workspace(self.backend.origin)
        w2.provider_store().write(
            ProviderCredentials(provider=Provider.OPENAI, api_key=OPENAI_KEY),
            w2.config.profile,
            Provider.OPENAI,
        )  # type: ignore[arg-type]
        self.backend.expect(ScriptedResponse.json_body({"error": True}, status=401))
        try:
            ProviderLoginCommand().execute(
                w2.context(stdin=OPENAI_KEY, provider=Provider.OPENAI), "openai", True, False
            )
        except CliError:
            pass
        r.check(
            "rejected re-login leaves prior key intact", w2.stored(Provider.OPENAI) == OPENAI_KEY
        )
        w.cleanup()
        w2.cleanup()
        # File fallback when no keyring
        w = Workspace(self.backend.origin, keyring_priority=0.0)
        self.backend.expect(ScriptedResponse.json_body({"data": [{"id": "m"}]}))
        ProviderLoginCommand().execute(
            w.context(stdin=OPENAI_KEY, provider=Provider.OPENAI), "openai", True, True
        )
        r.check(
            "accepted writes file when allowed",
            w.file_exists() and w.stored(Provider.OPENAI) == OPENAI_KEY,
        )
        w.cleanup()
        w = Workspace(self.backend.origin, keyring_priority=0.0)
        self.backend.expect(ScriptedResponse.json_body({"data": [{"id": "m"}]}))
        try:
            ProviderLoginCommand().execute(
                w.context(stdin=OPENAI_KEY, provider=Provider.OPENAI, no_input=True),
                "openai",
                True,
                False,
            )
        except CliError:
            pass
        r.check(
            "no consent writes nothing", not w.file_exists() and w.stored(Provider.OPENAI) is None
        )
        w.cleanup()
        # Claude accepted as well
        w = Workspace(self.backend.origin)
        self.backend.expect(ScriptedResponse.json_body({"data": [{"id": "claude-3"}]}))
        ProviderLoginCommand().execute(
            w.context(stdin=CLAUDE_KEY, provider=Provider.CLAUDE), "claude", True, False
        )
        r.check("accepted claude key is stored", w.stored(Provider.CLAUDE) == CLAUDE_KEY)
        r.check("claude does not overwrite openai", w.stored(Provider.OPENAI) is None)
        w.cleanup()

    def check_resolver_precedence(self) -> None:
        r = self.results
        w = Workspace(self.backend.origin)
        w.provider_store().write(
            ProviderCredentials(provider=Provider.OPENAI, api_key=OPENAI_KEY),
            w.config.profile,
            Provider.OPENAI,
        )  # type: ignore[arg-type]
        # Env wins over stored
        env_key = "sk-proj-" + "e" * 40
        ctx = w.context(environment={"OPENAI_API_KEY": env_key}, provider=Provider.OPENAI)
        resolved = ctx.provider_resolver().resolve(w.config.profile, Provider.OPENAI)
        r.check(
            "env outranks keyring",
            resolved is not None and resolved.credentials.secret_value() == env_key,
        )
        r.check(
            "env source is environment",
            resolved is not None and resolved.source.value == "environment",
        )
        # Invalid env raises, not fallback
        r.raises(
            "invalid env prefix raises InvalidProviderEnvironmentKey",
            lambda: (
                ctx.provider_resolver().resolve(w.config.profile, Provider.OPENAI)
                if False
                else w.context(environment={"OPENAI_API_KEY": CLAUDE_KEY}, provider=Provider.OPENAI)
                .provider_resolver()
                .resolve(w.config.profile, Provider.OPENAI)
            ),
            CliErrorCode.AUTH_REQUIRED,
            ExitCode.AUTHENTICATION,
        )
        # Without env, keyring is used
        ctx2 = w.context(provider=Provider.OPENAI)
        resolved2 = ctx2.provider_resolver().resolve(w.config.profile, Provider.OPENAI)
        r.check(
            "without env, keyring is source",
            resolved2 is not None and resolved2.source.value == "keyring",
        )
        w.cleanup()

    def check_whoami(self) -> None:
        r = self.results
        w = Workspace(self.backend.origin)
        r.raises(
            "whoami with no key raises ProviderAuthenticationRequired",
            lambda: ProviderWhoamiCommand().execute(w.context(provider=Provider.OPENAI), "openai"),
            CliErrorCode.AUTH_REQUIRED,
            ExitCode.AUTHENTICATION,
        )
        r.check("whoami makes no probe when no key", len(self.backend.requests) == 0)
        # Stored key: probe is made and identity printed
        w.provider_store().write(
            ProviderCredentials(provider=Provider.OPENAI, api_key=OPENAI_KEY),
            w.config.profile,
            Provider.OPENAI,
        )  # type: ignore[arg-type]
        self.backend.expect(ScriptedResponse.json_body({"data": [{"id": "gpt-4"}]}))
        ProviderWhoamiCommand().execute(w.context(provider=Provider.OPENAI), "openai")
        r.check("whoami prints provider", "openai" in w.stdout.getvalue())
        r.check("whoami never prints key", OPENAI_KEY not in w.stdout.getvalue())
        w.cleanup()


def main() -> int:
    results = Results()
    suite = Suite(results)
    try:
        suite.run()
    finally:
        suite.backend.shutdown()
    return results.summary()


if __name__ == "__main__":
    raise SystemExit(main())
