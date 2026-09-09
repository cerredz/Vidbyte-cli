"""Verification for task-board checkpoints, resume, replay, repair, slicing, and reporting.

Run with `python scripts/test-task-board-checkpoints.py`. Every case drives the real
TaskBoardFileStore, TaskBoardCheckpointer, TaskBoardCodexSession, and TaskBoardCommand
validation with fakes only at the SDK turn boundary. No network is used.
"""

from __future__ import annotations

import asyncio
import json
import sys
import tempfile
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from vidbyte_cli.commands.runtime.task_board import TaskBoardCommand  # noqa: E402
from vidbyte_cli.lib.errors.failures import (  # noqa: E402
    TaskBoardBoardNotFound,
    TaskBoardCheckpointMismatch,
    TaskBoardCheckpointMissing,
    TaskBoardTaskListInvalid,
)
from vidbyte_cli.lib.runtime_primitives.task_board import TaskBoardCodexSession  # noqa: E402
from vidbyte_cli.lib.runtime_primitives.task_board_checkpoints import (  # noqa: E402
    TaskBoardCheckpointer,
)
from vidbyte_cli.lib.runtime_primitives.task_board_files import TaskBoardFileStore  # noqa: E402
from vidbyte_cli.types.runtime import (  # noqa: E402
    RuntimeAdmissionGrant,
    RuntimeHost,
    RuntimeLaunchPlan,
    TaskBoardAgentSettings,
    TaskBoardCheckpointMode,
    TaskBoardHandoffMode,
    TaskBoardReasoningEffort,
    TaskBoardRunControls,
    TaskBoardSandbox,
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


def _session_with_fakes(
    prompts: list[str],
    bodies: list[str],
    tokens: int | None = 250,
    stream: list[object] | None = None,
) -> TaskBoardCodexSession:
    # Returns a session whose turns replay canned bodies and capture prompts. A body of "" is
    # a failed turn, which is how repair and stop-on-error cases produce a stored failure.
    emit = None if stream is None else stream.append
    session = TaskBoardCodexSession({}, lambda _msg: None, emit)
    session.prepare(make_plan())
    session._build_agent = lambda _i, _s: object()  # type: ignore[method-assign]
    state = {"n": 0}

    async def fake_turn(agent: object, prompt: str, settings: object) -> SimpleNamespace:
        prompts.append(prompt)
        body = bodies[state["n"] % len(bodies)]
        state["n"] += 1
        if not body:
            raise RuntimeError("fake host failure")
        return _reply(body, f"thread-{state['n']}", tokens)

    session._turn = fake_turn  # type: ignore[method-assign]
    return session


def _settings(tasks: tuple[str, ...], **overrides: object) -> TaskBoardSettings:
    # Builds board settings with test-small summary budgets.
    kwargs: dict[str, object] = {"tasks": tasks, "summary_max_chars": 200}
    kwargs.update(overrides)
    return TaskBoardSettings(**kwargs)  # type: ignore[arg-type]


def _controls(**overrides: object) -> TaskBoardRunControls:
    # Builds run controls with the defaults every case starts from.
    return TaskBoardRunControls(**overrides)  # type: ignore[arg-type]


def _armed(
    session: TaskBoardCodexSession, root: Path, board: str, **controls: object
) -> TaskBoardCheckpointer:
    # Arms one session against a board directory and returns that board's checkpointer.
    checkpointer = TaskBoardCheckpointer(root, board)
    session.with_checkpoints(checkpointer, _controls(**controls))
    return checkpointer


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
            session = _session_with_fakes([], ["out-a", "out-b"])
            _armed(session, Path(directory), "board1")
            result = await session._run(make_plan(), _settings(("a", "b")), "rta_1")
            files = {path.name for path in Path(directory, "board1").iterdir()}
            return (
                result.completed == 2
                and {"board.json", "step-0.json", "step-1.json"} <= files
                and result.total_tokens == 500
            )

    record("fresh run writes manifest and steps", asyncio.run(go()))


def test_result_carries_absolute_dir_and_resume_command() -> None:
    # [Silent Failure] The result addresses the board absolutely and says how to continue it.
    async def go() -> bool:
        with tempfile.TemporaryDirectory() as directory:
            session = _session_with_fakes([], ["r0"])
            _armed(session, Path(directory) / "runs" / "exp-a", "b-abs", stop_after=1)
            result = await session._run(make_plan(), _settings(("a", "b", "c")), "rta_abs")
            resume = result.resume_command or ""
            return (
                result.board_dir is not None
                and Path(result.board_dir).is_absolute()
                and result.board_dir.endswith("b-abs")
                and "--checkpoint-root" in resume
                and "--from 1" in resume
                and result.board_id == "b-abs"
            )

    record("result carries absolute dir and resume command", asyncio.run(go()))


def test_checkpoint_roots_isolate_boards() -> None:
    # [Edge Case] Two roots hold two boards of the same id without ever colliding.
    async def go() -> bool:
        with tempfile.TemporaryDirectory() as directory:
            left, right = Path(directory, "exp-a"), Path(directory, "exp-b")
            for root, body in ((left, "left"), (right, "right")):
                session = _session_with_fakes([], [body])
                _armed(session, root, "shared")
                await session._run(make_plan(), _settings(("a",)), "rta_iso")
            stored = [
                TaskBoardCheckpointer(root, "shared").read_step(0).summary for root in (left, right)
            ]
            return stored == ["left", "right"]

    record("checkpoint roots isolate boards", asyncio.run(go()))


def test_list_boards_reports_progress() -> None:
    # [Edge Case] The index reports one row per board and skips unrelated directories.
    async def go() -> bool:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for board, bodies, tasks in (("b-a", ["x", "y"], ("a", "b")), ("b-b", ["z"], ("c",))):
                session = _session_with_fakes([], bodies)
                _armed(session, root, board)
                await session._run(make_plan(), _settings(tasks), "rta_list")
            (root / "not-a-board").mkdir()
            rows = TaskBoardCheckpointer.list_boards(root)
            by_id = {row.board_id: row for row in rows}
            return (
                set(by_id) == {"b-a", "b-b"}
                and by_id["b-a"].completed == 2
                and by_id["b-b"].task_count == 1
                and Path(by_id["b-a"].board_dir).is_absolute()
            )

    record("list boards reports progress", asyncio.run(go()))


def test_status_chain_reports_pending_and_links() -> None:
    # [Silent Failure] The stored chain names pending steps and links each step to its parent.
    async def go() -> bool:
        with tempfile.TemporaryDirectory() as directory:
            session = _session_with_fakes([], ["r0", "r1"])
            checkpointer = _armed(session, Path(directory), "b-chain", stop_after=2)
            await session._run(make_plan(), _settings(("a", "b", "c")), "rta_chain")
            chain = checkpointer.chain()
            ancestors = tuple(node.index for node in chain.ancestors_of(1))
            return (
                chain.completed_indices == (0, 1)
                and chain.pending_indices == (2,)
                and chain.node_at(0).parent_index is None
                and chain.node_at(1).parent_index == 0
                and ancestors == (0,)
                and chain.total_tokens == 500
            )

    record("status chain reports pending and links", asyncio.run(go()))


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
            _armed(resumed, Path(directory), "b2")
            await resumed._run(make_plan(), settings, "rta_resumed")
            return plain_prompts == resumed_prompts and len(resumed_prompts) == 2

    record("resume from zero matches fresh prompts", asyncio.run(go()))


def test_resume_skips_prefix_and_seeds_window() -> None:
    # [Silent Failure] Step 3 of 4 with window 2 sees stored summaries [1] and [2].
    async def go() -> bool:
        with tempfile.TemporaryDirectory() as directory:
            first = _session_with_fakes([], ["r0", "r1", "r2", "r3"])
            _armed(first, Path(directory), "b3")
            settings = _settings(("a", "b", "c", "d"), window=2)
            await first._run(make_plan(), settings, "rta_first")
            seen: list[str] = []
            second = _session_with_fakes(seen, ["r3-new"])
            _armed(second, Path(directory), "b3", start_from=3)
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
            first = _session_with_fakes([], ["r0"])
            _armed(first, Path(directory), "b4")
            settings = _settings(("a",))
            await first._run(make_plan(), settings, "rta_first")
            seen: list[str] = []
            second = _session_with_fakes(seen, ["unused"])
            _armed(second, Path(directory), "b4", start_from=1)
            result = await second._run(make_plan(), settings, "rta_second")
            return seen == [] and result.completed == 1 and len(result.steps) == 1

    record("resume past end runs nothing", asyncio.run(go()))


def test_missing_step_file_fails() -> None:
    # [Hidden Failure] A gap in the prefix fails loudly instead of re-executing.
    async def go() -> bool:
        with tempfile.TemporaryDirectory() as directory:
            first = _session_with_fakes([], ["r0", "r1"])
            _armed(first, Path(directory), "b5")
            settings = _settings(("a", "b"))
            await first._run(make_plan(), settings, "rta_first")
            Path(directory, "b5", "step-0.json").unlink()
            second = _session_with_fakes([], ["unused"])
            _armed(second, Path(directory), "b5", start_from=2)
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
            first = _session_with_fakes([], ["r0"])
            _armed(first, Path(directory), "b6")
            await first._run(make_plan(), _settings(("a",)), "rta_first")
            seen: list[str] = []
            second = _session_with_fakes(seen, ["unused"])
            _armed(second, Path(directory), "b6", start_from=1)
            try:
                await second._run(make_plan(), _settings(("a-changed",)), "rta_second")
            except TaskBoardCheckpointMismatch:
                return seen == []
            return False

    record("changed board text rejected", asyncio.run(go()))


def test_changed_window_or_handoff_rejected() -> None:
    # [Hidden Failure] A different window or handoff mode fails closed before any model turn.
    async def go() -> bool:
        with tempfile.TemporaryDirectory() as directory:
            first = _session_with_fakes([], ["r0", "r1"])
            _armed(first, Path(directory), "b7")
            await first._run(make_plan(), _settings(("a", "b"), window=10), "rta_first")
            rejected = 0
            for drift in ({"window": 3}, {"handoff_mode": TaskBoardHandoffMode.FULL_RESULT}):
                seen: list[str] = []
                second = _session_with_fakes(seen, ["unused"])
                _armed(second, Path(directory), "b7", start_from=1)
                try:
                    await second._run(make_plan(), _settings(("a", "b"), **drift), "rta_drift")
                except TaskBoardCheckpointMismatch:
                    rejected += int(seen == [])
            return rejected == 2

    record("changed window or handoff rejected", asyncio.run(go()))


def test_replay_prompt_byte_equal() -> None:
    # [Silent Failure] Replay rebuilds the original step prompt exactly.
    async def go() -> bool:
        with tempfile.TemporaryDirectory() as directory:
            original: list[str] = []
            first = _session_with_fakes(original, ["r0", "r1", "r2"])
            _armed(first, Path(directory), "b8")
            settings = _settings(("a", "b", "c"), window=2)
            await first._run(make_plan(), settings, "rta_first")
            replayed: list[str] = []
            second = _session_with_fakes(replayed, ["r1-debug"])
            _armed(second, Path(directory), "b8", replay_index=1)
            result = await second._replay(settings, "rta_second", 1)
            return (
                replayed == [original[1]]
                and len(result.steps) == 1
                and result.steps[0].index == 1
                and result.steps[0].summary == "r1-debug"
            )

    record("replay prompt byte equal", asyncio.run(go()))


def test_print_prompt_previews_without_turns() -> None:
    # [Silent Failure] A preview equals the replay prompt and starts no agent at all.
    async def go() -> bool:
        with tempfile.TemporaryDirectory() as directory:
            original: list[str] = []
            first = _session_with_fakes(original, ["r0", "r1", "r2"])
            _armed(first, Path(directory), "b-preview")
            settings = _settings(("a", "b", "c"), window=2)
            await first._run(make_plan(), settings, "rta_first")
            seen: list[str] = []
            preview_session = _session_with_fakes(seen, ["unused"])
            _armed(preview_session, Path(directory), "b-preview", replay_index=2)
            preview = preview_session.preview_prompt(settings, 2)
            return preview == original[2] and seen == []

    record("print prompt previews without turns", asyncio.run(go()))


def test_unknown_usage_records_none() -> None:
    # [Silent Failure] Replies without usage report None tokens, never zero.
    async def go() -> bool:
        with tempfile.TemporaryDirectory() as directory:
            session = _session_with_fakes([], ["quiet"], tokens=None)
            checkpointer = _armed(session, Path(directory), "b9")
            result = await session._run(make_plan(), _settings(("a",)), "rta_silent")
            stored = checkpointer.read_step(0)
            return stored.total_tokens is None and result.estimated_cost_usd is None

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
            _armed(session, blocker, "b10")
            result = await session._run(make_plan(), _settings(("a",)), "rta_blocked")
            return result.completed == 1 and any("Checkpoint write failed" in n for n in notes)

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


def test_stream_mode_emits_one_record_per_step() -> None:
    # [Silent Failure] Stream mode publishes each step as it lands; save-only publishes none.
    async def go() -> bool:
        with tempfile.TemporaryDirectory() as directory:
            streamed: list[object] = []
            session = _session_with_fakes([], ["r0", "r1"], stream=streamed)
            _armed(
                session,
                Path(directory),
                "b-stream",
                checkpoint_mode=TaskBoardCheckpointMode.STREAM,
            )
            await session._run(make_plan(), _settings(("a", "b")), "rta_stream")
            quiet: list[object] = []
            silent = _session_with_fakes([], ["r0"], stream=quiet)
            _armed(silent, Path(directory), "b-quiet")
            await silent._run(make_plan(), _settings(("a",)), "rta_quiet")
            return len(streamed) == 2 and quiet == []

    record("stream mode emits one record per step", asyncio.run(go()))


def test_export_mode_appends_one_line_per_step() -> None:
    # [Edge Case] Export mode writes an append-only log a forking tool can tail.
    async def go() -> bool:
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory, "logs", "progress.jsonl")
            session = _session_with_fakes([], ["r0", "r1"])
            _armed(
                session,
                Path(directory),
                "b-export",
                checkpoint_mode=TaskBoardCheckpointMode.EXPORT,
                export_file=str(target),
            )
            result = await session._run(make_plan(), _settings(("a", "b")), "rta_export")
            lines = target.read_text(encoding="utf-8").strip().splitlines()
            parsed = [json.loads(line) for line in lines]
            # Compared resolved: the CLI reports an absolute, symlink-free path, which on
            # macOS (/var -> /private/var) and Windows CI (8.3 short names) is not the
            # spelling the temporary directory handed us.
            return (
                len(parsed) == 2
                and [item["index"] for item in parsed] == [0, 1]
                and result.export_file == str(target.resolve())
            )

    record("export mode appends one line per step", asyncio.run(go()))


