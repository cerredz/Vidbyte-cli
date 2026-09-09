"""Verification for task-board checkpoints, resume, and replay.

Run with `python scripts/test-task-board-checkpoints.py`. Every case drives the real
TaskBoardCheckpointer, TaskBoardCodexSession, and TaskBoardCommand validation with
fakes only at the SDK turn boundary. No network is used.
"""

from __future__ import annotations

import asyncio
import sys
import tempfile
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from vidbyte_cli.commands.runtime.task_board import TaskBoardCommand  # noqa: E402
from vidbyte_cli.lib.errors.failures import (  # noqa: E402
    TaskBoardCheckpointMismatch,
    TaskBoardCheckpointMissing,
)
from vidbyte_cli.lib.runtime_primitives.task_board import TaskBoardCodexSession  # noqa: E402
from vidbyte_cli.lib.runtime_primitives.task_board_checkpoints import (  # noqa: E402
    TaskBoardCheckpointer,
)
from vidbyte_cli.types.runtime import (  # noqa: E402
    RuntimeAdmissionGrant,
    RuntimeHost,
    RuntimeLaunchPlan,
    TaskBoardSettings,
)

PASS = "PASS"
FAIL = "FAIL"
RESULTS: list[tuple[str, str, str]] = []


def record(name: str, ok: bool, detail: str = "") -> None:
    # Stores one labeled outcome for the final summary.
    RESULTS.append((PASS if ok else FAIL, name, detail))
    print(f"{PASS if ok else FAIL} {name}" + (f" — {detail}" if detail and not ok else ""))


def make_plan() -> RuntimeLaunchPlan:
    # Builds a local-only plan pointing at the current directory for tests.
    return RuntimeLaunchPlan(
        capability_id="runtime.task-board@1",
        host=RuntimeHost.CODEX,
        executable=Path(sys.executable),
        working_directory=Path.cwd(),
        task="Checkpoint board",
    )


def make_grant() -> RuntimeAdmissionGrant:
    # Builds a time-valid grant; only its id is used by checkpoint tests.
    now = datetime.now(UTC)
    return RuntimeAdmissionGrant(
        admission_id="rta_ckpt1",
        capability_id="runtime.task-board@1",
        execution_location="local",
        charged_cents=2,
        admitted_at=now - timedelta(seconds=10),
        expires_at=now + timedelta(seconds=300),
        grant_token="tok_" + "x" * 20,
    )


def _reply(text: str, thread: str, tokens: int | None = 250) -> SimpleNamespace:
    # Builds the SDK reply shape with optional token reporting.
    codex = SimpleNamespace(status="completed", final_response=text, thread_id=thread)
    codex.usage_available = tokens is not None
    codex.usage = SimpleNamespace(total_tokens=tokens or 0)
    return SimpleNamespace(content=text, codex=codex)


def _session_with_fakes(prompts: list[str], bodies: list[str]) -> TaskBoardCodexSession:
    # Returns a session whose turns replay canned bodies and capture prompts.
    session = TaskBoardCodexSession({}, lambda _msg: None)
    session.prepare(make_plan())
    session._build_agent = lambda _i: object()  # type: ignore[method-assign]
    state = {"n": 0}

    async def fake_turn(agent: object, prompt: str) -> SimpleNamespace:
        prompts.append(prompt)
        body = bodies[state["n"] % len(bodies)]
        state["n"] += 1
        return _reply(body, f"thread-{state['n']}")

    session._turn = fake_turn  # type: ignore[method-assign]
    return session


def _settings(tasks: tuple[str, ...], **overrides: object) -> TaskBoardSettings:
    # Builds board settings with test-small summary budgets.
    kwargs: dict[str, object] = {"tasks": tasks, "summary_max_chars": 200}
    kwargs.update(overrides)
    return TaskBoardSettings(**kwargs)  # type: ignore[arg-type]


