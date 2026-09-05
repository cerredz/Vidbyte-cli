"""Verification for extended provider BYOK login: grok, deepseek, glm, muse.

Run with `python scripts/test-provider-byok-login-extended.py`. Drives real
verifiers over a loopback HTTP server by patching PROVIDER_PROBE_URLS to
point at the fake backend. Nothing reaches the internet. Covers all six
providers (openai, claude, grok, deepseek, glm, muse) and is the Phase 5
script for provider-byok-login-extended.
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
    DeepSeekVerifier,
    GlmVerifier,
    GrokVerifier,
    MuseVerifier,
    OpenAIVerifier,
    verifier_for_provider,
)
from vidbyte_cli.lib.config.models import ConfigField, ConfigSource, ResolvedConfig  # noqa: E402
from vidbyte_cli.lib.config.paths import VidbytePaths  # noqa: E402
from vidbyte_cli.lib.errors.cli_error import CliError  # noqa: E402
from vidbyte_cli.lib.errors.codes import CliErrorCode, ExitCode  # noqa: E402
from vidbyte_cli.lib.io import IOStreams  # noqa: E402
from vidbyte_cli.lib.output.formats import ColorMode, OutputFormat  # noqa: E402
from vidbyte_cli.lib.runtime.context import ApplicationContext, InvocationOptions  # noqa: E402
from vidbyte_cli.types.provider import (  # noqa: E402
    PROVIDER_DISPLAY,
    PROVIDER_ENV_VARS,
    PROVIDER_KEY_PREFIXES,
    PROVIDER_PROBE_URLS,
    Provider,
)

OPENAI_KEY = "sk-proj-" + "a" * 40
CLAUDE_KEY = "sk-ant-api03-" + "b" * 40
DEEPSEEK_KEY = "sk-deepseek-" + "c" * 40
MUSE_KEY = "LLM|12345|" + "d" * 40
GROK_KEY = "xai-" + "e" * 40
GLM_KEY = "glm-" + "f" * 40
BAD_SCHOICE = "not-a-key"


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
        self.root = Path(tempfile.mkdtemp(prefix="vidbyte-provider-extended-"))
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
        for p in Provider:
            PROVIDER_PROBE_URLS[p] = f"{self.backend.origin}/v1/models"

    def run(self) -> None:
        for group in (
            self.check_type_maps,
            self.check_prefix_validation,
            self.check_verifier_headers,
            self.check_verifier_classification_and_protocol,
            self.check_factory,
            self.check_login_persistence_all_providers,
            self.check_resolver_precedence,
            self.check_whoami,
            self.check_logout_scoping,
        ):
            group()
            self.backend.reset()

    def check_type_maps(self) -> None:
        r = self.results
        for p in Provider:
            r.check(f"{p.value} has env var", p in PROVIDER_ENV_VARS)
            r.check(f"{p.value} has probe url", p in PROVIDER_PROBE_URLS)
            r.check(f"{p.value} has display", p in PROVIDER_DISPLAY)
            r.check(f"{p.value} has prefix entry", p in PROVIDER_KEY_PREFIXES)
        # Case sensitive via click Choice is tested implicitly; enum is value-based
        r.check("Provider enum has 6 members", len(list(Provider)) == 6)
        r.check("muse prefix is LLM|", PROVIDER_KEY_PREFIXES[Provider.MUSE] == ("LLM|",))
        r.check("deepseek prefix is sk-", PROVIDER_KEY_PREFIXES[Provider.DEEPSEEK] == ("sk-",))
        r.check("grok prefix empty (opaque)", PROVIDER_KEY_PREFIXES[Provider.GROK] == ())
        r.check("glm prefix empty (opaque)", PROVIDER_KEY_PREFIXES[Provider.GLM] == ())

    def check_prefix_validation(self) -> None:
        r = self.results
        r.check(
            "openai sk- is live", ProviderCredentials.is_live_format(Provider.OPENAI, OPENAI_KEY)
        )
        r.check(
            "deepseek sk- is live",
            ProviderCredentials.is_live_format(Provider.DEEPSEEK, DEEPSEEK_KEY),
        )
        r.check("muse LLM| is live", ProviderCredentials.is_live_format(Provider.MUSE, MUSE_KEY))
        r.check("grok opaque is live", ProviderCredentials.is_live_format(Provider.GROK, GROK_KEY))
        r.check("glm opaque is live", ProviderCredentials.is_live_format(Provider.GLM, GLM_KEY))
        r.check(
            "openai sk-ant not live for openai",
            not ProviderCredentials.is_live_format(Provider.OPENAI, CLAUDE_KEY),
        )
        r.check(
            "claude sk-proj not live for claude",
            not ProviderCredentials.is_live_format(Provider.CLAUDE, OPENAI_KEY),
        )
        r.check(
            "muse sk- not live for muse",
            not ProviderCredentials.is_live_format(Provider.MUSE, OPENAI_KEY),
        )
        r.check(
            "deepseek LLM| not live for deepseek",
            not ProviderCredentials.is_live_format(Provider.DEEPSEEK, MUSE_KEY),
        )
        # Wrong prefix raises without network
        ws = Workspace("http://127.0.0.1:9")
        before = len(self.backend.requests)
        r.raises(
            "muse prefix mismatch raises ProviderKeyNotLiveFormat",
            lambda: ProviderLoginCommand().execute(
                ws.context(stdin=OPENAI_KEY, provider=Provider.MUSE), "muse", True, False
            ),
            CliErrorCode.INVALID_ARGUMENT,
            ExitCode.USAGE,
        )
        r.check("no network on muse prefix mismatch", len(self.backend.requests) == before)
        r.check("nothing stored on muse prefix mismatch", ws.stored(Provider.MUSE) is None)
        ws.cleanup()
        ws2 = Workspace("http://127.0.0.1:9")
        before = len(self.backend.requests)
        r.raises(
            "deepseek prefix mismatch raises ProviderKeyNotLiveFormat",
            lambda: ProviderLoginCommand().execute(
                ws2.context(stdin=MUSE_KEY, provider=Provider.DEEPSEEK), "deepseek", True, False
            ),
            CliErrorCode.INVALID_ARGUMENT,
            ExitCode.USAGE,
        )
        r.check("no network on deepseek prefix mismatch", len(self.backend.requests) == before)
        ws2.cleanup()
        # Grok/glm accept any bounded non-empty
        r.check(
            "grok sk- accepted (opaque)",
            ProviderCredentials.is_live_format(Provider.GROK, OPENAI_KEY),
        )
        r.check(
            "glm any string accepted", ProviderCredentials.is_live_format(Provider.GLM, BAD_SCHOICE)
        )

    def check_verifier_headers(self) -> None:
        r = self.results
        # OpenAI still Bearer
        self.backend.expect(ScriptedResponse.json_body({"data": [{"id": "m"}]}))
        OpenAIVerifier().verify(
            ProviderCredentials(provider=Provider.OPENAI, api_key=OPENAI_KEY)  # type: ignore[arg-type]
        )
        sent = self.backend.requests[-1]
        r.check("openai sends Bearer", sent.headers.get("authorization") == f"Bearer {OPENAI_KEY}")
        r.check("openai no x-api-key", "x-api-key" not in sent.headers)
        self.backend.reset()
        # Grok Bearer
        self.backend.expect(ScriptedResponse.json_body({"data": [{"id": "m"}]}))
        GrokVerifier().verify(
            ProviderCredentials(provider=Provider.GROK, api_key=GROK_KEY)  # type: ignore[arg-type]
        )
        sent = self.backend.requests[-1]
        r.check("grok sends Bearer", sent.headers.get("authorization") == f"Bearer {GROK_KEY}")
        r.check("grok no x-api-key", "x-api-key" not in sent.headers)
        r.check("grok probe path is /v1/models", sent.path == "/v1/models")
        self.backend.reset()
        # DeepSeek Bearer
        self.backend.expect(ScriptedResponse.json_body({"data": [{"id": "m"}]}))
        DeepSeekVerifier().verify(
            ProviderCredentials(provider=Provider.DEEPSEEK, api_key=DEEPSEEK_KEY)  # type: ignore[arg-type]
        )
        sent = self.backend.requests[-1]
        r.check(
            "deepseek sends Bearer", sent.headers.get("authorization") == f"Bearer {DEEPSEEK_KEY}"
        )
        r.check("deepseek no x-api-key", "x-api-key" not in sent.headers)
        self.backend.reset()
        # GLM Bearer
        self.backend.expect(ScriptedResponse.json_body({"data": [{"id": "m"}]}))
        GlmVerifier().verify(
            ProviderCredentials(provider=Provider.GLM, api_key=GLM_KEY)  # type: ignore[arg-type]
        )
        sent = self.backend.requests[-1]
        r.check("glm sends Bearer", sent.headers.get("authorization") == f"Bearer {GLM_KEY}")
        r.check("glm no x-api-key", "x-api-key" not in sent.headers)
        self.backend.reset()
        # Muse Bearer
        self.backend.expect(ScriptedResponse.json_body({"data": [{"id": "m"}]}))
        MuseVerifier().verify(
            ProviderCredentials(provider=Provider.MUSE, api_key=MUSE_KEY)  # type: ignore[arg-type]
        )
        sent = self.backend.requests[-1]
        r.check("muse sends Bearer", sent.headers.get("authorization") == f"Bearer {MUSE_KEY}")
        r.check("muse no x-api-key", "x-api-key" not in sent.headers)
        self.backend.reset()
        # Claude still x-api-key + version
        self.backend.expect(ScriptedResponse.json_body({"data": [{"id": "m"}]}))
        ClaudeVerifier().verify(
            ProviderCredentials(provider=Provider.CLAUDE, api_key=CLAUDE_KEY)  # type: ignore[arg-type]
        )
        sent = self.backend.requests[-1]
        r.check("claude sends x-api-key", sent.headers.get("x-api-key") == CLAUDE_KEY)
        r.check("claude version 2023-06-01", sent.headers.get("anthropic-version") == "2023-06-01")

    def check_verifier_classification_and_protocol(self) -> None:
        r = self.results
        for status, code, exit_code in [
            (401, CliErrorCode.AUTH_REQUIRED, ExitCode.AUTHENTICATION),
            (403, CliErrorCode.AUTH_REQUIRED, ExitCode.AUTHENTICATION),
            (400, CliErrorCode.INVALID_ARGUMENT, ExitCode.USAGE),
            (429, CliErrorCode.API_UNAVAILABLE, ExitCode.OPERATIONAL_FAILURE),
            (500, CliErrorCode.API_UNAVAILABLE, ExitCode.OPERATIONAL_FAILURE),
        ]:
            self.backend.expect(ScriptedResponse.json_body({"error": True}, status=status))
            r.raises(
                f"status {status} maps to {code.value}",
                lambda: GrokVerifier().verify(
                    ProviderCredentials(provider=Provider.GROK, api_key=GROK_KEY)  # type: ignore[arg-type]
                ),
                code,
                exit_code,
            )
        # DeepSeek 401 same
        self.backend.expect(ScriptedResponse.json_body({"error": True}, status=401))
        r.raises(
            "deepseek 401 rejected",
            lambda: DeepSeekVerifier().verify(
                ProviderCredentials(provider=Provider.DEEPSEEK, api_key=DEEPSEEK_KEY)  # type: ignore[arg-type]
            ),
            CliErrorCode.AUTH_REQUIRED,
            ExitCode.AUTHENTICATION,
        )
        # Valid 200
        self.backend.expect(ScriptedResponse.json_body({"data": [{"id": "m"}]}))
        ident = GlmVerifier().verify(
            ProviderCredentials(provider=Provider.GLM, api_key=GLM_KEY)  # type: ignore[arg-type]
        )
        r.check("glm valid 200 verified", ident.verified is True)
        # Protocol errors
        for label, resp in (
            ("empty body", ScriptedResponse(body=b"")),
            ("non-JSON", ScriptedResponse(body=b"<html/>")),
            ("no data list", ScriptedResponse.json_body({"object": "list"})),
            ("oversized", ScriptedResponse(body=b"x" * (1_048_577))),
        ):
            self.backend.expect(resp)
            r.raises(
                f"{label} raises protocol error",
                lambda: MuseVerifier().verify(
                    ProviderCredentials(provider=Provider.MUSE, api_key=MUSE_KEY)  # type: ignore[arg-type]
                ),
                CliErrorCode.API_PROTOCOL_ERROR,
                ExitCode.OPERATIONAL_FAILURE,
            )

    def check_factory(self) -> None:
        r = self.results
        for p, cls in [
            (Provider.OPENAI, OpenAIVerifier),
            (Provider.CLAUDE, ClaudeVerifier),
            (Provider.GROK, GrokVerifier),
            (Provider.DEEPSEEK, DeepSeekVerifier),
            (Provider.GLM, GlmVerifier),
            (Provider.MUSE, MuseVerifier),
        ]:
            inst = verifier_for_provider(p)
            r.check(f"factory {p.value} returns {cls.__name__}", isinstance(inst, cls))

    def check_login_persistence_all_providers(self) -> None:
        r = self.results
        cases = [
            (Provider.GROK, GROK_KEY),
            (Provider.DEEPSEEK, DEEPSEEK_KEY),
            (Provider.GLM, GLM_KEY),
            (Provider.MUSE, MUSE_KEY),
        ]
        for provider, key in cases:
            ws = Workspace(self.backend.origin)
            self.backend.expect(ScriptedResponse.json_body({"data": [{"id": "m"}]}))
            ProviderLoginCommand().execute(
                ws.context(stdin=key, provider=provider), provider.value, True, False
            )
            r.check(f"accepted {provider.value} stored", ws.stored(provider) == key)
            r.check(f"one probe per {provider.value} login", len(self.backend.requests) == 1)
            ws.cleanup()
            self.backend.reset()
            # Rejected writes nothing
            w = Workspace(self.backend.origin)
            self.backend.expect(ScriptedResponse.json_body({"error": True}, status=401))
            try:
                ProviderLoginCommand().execute(
                    w.context(stdin=key, provider=provider), provider.value, True, False
                )
            except CliError:
                pass
            r.check(f"{provider.value} 401 writes nothing", w.stored(provider) is None)
            w.cleanup()
            self.backend.reset()

    def check_resolver_precedence(self) -> None:
        r = self.results
        # Muse env precedence
        w = Workspace(self.backend.origin)
        w.provider_store().write(
            ProviderCredentials(provider=Provider.MUSE, api_key=MUSE_KEY),
            w.config.profile,
            Provider.MUSE,  # type: ignore[arg-type]
        )
        env_key = "LLM|99999|" + "z" * 40
        ctx = w.context(environment={"MODEL_API_KEY": env_key}, provider=Provider.MUSE)
        resolved = ctx.provider_resolver().resolve(w.config.profile, Provider.MUSE)
        r.check(
            "muse env outranks keyring",
            resolved is not None and resolved.credentials.secret_value() == env_key,
        )
        # Invalid env raises
        r.raises(
            "invalid muse env raises",
            lambda: (
                w.context(environment={"MODEL_API_KEY": OPENAI_KEY}, provider=Provider.MUSE)
                .provider_resolver()
                .resolve(w.config.profile, Provider.MUSE)
            ),
            CliErrorCode.AUTH_REQUIRED,
            ExitCode.AUTHENTICATION,
        )
        # DeepSeek invalid env
        r.raises(
            "invalid deepseek env raises",
            lambda: (
                w.context(environment={"DEEPSEEK_API_KEY": MUSE_KEY}, provider=Provider.DEEPSEEK)
                .provider_resolver()
                .resolve(w.config.profile, Provider.DEEPSEEK)
            ),
            CliErrorCode.AUTH_REQUIRED,
            ExitCode.AUTHENTICATION,
        )
        # Grok env any string accepted
        ctx2 = w.context(environment={"XAI_API_KEY": "any-opaque-key"}, provider=Provider.GROK)
        resolved2 = ctx2.provider_resolver().resolve(w.config.profile, Provider.GROK)
        r.check("grok env opaque accepted", resolved2 is not None)
        w.cleanup()

    def check_whoami(self) -> None:
        r = self.results
        w = Workspace(self.backend.origin)
        r.raises(
            "whoami no key raises",
            lambda: ProviderWhoamiCommand().execute(w.context(provider=Provider.GLM), "glm"),
            CliErrorCode.AUTH_REQUIRED,
            ExitCode.AUTHENTICATION,
        )
        r.check("whoami no probe when no key", len(self.backend.requests) == 0)
        w.provider_store().write(
            ProviderCredentials(provider=Provider.MUSE, api_key=MUSE_KEY),
            w.config.profile,
            Provider.MUSE,  # type: ignore[arg-type]
        )
        self.backend.expect(ScriptedResponse.json_body({"data": [{"id": "m"}]}))
        ProviderWhoamiCommand().execute(w.context(provider=Provider.MUSE), "muse")
        r.check("whoami prints muse", "muse" in w.stdout.getvalue())
        r.check("whoami never prints key", MUSE_KEY not in w.stdout.getvalue())
        w.cleanup()

    def check_logout_scoping(self) -> None:
        r = self.results
        w = Workspace(self.backend.origin)
        w.provider_store().write(
            ProviderCredentials(provider=Provider.OPENAI, api_key=OPENAI_KEY),
            w.config.profile,
            Provider.OPENAI,  # type: ignore[arg-type]
        )
        w.provider_store().write(
            ProviderCredentials(provider=Provider.GROK, api_key=GROK_KEY),
            w.config.profile,
            Provider.GROK,  # type: ignore[arg-type]
        )
        # Clear only grok
        from vidbyte_cli.commands.provider.logout import ProviderLogoutCommand

        ProviderLogoutCommand().execute(w.context(provider=Provider.GROK), "grok")
        r.check("logout grok clears grok", w.stored(Provider.GROK) is None)
        r.check("logout grok leaves openai", w.stored(Provider.OPENAI) == OPENAI_KEY)
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