def test_hook_runs_and_failure_is_not_fatal() -> None:
    # [Hidden Assumption] The hook observes each save, and a broken hook never fails a step.
    async def go() -> bool:
        with tempfile.TemporaryDirectory() as directory:
            marker = Path(directory, "hook.txt")
            command = f"{sys.executable} -c \"open(r'{marker}','a').write(1*'x')\""
            session = _session_with_fakes([], ["r0"])
            _armed(session, Path(directory), "b-hook", on_checkpoint=command)
            await session._run(make_plan(), _settings(("a",)), "rta_hook")
            notes: list[str] = []
            broken = _session_with_fakes([], ["r0"])
            broken._progress = notes.append  # type: ignore[method-assign]
            _armed(broken, Path(directory), "b-hook2", on_checkpoint="exit 3")
            result = await broken._run(make_plan(), _settings(("a",)), "rta_hook2")
            return (
                marker.exists()
                and result.completed == 1
                and any("Checkpoint hook failed" in note for note in notes)
            )

    record("hook runs and failure is not fatal", asyncio.run(go()))


def test_fork_copies_prefix_and_keeps_original() -> None:
    # [Hidden Failure] A fork duplicates the prefix, records the edge, and touches nothing else.
    async def go() -> bool:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            session = _session_with_fakes([], ["r0", "r1", "r2"])
            source = _armed(session, root, "b-src")
            await session._run(make_plan(), _settings(("a", "b", "c")), "rta_src")
            target = TaskBoardCheckpointer(root, "b-fork")
            copied = source.fork_into(target, 2)
            forked = target.chain()
            original = source.chain()
            return (
                copied == 2
                and forked.parent_board_id == "b-src"
                and forked.forked_at_index == 2
                and forked.completed_indices == (0, 1)
                and original.completed_indices == (0, 1, 2)
                and target.stored_tasks() == ("a", "b", "c")
            )

    record("fork copies prefix and keeps original", asyncio.run(go()))