def test_board_id_stable_and_distinct() -> None:
    # [Edge Case] Same board hashes identically; one changed task changes the id.
    first = TaskBoardCheckpointer.board_id_for(("a", "b"))
    again = TaskBoardCheckpointer.board_id_for(("a", "b"))
    other = TaskBoardCheckpointer.board_id_for(("a", "c"))
    record("board id stable and distinct", first == again and first != other and len(first) == 12)


def test_fresh_run_writes_manifest_and_steps() -> None:
    # [Edge Case] A fresh checkpointed run stamps one manifest plus one file per step.
    async def go() -> bool:
        with tempfile.TemporaryDirectory() as directory:
            seen: list[str] = []
            session = _session_with_fakes(seen, ["out-a", "out-b"])
            checkpointer = TaskBoardCheckpointer(Path(directory), "board1")
            session.with_resume(checkpointer, 0)
            settings = _settings(("a", "b"))
            result = await session._run(make_plan(), settings, "rta_1")
            files = {path.name for path in Path(directory, "board1").iterdir()}
            return (
                result.completed == 2
                and "board.json" in files
                and "step-0.json" in files
                and "step-1.json" in files
            )

    record("fresh run writes manifest and steps", asyncio.run(go()))


def test_resume_from_zero_matches_fresh_prompts() -> None:
    # [Edge Case] --from 0 sends byte-identical prompts to a checkpoint-free run.
    async def go() -> bool:
        with tempfile.TemporaryDirectory() as directory:
            plain_prompts: list[str] = []
            plain = _session_with_fakes(plain_prompts, ["x", "y"])
            settings = _settings(("a", "b"))
            await plain._run(make_plan(), settings, "rta_plain")
            resumed_prompts: list[str] = []
            resumed = _session_with_fakes(resumed_prompts, ["x", "y"])
            resumed.with_resume(TaskBoardCheckpointer(Path(directory), "b2"), 0)
            await resumed._run(make_plan(), settings, "rta_resumed")
            return plain_prompts == resumed_prompts and len(resumed_prompts) == 2

    record("resume from zero matches fresh prompts", asyncio.run(go()))


def test_resume_skips_prefix_and_seeds_window() -> None:
    # [Silent Failure] Step 3 of 4 with window 2 sees stored summaries [1] and [2].
    async def go() -> bool:
        with tempfile.TemporaryDirectory() as directory:
            checkpointer = TaskBoardCheckpointer(Path(directory), "b3")
            first = _session_with_fakes([], ["r0", "r1", "r2", "r3"])
            first.with_resume(checkpointer, 0)
            settings = _settings(("a", "b", "c", "d"), window=2)
            await first._run(make_plan(), settings, "rta_first")
            seen: list[str] = []
            second = _session_with_fakes(seen, ["r3-new"])
            second.with_resume(TaskBoardCheckpointer(Path(directory), "b3"), 3)
            result = await second._run(make_plan(), settings, "rta_second")
            return (
                len(seen) == 1
                and "[1] r1" in seen[0]
                and "[2] r2" in seen[0]
                and result.completed == 4
                and len(result.steps) == 4
                and result.steps[0].summary == "r0"
            )

    record("resume skips prefix and seeds window", asyncio.run(go()))


def test_resume_past_end_runs_nothing() -> None:
    # [Edge Case] --from N on an N-task board returns stored steps with zero new turns.
    async def go() -> bool:
        with tempfile.TemporaryDirectory() as directory:
            checkpointer = TaskBoardCheckpointer(Path(directory), "b4")
            first = _session_with_fakes([], ["r0"])
            first.with_resume(checkpointer, 0)
            settings = _settings(("a",))
            await first._run(make_plan(), settings, "rta_first")
            seen: list[str] = []
            second = _session_with_fakes(seen, ["unused"])
            second.with_resume(TaskBoardCheckpointer(Path(directory), "b4"), 1)
            result = await second._run(make_plan(), settings, "rta_second")
            return seen == [] and result.completed == 1 and len(result.steps) == 1

    record("resume past end runs nothing", asyncio.run(go()))


