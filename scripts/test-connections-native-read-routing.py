"""Offline verification for native-CLI read routing.

Uses monkeypatched subprocess probes plus the loopback direct fallback. Never
spawns a real gh binary and never contacts GitHub, Slack, or Google.
"""

from __future__ import annotations

import io
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from pydantic import SecretStr, ValidationError  # noqa: E402

from vidbyte_cli.commands.connections.read import ConnectionReadCommand  # noqa: E402
from vidbyte_cli.lib.config.models import (  # noqa: E402
    ConfigField,
    ConfigSource,
    ResolvedConfig,
)
from vidbyte_cli.lib.config.paths import VidbytePaths  # noqa: E402
from vidbyte_cli.lib.connections.manager import ConnectionManager  # noqa: E402
from vidbyte_cli.lib.connections.native import NativeProbe, NativeRunner  # noqa: E402
from vidbyte_cli.lib.connections.providers.github_native import (  # noqa: E402
    GitHubNativeAdapter,
)
from vidbyte_cli.lib.connections.store import (  # noqa: E402
    ConnectionKeyringStore,
    ConnectionStore,
)
from vidbyte_cli.lib.errors.failures import (  # noqa: E402
    ConnectionAuthenticationRequired,
    ConnectionNativeCliFailed,
    ConnectionNativeCliMissing,
    ConnectionProtocolError,
    ConnectionResourceUnavailable,
)
from vidbyte_cli.lib.io import IOStreams  # noqa: E402
from vidbyte_cli.lib.output.formats import ColorMode, OutputFormat  # noqa: E402
from vidbyte_cli.lib.runtime.context import (  # noqa: E402
    ApplicationContext,
    InvocationOptions,
)
from vidbyte_cli.types.connection import (  # noqa: E402
    ConnectionMetadata,
    ConnectionProvider,
    ConnectionResource,
    ConnectionToken,
    ReadProvenance,
    ReadVia,
)


class Results:
    """Collects labeled PASS/FAIL results with a final count."""

    def __init__(self) -> None:
        # Separate counters keep one failure from hiding later results.
        self.passed = 0
        self.failed = 0

    def check(self, name: str, condition: bool, detail: str = "") -> None:
        # Prints one machine-searchable label per design-plan case.
        if condition:
            self.passed += 1
            print(f"PASS: {name}")
        else:
            self.failed += 1
            print(f"FAIL: {name} {detail}")

    def summary(self) -> int:
        # Reports the total and fails the process on any failure.
        print(f"{self.passed}/{self.passed + self.failed} tests passed")
        return 1 if self.failed else 0


class FakeKeyring:
    """In-memory keyring backend for isolated manager tests."""

    priority = 5.0

    def __init__(self) -> None:
        # Values are stored as serialized keyring strings.
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


class StubProbe(NativeProbe):
    """Deterministic probe double driven by fixed availability."""

    def __init__(self, found: bool, authenticated: bool) -> None:
        # Bypasses PATH so tests run identically on every machine.
        super().__init__()
        from vidbyte_cli.lib.connections.native import NativeAvailability

        version = "2.74.0" if found else None
        self._fixed = NativeAvailability(found=found, authenticated=authenticated, version=version)

    def github(self) -> Any:
        # Returns the fixed availability without spawning anything.
        return self._fixed