def test_fork_past_a_gap_fails() -> None:
    # [Hidden Failure] Forking beyond a missing step names the gap instead of copying part of it.
    async def go() -> bool:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            session = _session_with_fakes([], ["r0", "r1"])
            source = _armed(session, root, "b-gap")
            await session._run(make_plan(), _settings(("a", "b")), "rta_gap")
            (root / "b-gap" / "step-0.json").unlink()
            try:
                source.fork_into(TaskBoardCheckpointer(root, "b-gap-fork"), 2)
            except TaskBoardCheckpointMissing:
                return True
            return False

    record("fork past a gap fails", asyncio.run(go()))


def test_retry_failed_only_reruns_just_the_failures() -> None:
    # [Hidden Failure] A repair pass pays for the stored failures and for nothing else.
    async def go() -> bool:
        with tempfile.TemporaryDirectory() as directory:
            first = _session_with_fakes([], ["r0", "", "r2"])
            _armed(first, Path(directory), "b-repair")
            settings = _settings(("a", "b", "c"), stop_on_error=False, max_retries_per_task=0)
            await first._run(make_plan(), settings, "rta_repair")
            seen: list[str] = []
            second = _session_with_fakes(seen, ["b-fixed"])
            checkpointer = _armed(second, Path(directory), "b-repair", retry_failed_only=True)
            result = await second._run(make_plan(), settings, "rta_repaired")
            return (
                len(seen) == 1
                and "Task 1:" in seen[0]
                and checkpointer.read_step(1).status == "completed"
                and checkpointer.read_step(0).summary == "r0"
                and result.completed == 3
                # A repaired index appears once, and the board no longer reports a failure.
                and [step.index for step in result.steps] == [0, 1, 2]
                and result.failed == 0
            )

    record("retry failed only reruns just the failures", asyncio.run(go()))


