"""Proves the persistence relocation is complete, and that the layering it restores holds.

Behavior is covered by `test-layered-runtime-admission-gate.py`. This script checks what a
half-finished move leaves behind: a stale module still importable, a prompt orphaned in the
old folder, a patch target hidden inside a string literal, a `package-data` glob pointing at
a package with no `.md` files, or a `lib/` module reaching into `services/`.
"""

from __future__ import annotations

import ast
import importlib
import importlib.util
import re
import sys
import tomllib
import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock

from vidbyte_cli.lib.errors.failures import RuntimeAdmissionNotVerified
from vidbyte_cli.lib.runtime_primitives.executor import RuntimeExecutor
from vidbyte_cli.lib.runtime_primitives.gate import RuntimeAdmissionGate
from vidbyte_cli.services.persistence.prompts.library import PersistencePrompts
from vidbyte_cli.services.persistence.runner import PersistenceRunner
from vidbyte_cli.services.persistence.session import PersistentCodexSession
from vidbyte_cli.types.runtime import (
    PersistenceSettings,
    PersistenceStrength,
    RuntimeAdmissionGrant,
    RuntimeAdmissionVerdict,
    RuntimeHost,
    RuntimeLaunchPlan,
)

_ROOT = Path(__file__).resolve().parents[1]
_PACKAGE = _ROOT / "src" / "vidbyte_cli"
_OLD_PACKAGE = _PACKAGE / "lib" / "runtime_primitives"
_NEW_PACKAGE = _PACKAGE / "services" / "persistence"
_MOVED_MODULE = "vidbyte_cli.lib.runtime_primitives.persistence"

# A task deliberately built out of everything a naive renderer mishandles.
_HOSTILE_TASK = "Fix {a} and %s and {{braces}}\r\nsecond line — café \\n literal  "


def _plan(capability: str = "runtime.persistence@1", host: RuntimeHost = RuntimeHost.CODEX):
    # One inert launch plan; nothing here touches PATH, the network, or a subprocess.
    return RuntimeLaunchPlan(
        capability_id=capability,
        host=host,
        executable=Path("codex"),
        working_directory=Path.cwd(),
        task="task",
    )


def _verdict(admitted: bool = True, capability: str = "runtime.persistence@1"):
    # A receipt shaped exactly as the gate would return it.
    return RuntimeAdmissionVerdict(
        admitted=admitted, admission_id="rta_1", capability_id=capability, reason=None
    )


def _python_files(root: Path) -> list[Path]:
    # Every module under one package root, so a sweep cannot miss a new file.
    return sorted(path for path in root.rglob("*.py") if "__pycache__" not in path.parts)


class RelocationContracts(unittest.TestCase):
    """The move left nothing behind and nothing dangling."""

    def test_session_and_runner_import_from_the_service(self) -> None:
        # The new home is the real one: both symbols resolve under services/persistence.
        service = "vidbyte_cli.services.persistence"
        self.assertEqual(PersistentCodexSession.__module__, f"{service}.session")
        self.assertEqual(PersistenceRunner.__module__, f"{service}.runner")

    def test_old_persistence_module_is_gone(self) -> None:
        # A leftover module would let a stale import keep working and hide a partial move.
        self.assertIsNone(importlib.util.find_spec(_MOVED_MODULE))
        with self.assertRaises(ModuleNotFoundError):
            importlib.import_module(_MOVED_MODULE)

    def test_no_markdown_remains_in_the_old_package(self) -> None:
        # An orphaned prompt still ships and still reads, so the file has to be gone.
        self.assertEqual(list(_OLD_PACKAGE.glob("*.md")), [])

    def test_shared_primitives_stayed_in_lib(self) -> None:
        # The split is the point: these five are shared and must not have travelled.
        names = {path.name for path in _python_files(_OLD_PACKAGE)}
        expected = {"__init__.py", "executor.py", "gate.py", "hosts.py", "planner.py"}
        self.assertEqual(names, expected | {"verification.py"})

    def test_no_source_or_script_names_the_old_module(self) -> None:
        # A patch target inside a string literal is invisible to imports and to mypy.
        offenders = []
        this_file = Path(__file__).resolve()
        for path in (*_python_files(_PACKAGE), *_python_files(_ROOT / "scripts")):
            if path.resolve() == this_file:
                continue
            if "runtime_primitives.persistence" in path.read_text(encoding="utf-8"):
                offenders.append(str(path.relative_to(_ROOT)))
        self.assertEqual(offenders, [])