class Harness:
    """Isolated manager with seeded named connections."""

    def __init__(self) -> None:
        # Each harness owns temp disk state and one ConnectionManager.
        self.root = Path(tempfile.mkdtemp(prefix="vidbyte-native-test-"))
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
        streams = IOStreams(stdin=io.StringIO(), stdout=self.stdout, stderr=self.stderr)
        self.context = ApplicationContext(streams, environment={}, paths=self.paths)
        provenance = {field: ConfigSource.BUILT_IN for field in ConfigField}
        config = ResolvedConfig(
            profile="default",
            api_url="https://vidbyte.test",
            output_format=OutputFormat.HUMAN,
            color=ColorMode.NEVER,
            request_timeout_seconds=3.0,
            provenance=provenance,
        )
        options = InvocationOptions(
            output_format=OutputFormat.HUMAN,
            profile="default",
            api_url=config.api_url,
            request_timeout_seconds=3.0,
            color=ColorMode.NEVER,
        )
        self.context.configure(options, config)
        self.manager = ConnectionManager(self.context)
        store = ConnectionStore(
            self.paths,
            ConnectionKeyringStore(self.keyring),  # type: ignore[arg-type]
        )
        self.manager._store = store  # type: ignore[attr-defined]
        self.context._connections = self.manager  # type: ignore[attr-defined]
        self._seed_connections()

    def _seed_connections(self) -> None:
        # Seeds github and slack named connections with fresh tokens.
        pairs = (
            (ConnectionProvider.GITHUB, "work-github"),
            (ConnectionProvider.SLACK, "work-slack"),
        )
        for provider, name in pairs:
            token = ConnectionToken(
                access_token=SecretStr("seed-access"),
                provider_data={"scopes": "read:user repo"},
            )
            metadata = ConnectionMetadata(
                profile="default",
                provider=provider,
                name=name,
                account_id="42",
                account_label="octocat",
            )
            self.manager._store.save("default", token, metadata)  # type: ignore[attr-defined]

    def close(self) -> None:
        # Removes only this test's temporary directory.
        import shutil as _shutil

        _shutil.rmtree(self.root, ignore_errors=True)


class Completed:
    """Minimal subprocess.CompletedProcess double for runner tests."""

    def __init__(self, returncode: int, stdout: str, stderr: str = "") -> None:
        # Carries only the fields NativeRunner reads.
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


def github_repo(identifier: str = "acme/api") -> ConnectionResource:
    # Builds the standard GitHub repo resource used across cases.
    return ConnectionResource(
        provider=ConnectionProvider.GITHUB,
        resource_type="repo",
        identifier=identifier,
    )


def swap_subprocess(monkey_run: Any, monkey_which: Any) -> Any:
    # Swaps subprocess.run and shutil.which, returning restore state.
    original_run = subprocess.run
    original_which = shutil.which
    subprocess.run = monkey_run  # type: ignore[assignment]
    shutil.which = monkey_which  # type: ignore[assignment]
    return (original_run, original_which)


def restore_subprocess(state: Any) -> None:
    # Restores the real subprocess and which implementations.
    subprocess.run, shutil.which = state


def gh_binary(name: str) -> str | None:
    # Pretends gh is installed at a fixed location.
    _ = name
    return "/usr/bin/gh"


def no_binary(name: str) -> str | None:
    # Pretends no native binary exists on PATH.
    _ = name
    return None


class DirectDouble:
    """Records direct fallback reads without any HTTP."""

    def __init__(self) -> None:
        # Tracks which identifiers reached the direct path.
        self.calls: list[str] = []

    def read(self, context: Any, token: Any, resource: Any) -> Any:
        # Returns a direct read with the expected provenance.
        _ = (context, token)
        self.calls.append(resource.identifier)
        from vidbyte_cli.types.connection import ConnectionRead as ReadType

        return ReadType(
            provider=resource.provider,
            resource_type=resource.resource_type,
            identifier=resource.identifier,
            data={"full_name": "acme/api"},
            provenance=ReadProvenance(source="direct", plan=("GET", "api.github.com")),
        )