def test_budget_counts_only_this_invocation() -> None:
    # [Hidden Failure] A resumed board is not halted by the spend its earlier runs made.
    async def go() -> bool:
        with tempfile.TemporaryDirectory() as directory:
            first = _session_with_fakes([], ["r0", "r1"], tokens=400)
            _armed(first, Path(directory), "b-carry", stop_after=2)
            settings = _settings(("a", "b", "c"))
            await first._run(make_plan(), settings, "rta_carry")
            seen: list[str] = []
            second = _session_with_fakes(seen, ["r2"], tokens=400)
            _armed(second, Path(directory), "b-carry", start_from=2, max_tokens=500)
            result = await second._run(make_plan(), settings, "rta_carry2")
            # The stored prefix already spent 800, which must not pre-empt this invocation.
            return len(seen) == 1 and result.stopped_reason is None and result.total_tokens == 1200

    record("budget counts only this invocation", asyncio.run(go()))


def test_stop_after_slices_and_returns_resume() -> None:
    # [Edge Case] A slice runs exactly N steps and hands the caller its continuation.
    async def go() -> bool:
        with tempfile.TemporaryDirectory() as directory:
            seen: list[str] = []
            session = _session_with_fakes(seen, ["r0", "r1", "r2", "r3"])
            _armed(session, Path(directory), "b-slice", stop_after=2)
            result = await session._run(make_plan(), _settings(("a", "b", "c", "d")), "rta_slice")
            return (
                len(seen) == 2
                and result.stopped_reason == "stop-after"
                and "--from 2" in (result.resume_command or "")
            )

    record("stop after slices and returns resume", asyncio.run(go()))


