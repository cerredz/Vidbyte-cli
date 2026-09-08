"""Verification for task-board DAG dependencies: parsing, order, dep-only context.

Run with `python scripts/test-task-board-dag.py`. Every case drives the real
TaskBoardSettings, TaskBoardCommand parsing, and TaskBoardCodexSession with fakes only
at the SDK transport boundary. No network is used.
"""

from __future__ import annotations

import asyncio
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from vidbyte_cli.commands.runtime.task_board import TaskBoardCommand  # noqa: E402
from vidbyte_cli.lib.errors.failures import TaskBoardDependencyInvalid  # noqa: E402
from vidbyte_cli.lib.runtime_primitives.executor import RuntimeExecutor  # noqa: E402
from vidbyte_cli.lib.runtime_primitives.task_board import TaskBoardCodexSession  # noqa: E402
from vidbyte_cli.types.runtime import (  # noqa: E402
    RuntimeAdmissionGrant,
    RuntimeAdmissionVerdict,
    RuntimeHost,
    RuntimeLaunchPlan,
    TaskBoardContextMode,
    TaskBoardExecutionType,
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
        task="Task board with 2 tasks starting with: a",
    )


def make_verdict() -> RuntimeAdmissionVerdict:
    # Builds an admitted verdict matching the local plan for executor tests.
    return RuntimeAdmissionVerdict(
        admitted=True, admission_id="rta_test123", capability_id="runtime.task-board@1"
    )


def make_grant() -> RuntimeAdmissionGrant:
    # Builds a time-valid grant; the runner must never touch it or the network.
    now = datetime.now(UTC)
    return RuntimeAdmissionGrant(
        admission_id="rta_test123",
        capability_id="runtime.task-board@1",
        execution_location="local",
        charged_cents=2,
        admitted_at=now - timedelta(seconds=10),
        expires_at=now + timedelta(seconds=300),
        grant_token="tok_" + "x" * 20,
    )


def _fake_reply(text: str, thread: str) -> SimpleNamespace:
    # Builds the minimal SDK reply shape the session validates.
    return SimpleNamespace(
        content=text,
        codex=SimpleNamespace(status="completed", final_response=text, thread_id=thread),
    )


def _fake_session(prompts: list[str], turns: SimpleNamespace) -> TaskBoardCodexSession:
    # Builds a session whose agents and turns are fakes recording their prompts.
    session = TaskBoardCodexSession({}, lambda _msg: None)
    session.prepare(make_plan())
    session._build_agent = lambda _i: object()
    session._turn = turns.behavior(prompts)
    return session


class _ScriptedTurns:
    # Holds one scripted reply-or-error per call for fake SDK turns.
    def __init__(self, script: list[object]) -> None:
        self._script = script
        self.calls = 0

    def behavior(self, prompts: list[str]):  # type: ignore[no-untyped-def]
        # Returns an async turn recording prompts and replaying the script.
        async def fake_turn(agent: object, prompt: str) -> SimpleNamespace:
            prompts.append(prompt)
            action = self._script[min(self.calls, len(self._script) - 1)]
            self.calls += 1
            if isinstance(action, Exception):
                raise action
            return _fake_reply(str(action), f"thread-{self.calls}")

        return fake_turn


def test_linear_default_preserved() -> None:
    # [Edge Case] Settings without flags stay linear with no dependencies.
    settings = TaskBoardSettings(tasks=("a",))
    record(
        "linear default preserved",
        settings.execution_type is TaskBoardExecutionType.LINEAR and settings.dependencies == (),
    )


def test_links_with_linear_rejected() -> None:
    # [Edge Case] --depends-on with --type linear is rejected before admission.
    try:
        TaskBoardCommand()._parse_dependencies(("1:0",), "linear", 2)
        record("links with linear rejected", False, "accepted links in linear mode")
    except TaskBoardDependencyInvalid:
        record("links with linear rejected", True)


def test_malformed_specs_rejected() -> None:
    # [Edge Case] Every malformed link shape is rejected, not partially applied.
    bad = ["8", "8:", ":2", "8-2", "a:b", "8:2.5", "", "8:2,", "8:,2", "1:0:2", "  "]
    command = TaskBoardCommand()
    rejected = 0
    for spec in bad:
        try:
            command._parse_dependencies((spec,), "dag", 9)
        except TaskBoardDependencyInvalid:
            rejected += 1
    record("malformed specs rejected", rejected == len(bad), f"{rejected}/{len(bad)}")


