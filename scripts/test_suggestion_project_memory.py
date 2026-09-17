"""Deterministic verification for local suggestion projects and feedback memory.

Run with `python scripts/test_suggestion_project_memory.py`, or through the canonical CI gate.
The suite uses temporary paths and subprocesses with isolated homes, so it never reads or writes
the developer's real Vidbyte state and never calls a model provider.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

_REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPOSITORY_ROOT / "src"))

from vidbyte_cli.lib.config import VidbytePaths  # noqa: E402
from vidbyte_cli.services.suggestions.project_store import (  # noqa: E402
    ProjectAlreadyExistsError,
    ProjectNotFoundError,
    SuggestionProjectStore,
)
from vidbyte_cli.types.suggestions import FeedbackType  # noqa: E402


class Results:
    """Collects one PASS/FAIL line per test and decides the process status."""

    def __init__(self) -> None:
        # Counts accumulate in the order the suite exercises behavior.
        self.passed = 0
        self.failed = 0

    def check(self, name: str, condition: bool, detail: str = "") -> None:
        # Prints immediately so a failure remains associated with its exact test case.
        if condition:
            self.passed += 1
            print(f"PASS: {name}")
            return
        self.failed += 1
        suffix = f" - {detail}" if detail else ""
        print(f"FAIL: {name}{suffix}", file=sys.stderr)

    def summary(self) -> int:
        # Returns a failing process status whenever one case did not hold.
        total = self.passed + self.failed
        print(f"\n{self.passed}/{total} tests passed")
        return 1 if self.failed else 0


class FailingWriter:
    """Test double that forces the store to exercise its failed-write path."""

    def write(self, path: Path, content: bytes, *, mode: int = 0o600) -> None:
        # Raises before changing either destination or temporary state.
        raise OSError("simulated write failure")


class SuggestionProjectMemorySuite:
    """Runs unit and public-CLI checks for the project-memory feature."""

    def __init__(self, results: Results, root: Path) -> None:
        # All direct store operations share one isolated platform path set.
        self.results = results
        self.root = root
        self.paths = VidbytePaths(
            config_root=root / "config",
            cache_root=root / "cache",
            state_root=root / "state",
            data_root=root / "data",
            legacy_root=root / "legacy",
        )

    def run(self) -> None:
        # Executes unit storage checks before fresh-process command checks.
        self.check_storage()
        self.check_cli()

    def check_storage(self) -> None:
        # Exercises document creation, validation, ordering, and preservation.
        results = self.results
        empty_root = self.root / "empty"
        empty_paths = VidbytePaths(
            config_root=empty_root / "config",
            cache_root=empty_root / "cache",
            state_root=empty_root / "state",
            data_root=empty_root / "data",
            legacy_root=empty_root / "legacy",
        )
        empty_store = SuggestionProjectStore(empty_paths)
        results.check("[Edge Case] absent catalog lists as empty", empty_store.list() == ())

        project = SuggestionProjectStore(self.paths).create("demo", "Demo", "A test project.")
        catalog_path = self.paths.suggestion_projects_file()
        memory_path = self.paths.suggestion_project_memory_dir() / "demo.json"
        results.check(
            "[Edge Case] first project creates linked documents",
            catalog_path.exists()
            and memory_path.exists()
            and project.memory_file == "projects/demo.json",
        )
        catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
        results.check(
            "[Silent Failure] catalog stores the complete project link",
            catalog["projects"][0]["key"] == "demo"
            and catalog["projects"][0]["title"] == "Demo"
            and catalog["projects"][0]["description"] == "A test project."
            and catalog["projects"][0]["memory_file"] == "projects/demo.json",
        )

        largest = SuggestionProjectStore(self.paths).create(
            "a" * 64,
            "t" * 200,
            "d" * 4000,
        )
        results.check(
            "[Edge Case] maximum key, title, and description lengths validate",
            len(largest.key) == 64
            and len(largest.title) == 200
            and len(largest.description) == 4000,
        )

        for key in ("../escape", "Upper", "with/slash", "_leading"):
            try:
                SuggestionProjectStore(self.paths).create(key, "Title", "Description")
                valid = False
            except ValueError:
                valid = True
            results.check("[Hidden Assumption] unsafe project key is rejected", valid, key)

        try:
            SuggestionProjectStore(self.paths).create("demo", "Other", "Other")
            duplicate = False
        except ProjectAlreadyExistsError:
            duplicate = True
        results.check("[Edge Case] duplicate key does not overwrite", duplicate)

        SuggestionProjectStore(self.paths).create("zeta", "Zeta", "Later")
        listed = SuggestionProjectStore(self.paths).list()
        results.check(
            "[Silent Failure] list is complete and key sorted",
            [item.key for item in listed] == ["a" * 64, "demo", "zeta"],
        )

        original = memory_path.read_text(encoding="utf-8")
        failing = SuggestionProjectStore(self.paths, FailingWriter())
        try:
            failing.append_feedback("demo", FeedbackType.ACCEPTED, "Keep JSON", None)
            write_failed = False
        except OSError:
            write_failed = True
        results.check(
            "[Hidden Failure] failed memory write preserves prior document",
            write_failed and memory_path.read_text(encoding="utf-8") == original,
        )

        store = SuggestionProjectStore(self.paths)
        first = store.append_feedback("demo", FeedbackType.ACCEPTED, "Keep JSON", None)
        second = store.append_feedback(
            "demo", FeedbackType.REJECTED, "Use MongoDB", "Too much infrastructure."
        )
        memory = store.load_memory("demo")
        results.check(
            "[Silent Failure] feedback appends in chronological order",
            [item.type for item in memory.feedback]
            == [FeedbackType.ACCEPTED, FeedbackType.REJECTED]
            and first.reason is None
            and second.reason == "Too much infrastructure.",
        )
        results.check(
            "[Hidden Assumption] omitted reason remains null",
            memory.feedback[0].reason is None,
        )
        exact = store.append_feedback(
            "demo", FeedbackType.ACCEPTED, "  Keep spacing  ", "  Exact reason  "
        )
        results.check(
            "[Silent Failure] feedback text remains verbatim",
            exact.suggestion == "  Keep spacing  " and exact.reason == "  Exact reason  ",
        )
        store.append_feedback("demo", FeedbackType.REJECTED, "Use MongoDB", "Try again later.")
        results.check(
            "[Edge Case] repeated feedback remains explicit history",
            len(store.load_memory("demo").feedback) == 4,
        )

        try:
            store.load_memory("missing")
            missing = False
        except ProjectNotFoundError:
            missing = True
        results.check("[Hidden Failure] unknown project is not created implicitly", missing)

        memory_path.write_text(
            json.dumps({"schema_version": 1, "project_key": "other", "feedback": []}),
            encoding="utf-8",
        )
        try:
            store.load_memory("demo")
            mismatch = False
        except ValueError:
            mismatch = True
        results.check("[Silent Failure] mismatched memory key is rejected", mismatch)

        catalog_path.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "projects": [
                        {
                            "key": "demo",
                            "title": "Demo",
                            "description": "A test project.",
                            "memory_file": "../outside.json",
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )
        try:
            store.load_memory("demo")
            traversal = False
        except ValueError:
            traversal = True
        results.check("[Hidden Assumption] linked path cannot escape project directory", traversal)

    def check_cli(self) -> None:
        # Exercises command registration, envelopes, project context, and failures.
        results = self.results
        with tempfile.TemporaryDirectory(prefix="vidbyte-project-cli-") as temporary:
            root = Path(temporary)
            created = self.run_cli(
                root,
                [
                    "--json",
                    "agents",
                    "suggest",
                    "project",
                    "create",
                    "--key",
                    "cli",
                    "--title",
                    "CLI",
                    "--description",
                    "CLI project",
                ],
            )
            created_doc = self.document(created.stdout)
            results.check(
                "[Edge Case] project create works through public CLI",
                created.returncode == 0
                and created_doc.get("kind") == "suggestions.project.created",
            )
            listed = self.run_cli(root, ["--json", "agents", "suggest", "project", "list"])
            listed_doc = self.document(listed.stdout)
            projects = listed_doc.get("data", {}).get("projects", [])
            results.check(
                "[Silent Failure] project list returns created project",
                listed.returncode == 0 and projects[0].get("key") == "cli",
            )
            accepted = self.run_cli(
                root,
                [
                    "--json",
                    "agents",
                    "suggest",
                    "feedback",
                    "accept",
                    "--project",
                    "cli",
                    "--suggestion",
                    "Keep the local JSON design",
                ],
            )
            rejected = self.run_cli(
                root,
                [
                    "--json",
                    "agents",
                    "suggest",
                    "feedback",
                    "reject",
                    "--project",
                    "cli",
                    "--suggestion",
                    "Use MongoDB",
                    "--reason",
                    "No backend is needed.",
                ],
            )
            results.check(
                "[Edge Case] feedback commands return recorded envelopes",
                accepted.returncode == 0
                and rejected.returncode == 0
                and self.document(accepted.stdout).get("kind") == "suggestions.feedback.recorded"
                and self.document(rejected.stdout).get("kind") == "suggestions.feedback.recorded",
            )
            unknown = self.run_cli(
                root,
                [
                    "--json",
                    "agents",
                    "suggest",
                    "feedback",
                    "reject",
                    "--project",
                    "missing",
                    "--suggestion",
                    "No project",
                ],
            )
            results.check(
                "[Hidden Failure] unknown-project feedback writes nothing",
                unknown.returncode == 2
                and unknown.stdout == ""
                and '"code":"INVALID_ARGUMENT"' in unknown.stderr,
            )
            project_run = self.run_cli(
                root,
                [
                    "--json",
                    "--no-input",
                    "agents",
                    "suggest",
                    "run",
                    "--project",
                    "cli",
                    "--goal",
                    "Choose the next CLI improvement",
                    "--count",
                    "1",
                ],
            )
            project_doc = self.document(project_run.stdout)
            project_data = project_doc.get("data", {})
            kinds = [item.get("kind") for item in project_data.get("context_manifest", [])]
            results.check(
                "[Silent Failure] project run includes memory and capture instructions",
                project_run.returncode == 0
                and project_data.get("project_key") == "cli"
                and "project" in kinds
                and "accepted-feedback" in kinds
                and "rejected-feedback" in kinds
                and project_data.get("feedback_capture", {}).get("project_key") == "cli",
            )
            stateless = self.run_cli(
                root,
                [
                    "--json",
                    "--no-input",
                    "agents",
                    "suggest",
                    "run",
                    "--goal",
                    "Choose the next CLI improvement",
                    "--count",
                    "1",
                ],
            )
            stateless_data = self.document(stateless.stdout).get("data", {})
            results.check(
                "[Hidden Assumption] stateless run does not load project memory",
                stateless.returncode == 0
                and stateless_data.get("project_key") is None
                and stateless_data.get("feedback_capture") is None,
            )
            malformed_path = (
                root
                / "home"
                / "AppData"
                / "Local"
                / "Vidbyte"
                / "vidbyte-cli"
                / "suggestions"
                / "projects.json"
            )
            malformed_path.write_text("{not-json", encoding="utf-8")
            malformed = self.run_cli(root, ["--json", "agents", "suggest", "project", "list"])
            results.check(
                "[Hidden Failure] malformed catalog returns typed error",
                malformed.returncode == 1
                and malformed.stdout == ""
                and '"code":"OPERATION_FAILED"' in malformed.stderr,
            )
            help_result = self.run_cli(root, ["agents", "suggest", "feedback", "reject", "--help"])
            results.check(
                "[Hidden Assumption] feedback help works without credentials",
                help_result.returncode == 0 and len(help_result.stdout.split(".")) >= 4,
            )

    def run_cli(self, root: Path, args: list[str]) -> subprocess.CompletedProcess[str]:
        # Runs the public module with every local-state root isolated beneath one temp path.
        environment = dict(os.environ)
        source = str(_REPOSITORY_ROOT / "src")
        existing = environment.get("PYTHONPATH")
        environment["PYTHONPATH"] = f"{source}{os.pathsep}{existing}" if existing else source
        home = root / "home"
        environment["HOME"] = str(home)
        environment["USERPROFILE"] = str(home)
        environment["LOCALAPPDATA"] = str(root / "local")
        environment["APPDATA"] = str(root / "roaming")
        environment["XDG_CONFIG_HOME"] = str(root / "config")
        environment["XDG_CACHE_HOME"] = str(root / "cache")
        environment["XDG_DATA_HOME"] = str(root / "data")
        environment["XDG_STATE_HOME"] = str(root / "state")
        environment["PYTHON_KEYRING_BACKEND"] = "keyring.backends.null.Keyring"
        for name in [key for key in environment if key.startswith("VIDBYTE_")]:
            del environment[name]
        return subprocess.run(
            [sys.executable, "-m", "vidbyte_cli", *args],
            capture_output=True,
            text=True,
            check=False,
            env=environment,
        )

    def document(self, text: str) -> dict[str, object]:
        # Parses a result envelope while letting the individual check decide validity.
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            return {}
        return parsed if isinstance(parsed, dict) else {}


def main() -> int:
    # Creates one temporary root so all direct tests are disposable.
    with tempfile.TemporaryDirectory(prefix="vidbyte-project-memory-") as temporary:
        results = Results()
        SuggestionProjectMemorySuite(results, Path(temporary)).run()
        return results.summary()


if __name__ == "__main__":
    raise SystemExit(main())