def test_failed_board_resumes_into_repair() -> None:
    # [Silent Failure] A board holding failures is pointed at repair, never past the failure.
    async def go() -> bool:
        with tempfile.TemporaryDirectory() as directory:
            session = _session_with_fakes([], ["r0", ""])
            checkpointer = _armed(session, Path(directory), "b-failed")
            settings = _settings(("a", "b", "c"), max_retries_per_task=0)
            result = await session._run(make_plan(), settings, "rta_failed")
            resume = result.resume_command or ""
            status = checkpointer.resume_command(0, repair=True)
            return (
                result.stopped_reason == "stop-on-error"
                and "--retry-failed-only" in resume
                and resume == status
            )

    record("failed board resumes into repair", asyncio.run(go()))


def test_budget_guard_halts_between_steps() -> None:
    # [Hidden Failure] A token budget stops the board and never silently truncates it.
    async def go() -> bool:
        with tempfile.TemporaryDirectory() as directory:
            seen: list[str] = []
            session = _session_with_fakes(seen, ["r0", "r1", "r2"], tokens=400)
            _armed(session, Path(directory), "b-budget", max_tokens=500)
            result = await session._run(make_plan(), _settings(("a", "b", "c")), "rta_budget")
            cheap: list[str] = []
            priced = _session_with_fakes(cheap, ["r0", "r1", "r2"], tokens=400)
            _armed(
                priced,
                Path(directory),
                "b-cost",
                max_cost_usd=0.005,
                usd_per_million_tokens=10.0,
            )
            costed = await priced._run(make_plan(), _settings(("a", "b", "c")), "rta_cost")
            return (
                len(seen) == 2
                and result.stopped_reason == "max-tokens"
                and "--from 2" in (result.resume_command or "")
                and len(cheap) == 2
                and costed.stopped_reason == "max-cost"
            )

    record("budget guard halts between steps", asyncio.run(go()))


