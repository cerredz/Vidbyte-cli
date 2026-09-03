"""Verification that the CLI offers exactly the commands the shipped API can answer.

Run with `python scripts/test_research_only_surface.py`, or via `scripts/run_ci.py`. Three
kinds of case: the command tree is inspected in-process, structural claims are proved by
attempting real imports, and process contracts run through `python -m vidbyte_cli` in a fresh
process against an isolated state root. Nothing here reaches the network.

The negative space is the point. A deletion this size fails by leaving something behind — a
module still importable, a docstring still naming a deleted symbol, an error path that
silently changes encoding — so most cases assert absence rather than presence.
"""

from __future__ import annotations

import importlib
import json
import os
import subprocess
import sys
from pathlib import Path

_REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPOSITORY_ROOT / "src"))

import click  # noqa: E402

from vidbyte_cli.commands import register_all_commands  # noqa: E402
from vidbyte_cli.lib.api.client import ApiClient  # noqa: E402
from vidbyte_cli.lib.api.response import ResponseDecoder  # noqa: E402
from vidbyte_cli.lib.errors import codes, failures  # noqa: E402
from vidbyte_cli.lib.runtime.context import ApplicationContext  # noqa: E402
from vidbyte_cli.lib.runtime.options import RootInspection  # noqa: E402

EXPECTED_TOP_LEVEL = {"config", "doctor", "login", "logout", "research", "runtime", "whoami"}
EXPECTED_RESEARCH = {"add", "resume", "start", "status", "thread", "threads", "watch"}
EXPECTED_RUNTIME = {"adversarial-team", "doctor", "list"}
# Every module that existed only to serve a backend route that was never built.
DELETED_MODULES = (
    "vidbyte_cli.commands.harness",
    "vidbyte_cli.commands.auth.connect_github",
    "vidbyte_cli.harnesses",
    "vidbyte_cli.lib.harness",
    "vidbyte_cli.lib.git",
    "vidbyte_cli.lib.api.endpoints.harness",
    "vidbyte_cli.lib.output.render",
    "vidbyte_cli.lib.output.logger",
    "vidbyte_cli.types.harness",
    "vidbyte_cli.types.manifest",
)
DELETED_FAILURES = ("NotImplementedFeature", "HarnessInvocationFailed", "MissingHarnessArgument")
# Symbols no surviving source file may name, in code or in authored prose. `trace` strings are
# the real risk: they are static text no linter or type checker will ever flag as stale.
FORBIDDEN_SOURCE_TOKENS = ("harness", "HarnessRun", "RepoInspector", "NotImplementedFeature")


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

    def summary(self) -> int:
        total = self.passed + self.failed
        print(f"\n{self.passed}/{total} tests passed")
        return 1 if self.failed else 0


class CliProcess:
    """Runs the CLI through its public module entry point against an isolated state root."""

    def __init__(self) -> None:
        # A scratch root shared with smoke.py's convention, so neither suite can read a
        # developer's real profile or prompt for a keychain unlock in CI.
        self._root = _REPOSITORY_ROOT / ".surface-state"

    def run(self, args: list[str]) -> subprocess.CompletedProcess[str]:
        # Invokes `python -m vidbyte_cli` with every VIDBYTE_* override stripped.
        return subprocess.run(
            [sys.executable, "-m", "vidbyte_cli", *args],
            capture_output=True,
            text=True,
            check=False,
            env=self._environment(),
        )

    def run_code(self, code: str) -> subprocess.CompletedProcess[str]:
        # Runs one snippet in a fresh interpreter, for import-boundary assertions.
        return subprocess.run(
            [sys.executable, "-c", code],
            capture_output=True,
            text=True,
            check=False,
            env=self._environment(),
        )

    def _environment(self) -> dict[str, str]:
        # Redirects every platformdirs root and disables the keyring backend.
        environment = dict(os.environ)
        source = str(_REPOSITORY_ROOT / "src")
        existing = environment.get("PYTHONPATH")
        environment["PYTHONPATH"] = f"{source}{os.pathsep}{existing}" if existing else source
        for name in [key for key in environment if key.startswith("VIDBYTE_")]:
            del environment[name]
        environment.update(
            {
                "HOME": str(self._root / "home"),
                "USERPROFILE": str(self._root / "home"),
                "XDG_CONFIG_HOME": str(self._root / "config"),
                "XDG_CACHE_HOME": str(self._root / "cache"),
                "XDG_DATA_HOME": str(self._root / "data"),
                "XDG_STATE_HOME": str(self._root / "state"),
                "LOCALAPPDATA": str(self._root / "local"),
                "APPDATA": str(self._root / "roaming"),
                "PYTHON_KEYRING_BACKEND": "keyring.backends.null.Keyring",
            }
        )
        return environment