def test_missing_step_file_fails() -> None:
    # [Hidden Failure] A gap in the prefix fails loudly instead of re-executing.
    async def go() -> bool:
        with tempfile.TemporaryDirectory() as directory:
            checkpointer = TaskBoardCheckpointer(Path(directory), "b5")
            first = _session_with_fakes([], ["r0", "r1"])
            first.with_resume(checkpointer, 0)
            settings = _settings(("a", "b"))
            await first._run(make_plan(), settings, "rta_first")
            Path(directory, "b5", "step-0.json").unlink()
            second = _session_with_fakes([], ["unused"])
            second.with_resume(TaskBoardCheckpointer(Path(directory), "b5"), 2)
            try:
                await second._run(make_plan(), settings, "rta_second")
            except TaskBoardCheckpointMissing as error:
                return "step 0" in str(error)
            return False

    record("missing step file fails", asyncio.run(go()))


def test_changed_board_text_rejected() -> None:
    # [Hidden Failure] Edited task text fails closed before any model turn.
    async def go() -> bool:
        with tempfile.TemporaryDirectory() as directory:
            checkpointer = TaskBoardCheckpointer(Path(directory), "b6")
            first = _session_with_fakes([], ["r0"])
            first.with_resume(checkpointer, 0)
            await first._run(make_plan(), _settings(("a",)), "rta_first")
            seen: list[str] = []
            second = _session_with_fakes(seen, ["unused"])
            second.with_resume(TaskBoardCheckpointer(Path(directory), "b6"), 1)
            try:
                await second._run(make_plan(), _settings(("a-changed",)), "rta_second")
            except TaskBoardCheckpointMismatch:
                return seen == []
            return False

    record("changed board text rejected", asyncio.run(go()))


def test_changed_window_rejected() -> None:
    # [Hidden Failure] A different window fails closed before any model turn.
    async def go() -> bool:
        with tempfile.TemporaryDirectory() as directory:
            checkpointer = TaskBoardCheckpointer(Path(directory), "b7")
            first = _session_with_fakes([], ["r0", "r1"])
            first.with_resume(checkpointer, 0)
            await first._run(make_plan(), _settings(("a", "b"), window=10), "rta_first")
            seen: list[str] = []
            second = _session_with_fakes(seen, ["unused"])
            second.with_resume(TaskBoardCheckpointer(Path(directory), "b7"), 1)
            try:
                await second._run(make_plan(), _settings(("a", "b"), window=3), "rta_second")
            except TaskBoardCheckpointMismatch:
                return seen == []
            return False

    record("changed window rejected", asyncio.run(go()))


def test_replay_prompt_byte_equal() -> None:
    # [Silent Failure] Replay rebuilds the original step prompt exactly.
    async def go() -> bool:
        with tempfile.TemporaryDirectory() as directory:
            original: list[str] = []
            first = _session_with_fakes(original, ["r0", "r1", "r2"])
            first.with_resume(TaskBoardCheckpointer(Path(directory), "b8"), 0)
            settings = _settings(("a", "b", "c"), window=2)
            await first._run(make_plan(), settings, "rta_first")
            replayed: list[str] = []
            second = _session_with_fakes(replayed, ["r1-debug"])
            second.with_replay(TaskBoardCheckpointer(Path(directory), "b8"), 1)
            result = await second._replay(make_plan(), settings, "rta_second", 1)
            return (
                replayed == [original[1]]
                and len(result.steps) == 1
                and result.steps[0].index == 1
                and result.steps[0].summary == "r1-debug"
            )

    record("replay prompt byte equal", asyncio.run(go()))