class LayeringContracts(unittest.TestCase):
    """The dependency direction `services/README.md` states, enforced against the AST."""

    def _imported_roots(self, path: Path, package_depth: int) -> set[str]:
        # Resolves both absolute and relative imports to a top-level package under vidbyte_cli.
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        roots: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                parts = node.module.split(".")
                if parts[0] == "vidbyte_cli" and len(parts) > 1:
                    roots.add(parts[1])
            elif isinstance(node, ast.ImportFrom) and node.level:
                # `...x` from a module `package_depth` levels below vidbyte_cli names `x`.
                if node.level == package_depth and node.module:
                    roots.add(node.module.split(".")[0])
        return roots

    def test_no_module_under_lib_imports_a_service(self) -> None:
        # This is the coupling the whole change exists to remove.
        offenders = []
        for path in _python_files(_PACKAGE / "lib"):
            depth = len(path.relative_to(_PACKAGE).parts)
            if "services" in self._imported_roots(path, depth):
                offenders.append(str(path.relative_to(_ROOT)))
        self.assertEqual(offenders, [])

    def test_no_service_imports_a_command(self) -> None:
        # The other half of the documented one-way direction.
        offenders = []
        for path in _python_files(_PACKAGE / "services"):
            depth = len(path.relative_to(_PACKAGE).parts)
            if "commands" in self._imported_roots(path, depth):
                offenders.append(str(path.relative_to(_ROOT)))
        self.assertEqual(offenders, [])


class PromptContracts(unittest.TestCase):
    """The prompts moved without changing, and the loader fills them literally."""

    def setUp(self) -> None:
        self.prompts = PersistencePrompts()
        self.directory = _NEW_PACKAGE / "prompts"

    def test_system_prompt_matches_the_file_on_disk(self) -> None:
        # A whitespace change during the move would silently alter every paid run.
        stored = (self.directory / "persistence_system.md").read_text(encoding="utf-8")
        self.assertEqual(self.prompts.system_prompt(), stored)
        self.assertIn("Preserve the user's intent and constraints", stored)

    def test_turn_prompt_keeps_its_authored_opening(self) -> None:
        # The existing suite asserts this exact opening reaches the SDK; keep it here too.
        self.assertTrue(self.prompts.turn_prompt("x").startswith("Very good job, keep working"))

    def test_placeholder_is_filled_with_the_exact_task(self) -> None:
        # Braces, percent signs, CRLF, non-ASCII and trailing spaces must survive verbatim.
        rendered = self.prompts.turn_prompt(_HOSTILE_TASK)
        self.assertIn("Here is the original task in case your forgot " + _HOSTILE_TASK, rendered)

    def test_a_literal_placeholder_inside_the_task_is_not_re_expanded(self) -> None:
        # One pass over the template, so a task naming the token stays plain text.
        rendered = self.prompts.turn_prompt("see {{original_task}} above")
        self.assertEqual(rendered.count("{{original_task}}"), 1)
        self.assertIn("see {{original_task}} above", rendered)

    def test_no_unfilled_placeholder_survives_rendering(self) -> None:
        # An unreplaced token would be read by the model as instructions it cannot follow.
        self.assertNotIn("{{", self.prompts.turn_prompt("task"))
        self.assertNotIn("{{", self.prompts.system_prompt())

    def test_each_prompt_file_is_read_once_per_instance(self) -> None:
        # A 100-turn run must not re-read package data on every continuation.
        prompts = PersistencePrompts()
        for _ in range(5):
            prompts.turn_prompt("task")
            prompts.system_prompt()
        self.assertEqual(sorted(prompts._cache), ["persistence_system", "persistence_turn"])

    def test_resolution_does_not_depend_on_the_importing_module_name(self) -> None:
        # The anchor is a literal package path, so a re-imported copy still finds its files.
        spec = importlib.util.spec_from_file_location(
            "relocation_probe_library", self.directory / "library.py"
        )
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        self.assertEqual(module.PersistencePrompts().system_prompt(), self.prompts.system_prompt())

    def test_no_service_module_addresses_a_model(self) -> None:
        # Prompt text belongs in `.md` only; the field guide's own check, generalized.
        pattern = re.compile(r'"You are|Very good job, keep working|Work on the user')
        offenders = [
            str(path.relative_to(_ROOT))
            for path in _python_files(_PACKAGE / "services")
            if pattern.search(path.read_text(encoding="utf-8"))
        ]
        self.assertEqual(offenders, [])