class SurfaceSuite:
    """Every case from the design doc's testing plan, grouped by the claim it protects."""

    def __init__(self, results: Results) -> None:
        self.results = results
        self.cli = CliProcess()
        self.program = self._build_program()

    def run(self) -> None:
        for group in (
            self.check_command_surface,
            self.check_module_structure,
            self.check_source_prose,
            self.check_surviving_behavior,
            self.check_import_boundaries,
            self.check_help_tree,
        ):
            group()

    def _build_program(self) -> click.Group:
        # The same tree CliApplication builds, without running an invocation through it.
        program = click.Group(name="vidbyte-cli")
        register_all_commands(program)
        return program

    def _subcommands(self, name: str) -> set[str]:
        group = self.program.commands[name]
        assert isinstance(group, click.Group)
        return set(group.commands)

    # ---- command surface -------------------------------------------------------------

    def check_command_surface(self) -> None:
        # The exact set matters in both directions: a survivor is a broken promise, and a
        # missing research command is an over-deletion that help output would not reveal.
        results = self.results
        actual = set(self.program.commands)
        results.check(
            "the CLI exposes exactly seven top-level commands",
            actual == EXPECTED_TOP_LEVEL,
            f"got {sorted(actual)}",
        )
        research = self._subcommands("research")
        results.check(
            "research exposes exactly seven subcommands",
            research == EXPECTED_RESEARCH,
            f"got {sorted(research)}",
        )
        results.check(
            "config exposes exactly get and set",
            self._subcommands("config") == {"get", "set"},
        )
        results.check(
            "runtime exposes exactly the scaffolded local commands",
            self._subcommands("runtime") == EXPECTED_RUNTIME,
        )
        results.check(
            "registration returns nothing, because no subtree is attached later",
            register_all_commands(click.Group(name="probe")) is None,
        )
        for args in (
            ["harness"],
            ["harness", "catalog"],
            ["harness", "software-engineering", "fix", "task"],
            ["connect", "github"],
        ):
            result = self.cli.run(args)
            label = " ".join(args)
            results.check(
                f"`{label}` exits 2 as an unknown command",
                result.returncode == 2,
                f"exit {result.returncode}",
            )
            results.check(
                f"`{label}` reports INVALID_ARGUMENT, never NOT_IMPLEMENTED",
                "INVALID_ARGUMENT" in result.stderr and "NOT_IMPLEMENTED" not in result.stderr,
            )

    # ---- module structure ------------------------------------------------------------

    def check_module_structure(self) -> None:
        # An importable leftover keeps dead code alive behind a deleted source file.
        results = self.results
        for module in DELETED_MODULES:
            results.check(f"{module} is not importable", not self._importable(module))
        for name in DELETED_FAILURES:
            results.check(
                f"failures.{name} is gone",
                not hasattr(failures, name),
            )
        results.check(
            "CliErrorCode.NOT_IMPLEMENTED stays in the published enum",
            hasattr(codes.CliErrorCode, "NOT_IMPLEMENTED"),
            "removing a shipped code string breaks any agent matching on it",
        )
        results.check(
            "ApplicationContext exposes no harness_context",
            not hasattr(ApplicationContext, "harness_context"),
        )
        results.check(
            "ApplicationContext takes no harness_factory",
            "harness_factory" not in ApplicationContext.__init__.__code__.co_varnames,
        )
        fields = set(RootInspection.__dataclass_fields__)
        results.check(
            "RootInspection carries only values and exits_before_command",
            fields == {"values", "exits_before_command"},
            f"got {sorted(fields)}",
        )
        results.check("ApiClient exposes no get_list", not hasattr(ApiClient, "get_list"))
        results.check("ResponseDecoder exposes no many", not hasattr(ResponseDecoder, "many"))

    def _importable(self, module: str) -> bool:
        # True only if the module genuinely loads; a stale .pyc would still count as present.
        try:
            importlib.import_module(module)
        except ImportError:
            return False
        return True

    # ---- authored prose --------------------------------------------------------------

    def check_source_prose(self) -> None:
        # The sweep that catches what nothing else can: a `trace` or docstring still naming a
        # deleted symbol. Agents read `trace` to repair their own invocation, so a stale one
        # sends them at a call path that no longer exists.
        results = self.results
        offenders: list[str] = []
        for path in sorted((_REPOSITORY_ROOT / "src").rglob("*.py")):
            text = path.read_text(encoding="utf-8").lower()
            hits = [token for token in FORBIDDEN_SOURCE_TOKENS if token.lower() in text]
            if hits:
                offenders.append(f"{path.relative_to(_REPOSITORY_ROOT)}: {', '.join(hits)}")
        results.check(
            "no source file names a deleted symbol, in code or prose",
            not offenders,
            "; ".join(offenders),
        )
        trace = failures.AuthenticationRequired().trace or ""
        results.check(
            "AuthenticationRequired.trace names a call path that still exists",
            "ApplicationContext.api_client" in trace and "BaseHarness" not in trace,
            trace,
        )

    # ---- surviving behavior ----------------------------------------------------------

    def check_surviving_behavior(self) -> None:
        # Everything the deletion must not have disturbed.
        results = self.results
        conflict = self.cli.run(["--json", "--format", "human", "doctor"])
        results.check(
            "--json with a conflicting --format still fails with exit 2",
            conflict.returncode == 2 and "INVALID_ARGUMENT" in conflict.stderr,
        )
        # The single most plausible regression: deleting attach_allowed could tempt
        # _invalid() into returning None, which downgrades this to human prose on stderr.
        for label, args in (
            ("invalid root syntax", ["--format", "json", "--not-an-option"]),
            ("an unknown command", ["--format", "json", "not-a-command"]),
        ):
            result = self.cli.run(args)
            document = self._json_document(result.stderr)
            results.check(
                f"{label} after --format json still emits a machine error document",
                document.get("kind") == "error" and document.get("schema_version") == 1,
                result.stderr[:200],
            )
            data = document.get("data", {})
            results.check(
                f"{label} reports INVALID_ARGUMENT with exit_code 2",
                data.get("code") == "INVALID_ARGUMENT" and data.get("exit_code") == 2,
            )
            results.check(
                f"{label} keeps the agent-native fields",
                all(data.get(field) for field in ("description", "trace", "file_path")),
            )
        for args in (["--help"], ["--version"], ["research", "--help"]):
            result = self.cli.run(args)
            results.check(
                f"`{' '.join(args)}` exits 0 against an empty isolated home",
                result.returncode == 0,
                result.stderr[:200],
            )
        doctor = self.cli.run(["--json", "doctor"])
        emitted = [line for line in doctor.stdout.splitlines() if line.strip()]
        results.check(
            "--json doctor emits exactly one document despite configuring twice",
            doctor.returncode == 0 and len(emitted) == 1,
            f"{len(emitted)} lines",
        )
        # Local argument validation must still run before credentials are resolved, or a
        # typo would report AUTH_REQUIRED (4) and read as a login problem.
        bad_token = self.cli.run(["research", "thread", "not-a-share-token"])
        results.check(
            "a malformed thread token exits 2, not 4",
            bad_token.returncode == 2 and "INVALID_ARGUMENT" in bad_token.stderr,
            f"exit {bad_token.returncode}",
        )
        missing_auth = self.cli.run(["research", "thread", "11111111-1111-4111-8111-111111111111"])
        results.check(
            "a well-formed token with no credential exits 4",
            missing_auth.returncode == 4 and "AUTH_REQUIRED" in missing_auth.stderr,
            f"exit {missing_auth.returncode}",
        )

    def _json_document(self, serialized: str) -> dict[str, object]:
        try:
            document = json.loads(serialized)
        except json.JSONDecodeError:
            return {}
        return document if isinstance(document, dict) else {}

    # ---- import boundaries -----------------------------------------------------------

    def check_import_boundaries(self) -> None:
        # This change edits the import graph of every module on the help path.
        results = self.results
        boundaries = (
            (
                "importing vidbyte_cli pulls in neither click nor httpx",
                "import sys; import vidbyte_cli; "
                "assert 'click' not in sys.modules; assert 'httpx' not in sys.modules",
            ),
            (
                "importing vidbyte_cli.cli pulls in no httpx",
                "import sys; import vidbyte_cli.cli; assert 'httpx' not in sys.modules",
            ),
        )
        for label, code in boundaries:
            results.check(label, self.cli.run_code(code).returncode == 0)

    # ---- full help tree --------------------------------------------------------------

    def check_help_tree(self) -> None:
        # Rendering every help screen is what catches a registration that imports something
        # deleted: that failure would otherwise surface only on the one command a user ran.
        results = self.results
        failures_seen: list[str] = []
        for path in self._command_paths():
            result = self.cli.run([*path, "--help"])
            if result.returncode != 0:
                failures_seen.append(" ".join(path) or "<root>")
        results.check(
            "every command and subcommand renders help successfully",
            not failures_seen,
            ", ".join(failures_seen),
        )

    def _command_paths(self) -> list[list[str]]:
        # Every invocable path in the tree, root first, then groups, then their leaves.
        paths: list[list[str]] = [[]]
        for name, command in sorted(self.program.commands.items()):
            paths.append([name])
            if isinstance(command, click.Group):
                paths.extend([name, child] for child in sorted(command.commands))
        return paths


def main() -> int:
    results = Results()
    SurfaceSuite(results).run()
    return results.summary()


if __name__ == "__main__":
    raise SystemExit(main())