def test_report_file_written_from_stored_chain() -> None:
    # [Silent Failure] The Markdown report describes the same steps the chain holds.
    async def go() -> bool:
        with tempfile.TemporaryDirectory() as directory:
            report = Path(directory, "reports", "board.md")
            session = _session_with_fakes([], ["r0", "r1"])
            _armed(session, Path(directory), "b-report", report_file=str(report))
            result = await session._run(make_plan(), _settings(("a", "b")), "rta_report")
            body = report.read_text(encoding="utf-8")
            return (
                result.report_file == str(report.resolve())
                and "# Task board b-report" in body
                and "## Step 0 — completed" in body
                and "## Step 1 — completed" in body
                and "r1" in body
            )

    record("report file written from stored chain", asyncio.run(go()))


def test_handoff_modes_change_what_the_next_task_reads() -> None:
    # [Silent Failure] Each handoff mode forwards a different entry for the same result.
    async def go() -> bool:
        with tempfile.TemporaryDirectory() as directory:
            prompts: dict[str, str] = {}
            # The first body exceeds the 200-character summary budget, which is what makes
            # full-result distinguishable from summary rather than accidentally identical.
            body = "result " * 60
            for mode in TaskBoardHandoffMode:
                seen: list[str] = []
                session = _session_with_fakes(seen, [body, "second"])
                _armed(session, Path(directory), f"b-{mode.value}")
                await session._run(
                    make_plan(), _settings(("first", "second"), handoff_mode=mode), "rta_handoff"
                )
                prompts[mode.value] = seen[1]
            return (
                "Task: first" in prompts["task-and-summary"]
                and "Task: first" not in prompts["summary"]
                and "truncated" in prompts["summary"]
                and "truncated" not in prompts["full-result"]
                and len(set(prompts.values())) == 3
            )

    record("handoff modes change what the next task reads", asyncio.run(go()))


def test_agent_settings_are_bounded_and_carried() -> None:
    # [Edge Case] Per-iteration agent settings validate and reach the board settings intact.
    agent = TaskBoardAgentSettings(
        model="gpt-5-codex",
        sandbox=TaskBoardSandbox.READ_ONLY,
        reasoning_effort=TaskBoardReasoningEffort.HIGH,
        turn_timeout_seconds=600,
    )
    settings = _settings(("a",), agent=agent)
    rejected = False
    try:
        TaskBoardAgentSettings(turn_timeout_seconds=1)
    except ValueError:
        rejected = True
    record(
        "agent settings are bounded and carried",
        settings.agent.model == "gpt-5-codex"
        and settings.agent.sandbox is TaskBoardSandbox.READ_ONLY
        and settings.agent.reasoning_effort is TaskBoardReasoningEffort.HIGH
        and rejected,
    )


def test_task_list_round_trips_through_both_formats() -> None:
    # [Edge Case] Import and export are inverses in Markdown and JSON, and reject other shapes.
    with tempfile.TemporaryDirectory() as directory:
        store = TaskBoardFileStore(Path(directory))
        board = ("first task", "second task\nwith a second line")
        round_tripped = []
        for name in ("board.md", "board.json"):
            path = Path(directory, name)
            store.write_task_list(path, board)
            round_tripped.append(store.read_task_list(path) == board)
        rejected = 0
        for name, body in (("board.yaml", "- a"), ("bad.json", '{"a": 1}'), ("empty.md", "x")):
            path = Path(directory, name)
            path.write_text(body, encoding="utf-8")
            try:
                store.read_task_list(path)
            except TaskBoardTaskListInvalid:
                rejected += 1
        record(
            "task list round trips through both formats",
            all(round_tripped) and rejected == 3,
            f"round_tripped={round_tripped} rejected={rejected}",
        )