def test_out_of_range_rejected() -> None:
    # [Edge Case] Indices outside the board cannot become links.
    command = TaskBoardCommand()
    ok = True
    for spec in ("9:0", "0:9", "99:99"):
        try:
            command._parse_dependencies((spec,), "dag", 9)
            ok = False
        except TaskBoardDependencyInvalid:
            pass
    record("out of range rejected", ok)


def test_self_and_duplicate_rejected() -> None:
    # [Edge Case] Self-links and repeats across flags are rejected.
    command = TaskBoardCommand()
    ok = True
    for raw in (("3:3",), ("1:0", "1:0"), ("2:0,0",)):
        try:
            command._parse_dependencies(raw, "dag", 4)
            ok = False
        except TaskBoardDependencyInvalid:
            pass
    record("self and duplicate rejected", ok)


def test_accumulated_parents_accepted() -> None:
    # [Edge Case] Repeating a child across flags accumulates, then sorts, parents.
    links = TaskBoardCommand()._parse_dependencies(("5:3", "5:2", "8:2"), "dag", 9)
    record("accumulated parents accepted", links == ((5, 2), (5, 3), (8, 2)), str(links))


def test_cycles_rejected() -> None:
    # [Hidden Failure] Two- and three-cycles fail before any agent starts.
    ok = True
    for edges in (((0, 1), (1, 0)), ((0, 1), (1, 2), (2, 0))):
        try:
            TaskBoardSettings(tasks=("a", "b", "c"), dependencies=edges)
            ok = False
        except ValueError:
            pass
    try:
        TaskBoardCommand()._settings(
            ("a", "b"), 10, "windowed-summaries", "truncate-tail", 1200,
            True, 1, "dag", ((0, 1), (1, 0)),
        )
        ok = False
    except TaskBoardDependencyInvalid:
        pass
    record("cycles rejected", ok)


def test_dag_zero_edges_board_order() -> None:
    # [Edge Case] A dag with no links runs in board order with empty dep context.
    async def go() -> bool:
        prompts: list[str] = []
        session = _fake_session(prompts, _ScriptedTurns(["r0", "r1", "r2"]))
        settings = TaskBoardSettings(
            tasks=("a", "b", "c"), execution_type=TaskBoardExecutionType.DAG
        )
        result = await session._run(make_plan(), settings, "rta_dag_empty")
        return (
            [step.index for step in result.steps] == [0, 1, 2]
            and result.completed == 3
            and all("(no prior results)" in prompt for prompt in prompts)
        )

    record("dag zero edges board order", asyncio.run(go()))


def test_single_task_dag() -> None:
    # [Edge Case] One task with no parents completes with empty dep context.
    async def go() -> bool:
        prompts: list[str] = []
        session = _fake_session(prompts, _ScriptedTurns(["solo"]))
        settings = TaskBoardSettings(
            tasks=("only",), execution_type=TaskBoardExecutionType.DAG
        )
        result = await session._run(make_plan(), settings, "rta_dag_solo")
        return result.completed == 1 and "(no prior results)" in prompts[0]

    record("single task dag", asyncio.run(go()))


def test_topological_order_pulls_dependency_first() -> None:
    # [Silent Failure] Task 0 depending on task 2 runs after it, deterministically.
    async def go() -> bool:
        prompts: list[str] = []
        session = _fake_session(prompts, _ScriptedTurns(["r0", "r1", "r2", "r3"]))
        settings = TaskBoardSettings(
            tasks=("a", "b", "c", "d"),
            execution_type=TaskBoardExecutionType.DAG,
            dependencies=((0, 2),),
        )
        result = await session._run(make_plan(), settings, "rta_dag_order")
        first_runs = [prompt.split(":")[0] for prompt in prompts]
        return [step.index for step in result.steps] == [1, 2, 0, 3] and first_runs == [
            "Task 1",
            "Task 2",
            "Task 0",
            "Task 3",
        ]

    record("topological order pulls dependency first", asyncio.run(go()))