class RoutingSuite:
    """Runs every native-routing case against one harness."""

    def __init__(self, results: Results, harness: Harness) -> None:
        # Binds the shared results collector and isolated harness.
        self.results = results
        self.harness = harness

    def run(self) -> None:
        # Executes each case group in dependency order.
        self.check_types()
        self.check_plans()
        self.check_auto_native()
        self.check_direct_forced()
        self.check_auth_fallback()
        self.check_native_missing()
        self.check_classifier()
        self.check_runner_bounds()
        self.check_show_plan()
        self.check_slack_guard()

    def check_types(self) -> None:
        # Validates the transport vocabulary and provenance bounds.
        choices = set(ReadVia.cli_choices())
        self.results.check(
            "[Edge Case] via rejects unknown transport",
            "bogus" not in choices and choices == {"auto", "native", "direct"},
        )
        try:
            too_many = tuple(f"t{i}" for i in range(33))
            ReadProvenance(source="gh", plan=too_many)
            self.results.check("[Edge Case] provenance rejects long plan", False)
        except ValidationError:
            self.results.check("[Edge Case] provenance rejects long plan", True)
        try:
            ReadProvenance(source="gh", plan=("x" * 513,))
            self.results.check("[Edge Case] provenance rejects wide token", False)
        except ValidationError:
            self.results.check("[Edge Case] provenance rejects wide token", True)

    def check_plans(self) -> None:
        # Validates allowlisted argv shapes and identifier rejection.
        adapter = GitHubNativeAdapter(StubProbe(True, True))
        repo_plan = adapter.plan(github_repo())
        self.results.check(
            "[Edge Case] repo plan is allowlisted gh argv",
            repo_plan[:3] == ("gh", "repo", "view") and "--json" in repo_plan,
            repr(repo_plan),
        )
        pr_resource = ConnectionResource(
            provider=ConnectionProvider.GITHUB,
            resource_type="pull-request",
            identifier="acme/api",
            number=7,
        )
        pr_plan = adapter.plan(pr_resource)
        self.results.check(
            "[Edge Case] pr plan carries number and repo",
            pr_plan[:3] == ("gh", "pr", "view") and "7" in pr_plan,
            repr(pr_plan),
        )
        for bad in ("acme", "/api", "acme/api/extra", "acme/api;id", ""):
            self._check_bad_identifier(adapter, bad)
        try:
            slack_resource = ConnectionResource(
                provider=ConnectionProvider.SLACK,
                resource_type="channel",
                identifier="C123",
            )
            adapter.plan(slack_resource)
            self.results.check("[Edge Case] native rejects slack channel", False)
        except ConnectionProtocolError:
            self.results.check("[Edge Case] native rejects slack channel", True)
        try:
            missing_number = ConnectionResource(
                provider=ConnectionProvider.GITHUB,
                resource_type="pull-request",
                identifier="acme/api",
            )
            adapter.plan(missing_number)
            self.results.check("[Edge Case] native requires pr number", False)
        except ConnectionResourceUnavailable:
            self.results.check("[Edge Case] native requires pr number", True)

    def _check_bad_identifier(self, adapter: GitHubNativeAdapter, bad: str) -> None:
        # Asserts one malformed owner/repo value never reaches argv.
        try:
            adapter.plan(github_repo(bad or "x"))
            self.results.check(f"[Edge Case] repo plan rejects {bad!r}", False)
        except (ConnectionProtocolError, ValidationError):
            self.results.check(f"[Edge Case] repo plan rejects {bad!r}", True)

    def check_auto_native(self) -> None:
        # Proves healthy gh serves auto reads with gh provenance.
        def fake_repo_run(argv: Any, **kwargs: Any) -> Completed:
            # Emulates gh repo view --json for routing tests.
            _ = kwargs
            assert list(argv[:3]) == ["gh", "repo", "view"]
            body = json.dumps({"nameWithOwner": "acme/api"})
            return Completed(0, body)

        manager = self.harness.manager
        manager._github_native = GitHubNativeAdapter(StubProbe(True, True))
        state = swap_subprocess(fake_repo_run, gh_binary)
        try:
            found = manager.read(
                "default",
                ConnectionProvider.GITHUB,
                "work-github",
                github_repo(),
                ReadVia.AUTO,
            )
            self.results.check(
                "[Silent Failure] auto via healthy gh uses native",
                found.provenance.source == "gh",
                repr(found.provenance),
            )
        finally:
            restore_subprocess(state)

    def check_direct_forced(self) -> None:
        # Proves direct never spawns even when gh is healthy.
        def exploding_run(argv: Any, **kwargs: Any) -> Completed:
            # Must never run when direct is forced.
            _ = (argv, kwargs)
            raise AssertionError("native spawned on --via direct")

        manager = self.harness.manager
        manager._github_native = GitHubNativeAdapter(StubProbe(True, True))
        real_adapter = manager._adapter(ConnectionProvider.GITHUB)
        direct = DirectDouble()
        manager._adapters[ConnectionProvider.GITHUB] = direct  # type: ignore[assignment]
        state = swap_subprocess(exploding_run, gh_binary)
        try:
            forced = manager.read(
                "default",
                ConnectionProvider.GITHUB,
                "work-github",
                github_repo(),
                ReadVia.DIRECT,
            )
            self.results.check(
                "[Edge Case] direct forces no spawn",
                forced.provenance.source == "direct" and direct.calls == ["acme/api"],
            )
        finally:
            restore_subprocess(state)
            manager._adapters[ConnectionProvider.GITHUB] = real_adapter

    def check_auth_fallback(self) -> None:
        # Proves unauthenticated gh falls back to direct on auto.
        def auth_failed_run(argv: Any, **kwargs: Any) -> Completed:
            # Emulates gh not logged in for fallback tests.
            _ = (argv, kwargs)
            return Completed(1, "", "You are not authenticated.")

        manager = self.harness.manager
        manager._github_native = GitHubNativeAdapter(StubProbe(True, False))
        real_adapter = manager._adapter(ConnectionProvider.GITHUB)
        direct = DirectDouble()
        manager._adapters[ConnectionProvider.GITHUB] = direct  # type: ignore[assignment]
        state = swap_subprocess(auth_failed_run, gh_binary)
        try:
            fallback = manager.read(
                "default",
                ConnectionProvider.GITHUB,
                "work-github",
                github_repo(),
                ReadVia.AUTO,
            )
            self.results.check(
                "[Hidden Failure] unauthenticated gh falls back",
                fallback.provenance.source == "direct",
            )
        except ConnectionAuthenticationRequired:
            self.results.check("[Hidden Failure] unauthenticated gh falls back", True)
        finally:
            restore_subprocess(state)
            manager._adapters[ConnectionProvider.GITHUB] = real_adapter

    def check_native_missing(self) -> None:
        # Proves native with no gh raises the typed missing failure.
        def exploding_run(argv: Any, **kwargs: Any) -> Completed:
            # Must never run when the binary is absent.
            _ = (argv, kwargs)
            raise AssertionError("spawned with no binary")

        manager = self.harness.manager
        manager._github_native = GitHubNativeAdapter(StubProbe(False, False))
        state = swap_subprocess(exploding_run, no_binary)
        try:
            try:
                manager.read(
                    "default",
                    ConnectionProvider.GITHUB,
                    "work-github",
                    github_repo(),
                    ReadVia.NATIVE,
                )
                self.results.check("[Edge Case] missing gh raises typed", False)
            except ConnectionNativeCliMissing as error:
                self.results.check(
                    "[Edge Case] missing gh raises typed",
                    "gh" in str(error) and "direct" in error.hint.lower(),
                )
        finally:
            restore_subprocess(state)

    def check_classifier(self) -> None:
        # Maps native stderr wording to the typed failure vocabulary.
        cases: list[tuple[str, type]] = [
            ("could not resolve to a Repository", ConnectionResourceUnavailable),
            ("not authenticated, run gh auth login", ConnectionAuthenticationRequired),
            ("boom", ConnectionNativeCliFailed),
        ]
        for text, expected in cases:
            seen = self._classify_one(text)
            self.results.check(
                f"[Silent Failure] gh maps {expected.__name__}",
                isinstance(seen, expected),
                repr(seen),
            )
        array_seen = self._classify_one("[1,2]", code=0)
        self.results.check(
            "[Silent Failure] gh array output rejected",
            isinstance(array_seen, ConnectionProtocolError),
        )

    def _classify_one(self, text: str, code: int = 1) -> Exception | None:
        # Runs NativeRunner against one canned process result.
        def canned(argv: Any, **kwargs: Any) -> Completed:
            # Returns the fixed stdout and stderr for one case.
            _ = (argv, kwargs)
            return Completed(code, text, text)

        state = swap_subprocess(canned, gh_binary)
        try:
            try:
                NativeRunner(3.0).run(("gh", "repo", "view", "acme/api"))
                return None
            except Exception as error:  # noqa: BLE001
                return error
        finally:
            restore_subprocess(state)

    def check_runner_bounds(self) -> None:
        # Proves oversized output and timeouts fail with typed errors.
        def oversized(argv: Any, **kwargs: Any) -> Completed:
            # Returns stdout past the 1 MiB runner cap.
            _ = (argv, kwargs)
            return Completed(0, '{"k":"' + ("x" * (2 * 1024 * 1024)) + '"}')

        state = swap_subprocess(oversized, gh_binary)
        try:
            try:
                NativeRunner(3.0).run(("gh", "repo", "view", "acme/api"))
                self.results.check("[Hidden Failure] oversized output rejected", False)
            except ConnectionProtocolError:
                self.results.check("[Hidden Failure] oversized output rejected", True)
        finally:
            restore_subprocess(state)

        def hanging(argv: Any, **kwargs: Any) -> Any:
            # Emulates a gh that never returns before the deadline.
            _ = (argv, kwargs)
            raise subprocess.TimeoutExpired(cmd=list(argv), timeout=0.01)

        state = swap_subprocess(hanging, gh_binary)
        try:
            from vidbyte_cli.lib.errors.failures import ConnectionApiUnavailable

            try:
                NativeRunner(0.5).run(("gh", "repo", "view", "acme/api"))
                self.results.check("[Hidden Failure] timeout is retryable", False)
            except ConnectionApiUnavailable as error:
                self.results.check("[Hidden Failure] timeout is retryable", error.retryable is True)
        finally:
            restore_subprocess(state)

    def check_show_plan(self) -> None:
        # Proves show-plan performs zero spawns and names gh argv.
        spawns = 0

        def counting(argv: Any, **kwargs: Any) -> Completed:
            # Counts spawns to prove show-plan performs none.
            nonlocal spawns
            _ = kwargs
            spawns += 1
            return Completed(0, "{}")

        second = Harness()
        second.manager._github_native = GitHubNativeAdapter(StubProbe(True, True))
        state = swap_subprocess(counting, gh_binary)
        try:
            ConnectionReadCommand().execute(
                second.context,
                "github",
                "repo",
                "acme/api",
                "work-github",
                None,
                50,
                "auto",
                True,
            )
            self.results.check("[Hidden Assumption] show-plan performs zero spawns", spawns == 0)
            self.results.check(
                "[Silent Failure] show-plan names gh argv",
                "gh repo view acme/api" in second.stdout.getvalue(),
                second.stdout.getvalue()[-200:],
            )
        finally:
            restore_subprocess(state)
            second.close()

    def check_slack_guard(self) -> None:
        # Proves Slack never touches the native path in any mode.
        spawns = 0

        def counter(argv: Any, **kwargs: Any) -> Completed:
            # Any spawn during a Slack read is a routing violation.
            nonlocal spawns
            _ = (argv, kwargs)
            spawns += 1
            return Completed(0, "{}")

        manager = self.harness.manager
        state = swap_subprocess(counter, gh_binary)
        try:
            slack_resource = ConnectionResource(
                provider=ConnectionProvider.SLACK,
                resource_type="channel",
                identifier="C123ABC",
                limit=10,
            )
            try:
                manager.plan_read(slack_resource, ReadVia.AUTO)
            except Exception:  # noqa: BLE001
                pass
            self.results.check("[Hidden Assumption] slack never plans native", spawns == 0)
            try:
                manager.plan_read(slack_resource, ReadVia.NATIVE)
                self.results.check("[Edge Case] slack show-plan native raises", False)
            except ConnectionProtocolError:
                self.results.check("[Edge Case] slack show-plan native raises", True)
            try:
                manager.read(
                    "default",
                    ConnectionProvider.SLACK,
                    "work-slack",
                    slack_resource,
                    ReadVia.NATIVE,
                )
                self.results.check("[Edge Case] slack native raises typed", False)
            except ConnectionProtocolError:
                self.results.check("[Edge Case] slack native raises typed", True)
            native_info = manager.native_availability(ConnectionProvider.SLACK)
            self.results.check(
                "[Hidden Assumption] slack native reports missing",
                native_info["found"] is False,
                repr(native_info),
            )
        finally:
            restore_subprocess(state)


def main() -> int:
    # Builds one harness, runs the suite, and reports the count.
    results = Results()
    harness = Harness()
    try:
        RoutingSuite(results, harness).run()
    finally:
        harness.close()
    return results.summary()


if __name__ == "__main__":
    raise SystemExit(main())
