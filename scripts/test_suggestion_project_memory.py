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

from pydantic import BaseModel  # noqa: E402

from vidbyte_cli.lib.config import VidbytePaths  # noqa: E402
from vidbyte_cli.lib.errors.failures import (  # noqa: E402
    LocalDocumentInvalid,
    LocalFileWriteFailed,
    SuggestionProjectExists,
    SuggestionProjectNotFound,
    SuggestionProjectStateUnreadable,
    SuggestionProjectWriteFailed,
)
from vidbyte_cli.lib.files import LocalDocumentStore  # noqa: E402
from vidbyte_cli.services.suggestions.project import (  # noqa: E402
    ACCEPTED_FEEDBACK_KIND,
    PROJECT_CONTEXT_KIND,
    REJECTED_FEEDBACK_KIND,
    SuggestionFeedbackInput,
    SuggestionProject,
    SuggestionProjectCreateInput,
    SuggestionProjectKey,
)
from vidbyte_cli.types.suggestions import FeedbackType, SuggestionFeedback  # noqa: E402


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


class FailingDocuments(LocalDocumentStore):
    """Document store whose writes to one name fail, to exercise refused-write paths."""

    def __init__(self, root: Path, failing_name: str) -> None:
        # Only the named document fails, so earlier writes in the same mutation succeed.
        super().__init__(root)
        self._failing_name = failing_name

    def write(self, name: str | Path, document: BaseModel) -> Path:
        if str(name) == self._failing_name:
            raise LocalFileWriteFailed(Path(name).name, "the volume is full", OSError("full"))
        return super().write(name, document)