def test_unknown_board_fails_closed() -> None:
    # [Hidden Failure] Reading a board that was never checkpointed names the id and stops.
    with tempfile.TemporaryDirectory() as directory:
        try:
            TaskBoardCheckpointer(Path(directory), "nope").read_manifest()
        except TaskBoardBoardNotFound as error:
            record("unknown board fails closed", "nope" in str(error))
            return
        record("unknown board fails closed", False, "absent board read as a board")


def test_resume_bounds_rejected_before_admission() -> None:
    # [Hidden Assumption] Out-of-range and contradictory flags fail in validation, not in runs.
    import click

    from vidbyte_cli.commands.runtime.task_board import TaskBoardOptions

    def options(**overrides: object) -> TaskBoardOptions:
        base: dict[str, object] = {
            "task_files": (),
            "task_list": None,
            "host": "codex",
            "window": 10,
            "context_mode": "windowed-summaries",
            "handoff": "summary",
            "summary_mode": "truncate-tail",
            "summary_max_chars": 1200,
            "stop_on_error": True,
            "retries_per_task": 1,
            "model": "",
            "sandbox": "workspace-write",
            "reasoning_effort": "",
            "turn_timeout": 600,
            "key": None,
            "checkpoint": True,
            "checkpoint_root": Path(".vidbyte/task-board"),
            "checkpoint_id": None,
            "checkpoint_mode": "save-only",
            "export_file": None,
            "report_file": None,
            "on_checkpoint": "",
            "start_from": None,
            "replay_task": None,
            "print_prompt": False,
            "stop_after": None,
            "retry_failed_only": False,
            "max_tokens": None,
            "max_cost": None,
            "usd_per_million_tokens": 10.0,
        }
        base.update(overrides)
        return TaskBoardOptions(base)

    command = TaskBoardCommand()
    settings = _settings(("a", "b"))
    with tempfile.TemporaryDirectory() as directory:
        checkpointer = TaskBoardCheckpointer(Path(directory), "b12")
        checkpointer.write_manifest(settings)
        for name, call in (
            (
                "resume past end rejected early",
                lambda: command._validate_resume(checkpointer, settings, options(start_from=5)),
            ),
            (
                "from plus replay rejected",
                lambda: command._checkpointer(options(start_from=1, replay_task=1)),
            ),
            (
                "resume without checkpoints rejected",
                lambda: command._checkpointer(options(checkpoint=False, start_from=1)),
            ),
        ):
            try:
                call()
                record(name, False, "accepted an invalid invocation")
            except click.BadParameter:
                record(name, True)


def main() -> int:
    # Runs every checkpoint, resume, replay, repair, slicing, and reporting case.
    for case in (
        test_board_id_stable_and_distinct,
        test_fresh_run_writes_manifest_and_steps,
        test_result_carries_absolute_dir_and_resume_command,
        test_checkpoint_roots_isolate_boards,
        test_list_boards_reports_progress,
        test_status_chain_reports_pending_and_links,
        test_resume_from_zero_matches_fresh_prompts,
        test_resume_skips_prefix_and_seeds_window,
        test_resume_past_end_runs_nothing,
        test_missing_step_file_fails,
        test_changed_board_text_rejected,
        test_changed_window_or_handoff_rejected,
        test_replay_prompt_byte_equal,
        test_print_prompt_previews_without_turns,
        test_unknown_usage_records_none,
        test_write_failure_never_fails_step,
        test_temp_files_ignored_on_load,
        test_stream_mode_emits_one_record_per_step,
        test_export_mode_appends_one_line_per_step,
        test_hook_runs_and_failure_is_not_fatal,
        test_fork_copies_prefix_and_keeps_original,
        test_fork_past_a_gap_fails,
        test_retry_failed_only_reruns_just_the_failures,
        test_stop_after_slices_and_returns_resume,
        test_budget_counts_only_this_invocation,
        test_budget_guard_halts_between_steps,
        test_failed_board_resumes_into_repair,
        test_report_file_written_from_stored_chain,
        test_handoff_modes_change_what_the_next_task_reads,
        test_agent_settings_are_bounded_and_carried,
        test_task_list_round_trips_through_both_formats,
        test_unknown_board_fails_closed,
        test_resume_bounds_rejected_before_admission,
    ):
        case()
    passed = sum(1 for status, _, _ in RESULTS if status == PASS)
    print(f"{passed}/{len(RESULTS)} tests passed")
    return 0 if passed == len(RESULTS) else 1


if __name__ == "__main__":
    raise SystemExit(main())