class PackagingContracts(unittest.TestCase):
    """The prompts are declared as package data at their new path, and only there."""

    def setUp(self) -> None:
        self.pyproject = tomllib.loads((_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
        self.package_data = self.pyproject["tool"]["setuptools"]["package-data"]

    def test_new_glob_is_declared(self) -> None:
        # Without this the wheel ships no prompt and fails on its first paid turn.
        self.assertIn("services/persistence/prompts/*.md", self.package_data["vidbyte_cli"])

    def test_stale_key_is_removed(self) -> None:
        # The old package still exists, so a stale key would never fail the build.
        self.assertNotIn("vidbyte_cli.lib.runtime_primitives", self.package_data)

    def test_every_prompt_file_is_covered_by_the_glob(self) -> None:
        # A prompt added later under a name the glob misses would be dropped silently.
        self.assertEqual(
            sorted(path.name for path in (_NEW_PACKAGE / "prompts").glob("*.md")),
            ["persistence_system.md", "persistence_turn.md"],
        )

    def test_run_ci_asserts_the_new_wheel_paths(self) -> None:
        # The gate must look where the prompts now are, or it proves nothing.
        gate = (_ROOT / "scripts" / "run_ci.py").read_text(encoding="utf-8")
        self.assertIn("vidbyte_cli/services/persistence/prompts/{name}", gate)
        self.assertIn('("persistence_system.md", "persistence_turn.md")', gate)
        self.assertNotIn("vidbyte_cli/lib/runtime_primitives/{name}", gate)


class RunnerContracts(unittest.TestCase):
    """The moved boundary rejects exactly what the executor's version rejected."""

    def setUp(self) -> None:
        self.session = MagicMock(spec=PersistentCodexSession)
        self.runner = PersistenceRunner()
        self.settings = PersistenceSettings(strength=PersistenceStrength.TIER_1)

    def _run(self, plan: RuntimeLaunchPlan, verdict: RuntimeAdmissionVerdict) -> None:
        self.runner.run(plan, self.settings, self.session, verdict)

    def test_admitted_verdict_and_matching_plan_reach_the_session(self) -> None:
        # The positive path, so the negative assertions below cannot pass vacuously.
        self._run(_plan(), _verdict())
        self.session.run.assert_called_once()

    def test_unadmitted_verdict_never_calls_the_session(self) -> None:
        # Raising is not enough; the session must record no call at all.
        with self.assertRaises(RuntimeAdmissionNotVerified):
            self._run(_plan(), _verdict(admitted=False))
        self.session.run.assert_not_called()

    def test_capability_mismatch_between_verdict_and_plan_is_rejected(self) -> None:
        with self.assertRaises(RuntimeAdmissionNotVerified):
            self._run(_plan(), _verdict(capability="runtime.same-host-ensemble@1"))
        self.session.run.assert_not_called()

    def test_valid_receipt_for_another_product_cannot_open_this_path(self) -> None:
        # Verdict and plan agree with each other but name a different capability.
        plan = _plan(capability="runtime.adversarial-team@1")
        with self.assertRaises(RuntimeAdmissionNotVerified) as caught:
            self._run(plan, _verdict(capability="runtime.adversarial-team@1"))
        self.assertIn("persistence_plan_invalid", caught.exception.description)
        self.session.run.assert_not_called()

    def test_persistence_capability_on_a_non_codex_host_is_rejected(self) -> None:
        with self.assertRaises(RuntimeAdmissionNotVerified) as caught:
            self._run(_plan(host=RuntimeHost.CLAUDE), _verdict())
        self.assertIn("persistence_plan_invalid", caught.exception.description)
        self.session.run.assert_not_called()

    def test_blank_admission_id_is_rejected(self) -> None:
        verdict = RuntimeAdmissionVerdict(
            admitted=True, admission_id="   ", capability_id="runtime.persistence@1", reason=None
        )
        with self.assertRaises(RuntimeAdmissionNotVerified):
            self._run(_plan(), verdict)
        self.session.run.assert_not_called()

    def test_the_runner_delegates_to_the_shared_verdict_policy(self) -> None:
        # One policy, not two: a restated check here could drift from the executor's.
        executor = MagicMock(spec=RuntimeExecutor)
        PersistenceRunner(executor).run(_plan(), self.settings, self.session, _verdict())
        executor.require_verdict.assert_called_once()


class ExecutorContracts(unittest.TestCase):
    """The shared executor kept its own primitive and lost the product-specific one."""

    def test_execute_persistence_is_gone(self) -> None:
        # A surviving copy would be a second, unverified way to start a paid session.
        self.assertFalse(hasattr(RuntimeExecutor, "execute_persistence"))

    def test_verdict_check_is_public(self) -> None:
        # The service calls it by name, so it is part of the contract now.
        self.assertTrue(callable(RuntimeExecutor.require_verdict))

    def test_adversarial_team_still_denies_a_missing_verdict(self) -> None:
        # The collateral check: the primitive that stayed behind is unchanged.
        with self.assertRaises(RuntimeAdmissionNotVerified):
            RuntimeExecutor().execute_adversarial_team(_plan("runtime.adversarial-team@1"))

    def test_gate_still_admits_a_well_formed_persistence_receipt(self) -> None:
        # Proves the gate stayed in lib/ and still reaches persistence's price entry.
        now = datetime.now(UTC)
        grant = RuntimeAdmissionGrant(
            admission_id="rta_1",
            capability_id="runtime.persistence@1",
            charged_cents=2,
            execution_location="local",
            grant_token="payload.signature",
            admitted_at=now - timedelta(seconds=1),
            expires_at=now + timedelta(minutes=5),
        )
        verdict = RuntimeAdmissionGate().verify_online(_plan(), grant, grant)
        self.assertTrue(verdict.admitted)


class Reporter(unittest.TextTestResult):
    """Prints one PASS/FAIL line per test case, as the verification contract requires."""

    def addSuccess(self, test: unittest.TestCase) -> None:
        super().addSuccess(test)
        self.stream.write(f"PASS {test.id().split('.', 1)[1]}\n")

    def addFailure(self, test: unittest.TestCase, error: object) -> None:
        super().addFailure(test, error)  # type: ignore[arg-type]
        self.stream.write(f"FAIL {test.id().split('.', 1)[1]}\n")

    def addError(self, test: unittest.TestCase, error: object) -> None:
        super().addError(test, error)  # type: ignore[arg-type]
        self.stream.write(f"FAIL {test.id().split('.', 1)[1]}\n")


def main() -> int:
    # Runs every case, prints the summary line, and returns non-zero if any failed.
    suite = unittest.defaultTestLoader.loadTestsFromModule(sys.modules[__name__])
    runner = unittest.TextTestRunner(resultclass=Reporter, verbosity=0, stream=sys.stdout)
    result = runner.run(suite)
    passed = result.testsRun - len(result.failures) - len(result.errors)
    sys.stdout.write(f"{passed}/{result.testsRun} tests passed\n")
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