def test_unknown_usage_records_none() -> None:
    # [Silent Failure] Replies without usage report None tokens, never zero.
    async def go() -> bool:
        with tempfile.TemporaryDirectory() as directory:
            checkpointer = TaskBoardCheckpointer(Path(directory), "b9")
            session = TaskBoardCodexSession({}, lambda _msg: None)
            session.prepare(make_plan())
            session._build_agent = lambda _i: object()  # type: ignore[method-assign]

            async def silent_turn(agent: object, prompt: str) -> SimpleNamespace:
                codex = SimpleNamespace(status="completed", final_response="quiet", thread_id="t")
                return SimpleNamespace(content="quiet", codex=codex)

            session._turn = silent_turn  # type: ignore[method-assign]
            session.with_resume(checkpointer, 0)
            await session._run(make_plan(), _settings(("a",)), "rta_silent")
            stored = checkpointer.load_prefix(1)[0]
            return stored.total_tokens is None

    record("unknown usage records none", asyncio.run(go()))


def test_write_failure_never_fails_step() -> None:
    # [Hidden Assumption] An unwritable checkpoint directory still completes the step.
    async def go() -> bool:
        with tempfile.TemporaryDirectory() as directory:
            blocker = Path(directory, "blocker")
            blocker.write_text("not a directory", encoding="utf-8")
            notes: list[str] = []
            session = _session_with_fakes([], ["done"])
            session._progress = notes.append  # type: ignore[method-assign]
            session.with_resume(TaskBoardCheckpointer(blocker, "b10"), 0)
            result = await session._run(make_plan(), _settings(("a",)), "rta_blocked")
            write_note = any("Checkpoint write failed" in note for note in notes)
            return result.completed == 1 and write_note

    record("write failure never fails step", asyncio.run(go()))


def test_temp_files_ignored_on_load() -> None:
    # [Hidden Assumption] Partial temp siblings are never read as steps.
    with tempfile.TemporaryDirectory() as directory:
        checkpointer = TaskBoardCheckpointer(Path(directory), "b11")
        Path(directory, "b11").mkdir(parents=True, exist_ok=True)
        Path(directory, "b11", ".step-0.json.abc.tmp").write_text("partial", encoding="utf-8")
        try:
            checkpointer.load_prefix(1)
        except TaskBoardCheckpointMissing:
            record("temp files ignored on load", True)
            return
        record("temp files ignored on load", False, "partial temp file read as step")


def test_resume_bounds_rejected_before_admission() -> None:
    # [Hidden Assumption] Out-of-range --from/--replay-task fail in validation, not in runs.
    import click

    command = TaskBoardCommand()
    settings = _settings(("a", "b"))
    with tempfile.TemporaryDirectory() as directory:
        checkpointer = TaskBoardCheckpointer(Path(directory), "b12")
        checkpointer.write_manifest(settings)
        try:
            command._validate_resume(checkpointer, settings, 5, None)
            record("resume past end rejected early", False, "accepted --from 5 on 2 tasks")
        except click.BadParameter:
            record("resume past end rejected early", True)
        try:
            command._checkpointer(("a", "b"), True, None, 1, 1)
            record("from plus replay rejected", False, "accepted both flags")
        except click.BadParameter:
            record("from plus replay rejected", True)
        try:
            command._checkpointer(("a", "b"), False, None, 1, None)
            record("resume without checkpoints rejected", False, "accepted --from uncheckpointed")
        except click.BadParameter:
            record("resume without checkpoints rejected", True)


def main() -> int:
    # Runs every design-doc Section 10 checkpoint case and reports the tally.
    test_board_id_stable_and_distinct()
    test_fresh_run_writes_manifest_and_steps()
    test_resume_from_zero_matches_fresh_prompts()
    test_resume_skips_prefix_and_seeds_window()
    test_resume_past_end_runs_nothing()
    test_missing_step_file_fails()
    test_changed_board_text_rejected()
    test_changed_window_rejected()
    test_replay_prompt_byte_equal()
    test_unknown_usage_records_none()
    test_write_failure_never_fails_step()
    test_temp_files_ignored_on_load()
    test_resume_bounds_rejected_before_admission()
    passed = sum(1 for status, _, _ in RESULTS if status == PASS)
    print(f"{passed}/{len(RESULTS)} tests passed")
    return 0 if passed == len(RESULTS) else 1


if __name__ == "__main__":
    raise SystemExit(main())