def test_task_eight_sees_only_task_two() -> None:
    # [Silent Failure] Task 8 with sole dep 8:2 sees exactly [2], never unrelated tasks.
    async def go() -> bool:
        prompts: list[str] = []
        replies = [f"outcome-{i}" for i in range(9)]
        session = _fake_session(prompts, _ScriptedTurns(replies))
        settings = TaskBoardSettings(
            tasks=tuple(f"task-{i}" for i in range(9)),
            execution_type=TaskBoardExecutionType.DAG,
            dependencies=((8, 2),),
        )
        result = await session._run(make_plan(), settings, "rta_dag_dep8")
        prompt8 = next(p for p in prompts if p.startswith("Task 8:"))
        unrelated = any(f"[{i}] " in prompt8 for i in (0, 1, 3, 4, 5, 6, 7))
        return result.completed == 9 and "[2] outcome-2" in prompt8 and not unrelated

    record("task eight sees only task two", asyncio.run(go()))


def test_window_ignored_in_dag() -> None:
    # [Silent Failure] Window 0 vs 10 render identical prompts for identical deps.
    session = TaskBoardCodexSession({}, lambda _msg: None)
    base = dict(tasks=("a", "b"), execution_type=TaskBoardExecutionType.DAG)
    narrow = TaskBoardSettings(dependencies=((1, 0),), window=0, **base)  # type: ignore[arg-type]
    wide = TaskBoardSettings(dependencies=((1, 0),), window=10, **base)  # type: ignore[arg-type]
    slots = ["first-summary", ""]
    record(
        "window ignored in dag",
        session._build_prompt("b", 1, slots, narrow)
        == session._build_prompt("b", 1, slots, wide),
    )


def test_truncation_markers_in_dag() -> None:
    # [Silent Failure] Over-limit dep summaries carry the marker in dag prompts too.
    async def go() -> bool:
        prompts: list[str] = []
        session = _fake_session(prompts, _ScriptedTurns(["x" * 500, "done"]))
        settings = TaskBoardSettings(
            tasks=("a", "b"),
            execution_type=TaskBoardExecutionType.DAG,
            dependencies=((1, 0),),
            summary_max_chars=100,
        )
        await session._run(make_plan(), settings, "rta_dag_trunc")
        return len(prompts) == 2 and "...[truncated 400 chars]" in prompts[1]

    record("truncation markers in dag", asyncio.run(go()))


def test_dag_stop_on_error_halts() -> None:
    # [Hidden Failure] stop_on_error halts the dag at the first failure.
    async def go() -> bool:
        prompts: list[str] = []
        session = _fake_session(prompts, _ScriptedTurns([RuntimeError("boom")]))
        settings = TaskBoardSettings(
            tasks=("a", "b"),
            execution_type=TaskBoardExecutionType.DAG,
            dependencies=((1, 0),),
            stop_on_error=True,
            max_retries_per_task=0,
        )
        result = await session._run(make_plan(), settings, "rta_dag_halt")
        return (
            result.completed == 0 and len(result.steps) == 1
            and result.steps[0].status == "failed"
        )

    record("dag stop on error halts", asyncio.run(go()))


def test_dag_skips_dependents_continues_independent() -> None:
    # [Hidden Failure] Failed tasks skip only transitive dependents; others still run.
    async def go() -> object:
        prompts: list[str] = []
        session = TaskBoardCodexSession({}, lambda _msg: None)
        session.prepare(make_plan())
        session._build_agent = lambda _i: object()
        calls = {"turns": 0}

        async def fake_turn(agent: object, prompt: str) -> SimpleNamespace:
            prompts.append(prompt)
            calls["turns"] += 1
            if prompt.startswith("Task 0:"):
                raise RuntimeError("boom")
            return _fake_reply("fine", f"thread-{calls['turns']}")

        session._turn = fake_turn
        settings = TaskBoardSettings(
            tasks=("a", "b", "c"),
            execution_type=TaskBoardExecutionType.DAG,
            dependencies=((2, 0),),
            stop_on_error=False,
            max_retries_per_task=0,
        )
        result = await session._run(make_plan(), settings, "rta_dag_skip")
        by_index = {step.index: step for step in result.steps}
        prompt1 = next(p for p in prompts if p.startswith("Task 1:"))
        return (
            by_index[0].status == "failed"
            and by_index[1].status == "completed"
            and by_index[2].status == "failed"
            and by_index[2].thread_id == "task-board-2-failed"
            and "(no prior results)" in prompt1
            and result.completed == 1
            and calls["turns"] == 2
        )

    record("dag skips dependents continues independent", bool(asyncio.run(go())))