class SuggestionProjectMemorySuite:
    """Runs unit and public-CLI checks for the project-memory feature."""

    def __init__(self, results: Results, root: Path) -> None:
        # All direct project operations share one isolated platform path set.
        self.results = results
        self.root = root
        self.paths = self.paths_under(root)

    def run(self) -> None:
        # Exercises the general document store, then the project class, then the public CLI.
        self.check_documents()
        self.check_projects()
        self.check_cli()

    def check_documents(self) -> None:
        # The lib class is product-neutral, so it is proven with its own tiny model.
        results = self.results
        documents = LocalDocumentStore(self.root / "documents", max_bytes=64)
        results.check(
            "[Edge Case] absent document reads as None",
            documents.read("absent.json", SuggestionProjectKeyModel) is None,
        )
        documents.write("one.json", SuggestionProjectKeyModel(value="a"))
        results.check(
            "[Silent Failure] written document reads back through its model",
            documents.read("one.json", SuggestionProjectKeyModel)
            == SuggestionProjectKeyModel(value="a"),
        )
        for name in ("../escape.json", "/absolute.json"):
            results.check(
                "[Hidden Assumption] document names cannot leave the root",
                self.raises(lambda name=name: documents.path_of(name), LocalDocumentInvalid),
                name,
            )
        (documents.root / "big.json").write_text(json.dumps({"value": "x" * 100}), "utf-8")
        results.check(
            "[Hidden Failure] oversized document is refused before parsing",
            self.raises(
                lambda: documents.read("big.json", SuggestionProjectKeyModel), LocalDocumentInvalid
            ),
        )
        (documents.root / "wrong.json").write_text(json.dumps({"other": 1}), "utf-8")
        results.check(
            "[Hidden Failure] schema mismatch is invalid, not empty",
            self.raises(
                lambda: documents.read("wrong.json", SuggestionProjectKeyModel),
                LocalDocumentInvalid,
            ),
        )

    def check_projects(self) -> None:
        # Exercises creation, validation, ordering, feedback history, and preservation.
        results = self.results
        empty = SuggestionProject(self.paths_under(self.root / "empty"))
        results.check("[Edge Case] absent catalog lists as empty", empty.list_projects() == ())

        project = SuggestionProject(self.paths)
        demo = self.key("demo")
        created = project.create(SuggestionProjectCreateInput(demo, " Demo ", "A test project."))
        suggestions_dir = self.paths.suggestions_dir()
        catalog_path = suggestions_dir / "projects.json"
        memory_path = suggestions_dir / "projects" / "demo.json"
        results.check(
            "[Edge Case] first project creates linked documents",
            catalog_path.exists()
            and memory_path.exists()
            and created.memory_file == "projects/demo.json"
            and created.title == "Demo",
        )
        results.check(
            "[Silent Failure] project_exists and get_project agree with the catalog",
            project.project_exists(demo)
            and project.get_project(demo) == created
            and not project.project_exists(self.key("missing")),
        )
        largest = project.create(
            SuggestionProjectCreateInput(self.key("a" * 64), "t" * 200, "d" * 4000)
        )
        results.check(
            "[Edge Case] maximum key, title, and description lengths validate",
            len(largest.key) == 64
            and len(largest.title) == 200
            and len(largest.description) == 4000,
        )
        for value in ("../escape", "Upper", "with/slash", "_leading", "a" * 65):
            results.check(
                "[Hidden Assumption] unsafe project key is rejected",
                self.raises(lambda value=value: SuggestionProjectKey(value), ValueError),
                value,
            )
        for title, description in (("", "d"), ("t", "   "), ("t" * 201, "d")):
            results.check(
                "[Edge Case] empty or oversized title and description are rejected",
                self.raises(
                    lambda title=title, description=description: SuggestionProjectCreateInput(
                        demo, title, description
                    ),
                    ValueError,
                ),
            )
        results.check(
            "[Edge Case] duplicate key does not overwrite",
            self.raises(
                lambda: project.create(SuggestionProjectCreateInput(demo, "Other", "Other")),
                SuggestionProjectExists,
            )
            and project.get_project(demo).title == "Demo",
        )
        project.create(SuggestionProjectCreateInput(self.key("zeta"), "Zeta", "Later"))
        results.check(
            "[Silent Failure] list is complete and key sorted",
            [item.key for item in project.list_projects()] == ["a" * 64, "demo", "zeta"],
        )

        original = memory_path.read_text(encoding="utf-8")
        failing = SuggestionProject(self.paths)
        failing._documents = FailingDocuments(suggestions_dir, "projects/demo.json")
        results.check(
            "[Hidden Failure] failed memory write preserves prior document",
            self.raises(
                lambda: failing.record_feedback(
                    SuggestionFeedbackInput(demo, FeedbackType.ACCEPTED, "Keep JSON")
                ),
                SuggestionProjectWriteFailed,
            )
            and memory_path.read_text(encoding="utf-8") == original,
        )
        rollback = SuggestionProject(self.paths)
        rollback._documents = FailingDocuments(suggestions_dir, "projects.json")
        results.check(
            "[Hidden Failure] failed catalog publish removes the new memory file",
            self.raises(
                lambda: rollback.create(
                    SuggestionProjectCreateInput(self.key("rolled"), "Rolled", "Back")
                ),
                SuggestionProjectWriteFailed,
            )
            and not (suggestions_dir / "projects" / "rolled.json").exists()
            and not project.project_exists(self.key("rolled")),
        )

        first = project.record_feedback(
            SuggestionFeedbackInput(demo, FeedbackType.ACCEPTED, "Keep JSON")
        )
        second = project.record_feedback(
            SuggestionFeedbackInput(
                demo, FeedbackType.REJECTED, "Use MongoDB", "Too much infrastructure."
            )
        )
        feedback = project.get_project_feedback(demo)
        results.check(
            "[Silent Failure] feedback appends in chronological order",
            [item.type for item in feedback] == [FeedbackType.ACCEPTED, FeedbackType.REJECTED]
            and first.reason is None
            and second.reason == "Too much infrastructure.",
        )
        exact = project.record_feedback(
            SuggestionFeedbackInput(
                demo, FeedbackType.ACCEPTED, "  Keep spacing  ", "  Exact reason  "
            )
        )
        results.check(
            "[Silent Failure] feedback text remains verbatim",
            exact.suggestion == "  Keep spacing  " and exact.reason == "  Exact reason  ",
        )
        for suggestion, reason in (("   ", None), ("x" * 8193, None), ("ok", "r" * 8193)):
            results.check(
                "[Edge Case] blank or oversized feedback is rejected",
                self.raises(
                    lambda suggestion=suggestion, reason=reason: SuggestionFeedbackInput(
                        demo, FeedbackType.REJECTED, suggestion, reason
                    ),
                    ValueError,
                ),
            )

        fields = project.context_fields(demo)
        results.check(
            "[Silent Failure] context fields carry metadata and both feedback kinds",
            fields[PROJECT_CONTEXT_KIND] == project.project_metadata(demo)
            and len(fields[ACCEPTED_FEEDBACK_KIND]) == 2
            and fields[REJECTED_FEEDBACK_KIND]
            == ("Rejected suggestion: Use MongoDB\nReason: Too much infrastructure.",),
        )
        results.check(
            "[Hidden Assumption] rejected context text recovers the verbatim suggestion",
            SuggestionFeedback.suggestion_from_context(fields[REJECTED_FEEDBACK_KIND][0])
            == "Use MongoDB",
        )
        results.check(
            "[Hidden Failure] unknown project is not created implicitly",
            self.raises(
                lambda: project.get_project_feedback(self.key("missing")),
                SuggestionProjectNotFound,
            )
            and not (suggestions_dir / "projects" / "missing.json").exists(),
        )

        memory_path.write_text(
            json.dumps({"schema_version": 1, "project_key": "other", "feedback": []}),
            encoding="utf-8",
        )
        results.check(
            "[Silent Failure] mismatched memory key is rejected",
            self.raises(
                lambda: project.get_project_feedback(demo), SuggestionProjectStateUnreadable
            ),
        )
        memory_path.unlink()
        results.check(
            "[Silent Failure] missing linked memory is not read as empty history",
            self.raises(
                lambda: project.get_project_feedback(demo), SuggestionProjectStateUnreadable
            ),
        )
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
        results.check(
            "[Hidden Assumption] linked path cannot escape the suggestions directory",
            self.raises(
                lambda: project.get_project_feedback(demo), SuggestionProjectStateUnreadable
            ),
        )
        catalog_path.write_text(json.dumps({"schema_version": 2, "projects": []}), "utf-8")
        results.check(
            "[Hidden Failure] unsupported catalog schema is unreadable state",
            self.raises(project.list_projects, SuggestionProjectStateUnreadable),
        )

    def check_cli(self) -> None:
        # Exercises command registration, envelopes, project context, and failures.
        results = self.results
        with tempfile.TemporaryDirectory(prefix="vidbyte-project-cli-") as temporary:
            root = Path(temporary)
            suggest = ["--json", "agents", "suggest"]
            created = self.run_cli(
                root,
                [
                    *suggest,
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
            results.check(
                "[Edge Case] project create works through public CLI",
                created.returncode == 0
                and self.document(created.stdout).get("kind") == "suggestions.project.created",
                created.stderr,
            )
            listed = self.run_cli(root, [*suggest, "project", "list"])
            projects = self.data(listed.stdout).get("projects", [])
            results.check(
                "[Silent Failure] project list returns created project",
                listed.returncode == 0
                and isinstance(projects, list)
                and projects[0].get("key") == "cli",
            )
            accepted = self.run_cli(
                root,
                [
                    *suggest,
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
                    *suggest,
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
                accepted.stderr + rejected.stderr,
            )
            unknown = self.run_cli(
                root,
                [
                    *suggest,
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
                and "INVALID_ARGUMENT" in unknown.stderr,
                unknown.stderr,
            )
            run = [*suggest, "run", "--goal", "Choose the next CLI improvement", "--dry-run"]
            project_run = self.run_cli(root, [*run, "--project", "cli"])
            project_data = self.data(project_run.stdout)
            manifest = project_data.get("context_manifest", [])
            kinds = [item.get("kind") for item in manifest] if isinstance(manifest, list) else []
            capture = project_data.get("feedback_capture") or {}
            results.check(
                "[Silent Failure] project run includes memory and capture instructions",
                project_run.returncode == 0
                and project_data.get("project_key") == "cli"
                and PROJECT_CONTEXT_KIND in kinds
                and ACCEPTED_FEEDBACK_KIND in kinds
                and REJECTED_FEEDBACK_KIND in kinds
                and isinstance(capture, dict)
                and capture.get("project_key") == "cli",
                project_run.stderr,
            )
            stateless = self.run_cli(root, run)
            stateless_data = self.data(stateless.stdout)
            results.check(
                "[Hidden Assumption] stateless run does not load project memory",
                stateless.returncode == 0
                and stateless_data.get("project_key") is None
                and stateless_data.get("feedback_capture") is None,
                stateless.stderr,
            )
            malformed_key = self.run_cli(root, [*run, "--project", "Not/Valid"])
            results.check(
                "[Hidden Failure] malformed run project key is a usage error",
                malformed_key.returncode == 2 and malformed_key.stdout == "",
                malformed_key.stderr,
            )
            catalogs = list(root.rglob("projects.json"))
            if catalogs:
                catalogs[0].write_text("{not-json", encoding="utf-8")
            malformed = self.run_cli(root, [*suggest, "project", "list"])
            results.check(
                "[Hidden Failure] malformed catalog returns typed error",
                len(catalogs) == 1
                and malformed.returncode == 1
                and malformed.stdout == ""
                and "OPERATION_FAILED" in malformed.stderr,
                malformed.stderr,
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

    def data(self, text: str) -> dict[str, object]:
        # The envelope's data object, or empty when the command produced no result.
        data = self.document(text).get("data")
        return data if isinstance(data, dict) else {}

    def key(self, value: str) -> SuggestionProjectKey:
        return SuggestionProjectKey(value)

    def raises(self, action: object, expected: type[BaseException]) -> bool:
        # True only when the call raises the expected type, so a silent success fails the check.
        assert callable(action)
        try:
            action()
        except expected:
            return True
        return False

    @staticmethod
    def paths_under(root: Path) -> VidbytePaths:
        return VidbytePaths(
            config_root=root / "config",
            cache_root=root / "cache",
            state_root=root / "state",
            data_root=root / "data",
            legacy_root=root / "legacy",
        )


class SuggestionProjectKeyModel(BaseModel):
    """Minimal document model proving LocalDocumentStore is independent of suggestions."""

    value: str


def main() -> int:
    # Creates one temporary root so all direct tests are disposable.
    with tempfile.TemporaryDirectory(prefix="vidbyte-project-memory-") as temporary:
        results = Results()
        SuggestionProjectMemorySuite(results, Path(temporary)).run()
        return results.summary()


if __name__ == "__main__":
    raise SystemExit(main())