def test_retry_success_single_entry() -> None:
    # [Hidden Failure] A retry success yields exactly one completed step entry.
    async def go() -> bool:
        prompts: list[str] = []
        session = _fake_session(
            prompts, _ScriptedTurns([RuntimeError("boom"), "recovered"])
        )
        settings = TaskBoardSettings(
            tasks=("a",),
            execution_type=TaskBoardExecutionType.DAG,
            max_retries_per_task=1,
        )
        result = await session._run(make_plan(), settings, "rta_dag_retry")
        return (
            result.completed == 1 and len(result.steps) == 1
            and result.steps[0].status == "completed"
        )

    record("retry success single entry", asyncio.run(go()))


def test_threads_unique_per_attempted_step() -> None:
    # [Silent Failure] Attempted steps never share a thread identity.
    async def go() -> bool:
        prompts: list[str] = []
        session = _fake_session(prompts, _ScriptedTurns(["r0", "r1", "r2"]))
        settings = TaskBoardSettings(
            tasks=("a", "b", "c"),
            execution_type=TaskBoardExecutionType.DAG,
            dependencies=((1, 0), (2, 1)),
        )
        result = await session._run(make_plan(), settings, "rta_dag_threads")
        threads = [step.thread_id for step in result.steps]
        return len(set(threads)) == 3 and result.completed == 3

    record("threads unique per attempted step", asyncio.run(go()))


def test_braces_not_interpolated_in_dag() -> None:
    # [Hidden Assumption] {{braces}} in dag task text are never interpolated.
    session = TaskBoardCodexSession({}, lambda _msg: None)
    settings = TaskBoardSettings(
        tasks=("fix {{original_task}} now", "next"),
        execution_type=TaskBoardExecutionType.DAG,
        dependencies=((1, 0),),
    )
    prompt = session._build_prompt("fix {{original_task}} now", 0, ["", ""], settings)
    record(
        "braces not interpolated in dag",
        "{{original_task}}" in prompt and prompt.startswith("Task 0:"),
    )


def test_isolated_dag_omits_section() -> None:
    # [Hidden Assumption] Isolated dag prompts carry no prior-results section.
    async def go() -> bool:
        prompts: list[str] = []
        session = _fake_session(prompts, _ScriptedTurns(["r0", "r1"]))
        settings = TaskBoardSettings(
            tasks=("a", "b"),
            execution_type=TaskBoardExecutionType.DAG,
            dependencies=((1, 0),),
            context_mode=TaskBoardContextMode.ISOLATED,
        )
        await session._run(make_plan(), settings, "rta_dag_isolated")
        return len(prompts) == 2 and not any("Prior summaries" in p for p in prompts)

    record("isolated dag omits section", asyncio.run(go()))


def test_executor_runs_dag_without_network() -> None:
    # [Hidden Assumption] The runner needs only the verdict; admit/verify stay in command.
    prompts: list[str] = []
    session = _fake_session(prompts, _ScriptedTurns(["r0", "r1"]))
    settings = TaskBoardSettings(
        tasks=("a", "b"),
        execution_type=TaskBoardExecutionType.DAG,
        dependencies=((1, 0),),
    )
    grant = make_grant()
    _ = grant
    result = RuntimeExecutor().execute_task_board(make_plan(), settings, session, make_verdict())
    record(
        "executor runs dag without network",
        result.completed == 2 and "[0] r0" in prompts[1],
    )


def main() -> int:
    # Runs every design-doc Section 10 dag case and reports the tally.
    test_linear_default_preserved()
    test_links_with_linear_rejected()
    test_malformed_specs_rejected()
    test_out_of_range_rejected()
    test_self_and_duplicate_rejected()
    test_accumulated_parents_accepted()
    test_cycles_rejected()
    test_dag_zero_edges_board_order()
    test_single_task_dag()
    test_topological_order_pulls_dependency_first()
    test_task_eight_sees_only_task_two()
    test_window_ignored_in_dag()
    test_truncation_markers_in_dag()
    test_dag_stop_on_error_halts()
    test_dag_skips_dependents_continues_independent()
    test_retry_success_single_entry()
    test_threads_unique_per_attempted_step()
    test_braces_not_interpolated_in_dag()
    test_isolated_dag_omits_section()
    test_executor_runs_dag_without_network()
    passed = sum(1 for status, _, _ in RESULTS if status == PASS)
    print(f"{passed}/{len(RESULTS)} tests passed")
    return 0 if passed == len(RESULTS) else 1


if __name__ == "__main__":
    raise SystemExit(main())
