"""Verification for the task-board primitive: window, summaries, gateway order.

Run with `python scripts/test-task-board.py`. Every case drives the real
TaskBoardSummarizer, TaskBoardSettings, RuntimeLaunchPlanner, RuntimeAdmissionGate,
and RuntimeExecutor with fakes only at the SDK transport boundary. No network is used.
"""

from __future__ import annotations

import asyncio
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from vidbyte_cli.lib.errors.failures import RuntimeAdmissionNotVerified  # noqa: E402
from vidbyte_cli.lib.runtime_primitives.executor import RuntimeExecutor  # noqa: E402
from vidbyte_cli.lib.runtime_primitives.gate import RuntimeAdmissionGate  # noqa: E402
from vidbyte_cli.lib.runtime_primitives.planner import RuntimeLaunchPlanner  # noqa: E402
from vidbyte_cli.lib.runtime_primitives.task_board import (  # noqa: E402
    TaskBoardCodexSession,
    TaskBoardSummarizer,
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


def make_grant(capability: str, cents: int = 2) -> RuntimeAdmissionGrant:
    # Builds a time-valid grant the online gate accepts when receipts match.
    now = datetime.now(UTC)
    return RuntimeAdmissionGrant(
        admission_id="rta_test123",
        capability_id=capability,
        execution_location="local",
        charged_cents=cents,
        admitted_at=now - timedelta(seconds=10),
        expires_at=now + timedelta(seconds=300),
        grant_token="tok_" + "x" * 20,
    )


def make_plan(capability: str = "runtime.task-board@1") -> RuntimeLaunchPlan:
    # Builds a local-only plan pointing at the current directory for tests.
    return RuntimeLaunchPlan(
        capability_id=capability,
        host=RuntimeHost.CODEX,
        executable=Path(sys.executable),
        working_directory=Path.cwd(),
        task="Task board with 2 tasks starting with: a",
    )


def test_empty_tasks_rejected() -> None:
    # [Edge Case] Empty board is rejected before admission.
    try:
        TaskBoardSettings(tasks=(), window=10)
        record("empty tasks rejected", False, "accepted empty tuple")
    except Exception:
        record("empty tasks rejected", True)


def test_too_many_tasks_rejected() -> None:
    # [Edge Case] 501 tasks exceed the 500 bound.
    try:
        TaskBoardSettings(tasks=tuple(f"t{i}" for i in range(501)), window=10)
        record("501 tasks rejected", False, "accepted oversize board")
    except Exception:
        record("501 tasks rejected", True)


def test_single_task_empty_context() -> None:
    # [Edge Case] Single task with window 10 renders no-prior marker.
    s = TaskBoardSummarizer()
    record(
        "single task empty context",
        s.render_prompt("do it", 0, "")
        == "Task 0: do it\n\nPrior summaries:\n(no prior results)\n\nComplete only this task.",
    )


def test_exact_limit_passthrough() -> None:
    # [Edge Case] Summary at exactly the limit passes through unmarked.
    s = TaskBoardSummarizer()
    record("exact limit passthrough", s.summarize("a" * 1200, "truncate-tail", 1200) == "a" * 1200)


def test_one_over_marks_truncation() -> None:
    # [Edge Case] One char over the limit appends a truncation marker.
    s = TaskBoardSummarizer()
    out = s.summarize("a" * 1201, "truncate-tail", 1200)
    record("one-over marks truncation", out.endswith("...[truncated 1 chars]") and len(out) > 1200)


def test_window_slice_exact() -> None:
    # [Silent Failure] Task 90 window 10 sees exactly 80..89.
    s = TaskBoardSummarizer()
    summaries = [f"r{i}" for i in range(100)]
    got = s.windowed(summaries, 90, 10)
    record("window 90 sees 80-89", tuple(i for i, _ in got) == tuple(range(80, 90)))


def test_window_clamps_to_prefix() -> None:
    # [Edge Case] Window larger than history clamps to the available prefix.
    s = TaskBoardSummarizer()
    got = s.windowed(["a", "b"], 2, 10)
    record("window clamps to prefix", tuple(i for i, _ in got) == (0, 1))


def test_window_zero_sees_nothing() -> None:
    # [Edge Case] Window 0 yields an empty context slice.
    s = TaskBoardSummarizer()
    record("window zero empty", s.windowed(["a", "b"], 2, 0) == ())


def test_head_tail_even_split() -> None:
    # [Silent Failure] head-tail keeps head and tail evenly instead of dropping tail.
    s = TaskBoardSummarizer()
    out = s.summarize("H" * 600 + "T" * 600, "head-tail", 200)
    record(
        "head-tail even split",
        out.startswith("H" * 100) and out.endswith("T" * 100) and "truncated 1000 chars" in out,
    )


def test_template_braces_not_interpolated() -> None:
    # [Hidden Assumption] {{braces}} in task text are never interpolated.
    s = TaskBoardSummarizer()
    out = s.render_prompt("fix {{original_task}} now", 3, "[0] ok")
    record("braces not interpolated", "{{original_task}}" in out and "Task 3:" in out)


def test_gate_admits_matching_grant() -> None:
    # [Hidden Failure] Matching grant and verified receipt admit the board.
    plan = make_plan()
    grant = make_grant("runtime.task-board@1")
    verdict = RuntimeAdmissionGate().verify_online(plan, grant, grant)
    record(
        "gate admits matching grant",
        verdict.admitted and verdict.capability_id == "runtime.task-board@1",
    )


def test_gate_rejects_capability_mismatch() -> None:
    # [Hidden Failure] Persistence grant reused for task-board is rejected.
    plan = make_plan()
    grant = make_grant("runtime.persistence@1")
    verdict = RuntimeAdmissionGate().verify_online(plan, grant, grant)
    record("gate rejects capability mismatch", not verdict.admitted)


def test_gate_rejects_price_drift() -> None:
    # [Hidden Failure] Wrong charged cents fail the price check.
    plan = make_plan()
    grant = make_grant("runtime.task-board@1", cents=25)
    verdict = RuntimeAdmissionGate().verify_online(plan, grant, grant)
    record("gate rejects price drift", not verdict.admitted)


def test_executor_requires_verdict() -> None:
    # [Hidden Assumption] Missing verdict never reaches the runner.
    try:
        RuntimeExecutor().execute_task_board(
            make_plan(), TaskBoardSettings(tasks=("a",)), object(), None
        )  # type: ignore[arg-type]
        record("executor requires verdict", False, "ran without verdict")
    except RuntimeAdmissionNotVerified:
        record("executor requires verdict", True)
    except Exception as error:
        record("executor requires verdict", False, f"wrong error {type(error).__name__}")


def test_executor_rejects_wrong_capability() -> None:
    # [Silent Failure] Persistence plan cannot drive the task-board runner.
    from vidbyte_cli.types.runtime import RuntimeAdmissionVerdict

    plan = make_plan("runtime.persistence@1")
    verdict = RuntimeAdmissionVerdict(
        admitted=True, admission_id="rta_x", capability_id="runtime.persistence@1"
    )
    try:
        RuntimeExecutor().execute_task_board(
            plan, TaskBoardSettings(tasks=("a",)), object(), verdict
        )
        record("executor rejects wrong capability", False, "ran with wrong capability")
    except RuntimeAdmissionNotVerified:
        record("executor rejects wrong capability", True)


def test_planner_rejects_blank_task() -> None:
    # [Hidden Assumption] Blank entries are rejected before host resolution.
    from vidbyte_cli.lib.runtime_primitives.hosts import RuntimeHostRegistry

    try:
        RuntimeLaunchPlanner(RuntimeHostRegistry()).build_task_board(("  ",), None, Path.cwd())
        record("planner rejects blank task", False, "accepted blank")
    except Exception:
        record("planner rejects blank task", True)


def _fake_reply(text: str, thread: str) -> SimpleNamespace:
    # Builds the minimal SDK reply shape the session validates.
    return SimpleNamespace(
        content=text,
        codex=SimpleNamespace(status="completed", final_response=text, thread_id=thread),
    )


def test_separate_threads_per_task() -> None:
    # [Silent Failure] Each task gets a unique thread; no resume across tasks.
    async def go() -> bool:
        session = TaskBoardCodexSession({}, lambda _msg: None)
        session.prepare(make_plan())
        calls: list[str] = []

        def fake_build(index: int) -> object:
            # Avoids SDK import while tracking per-task construction.
            calls.append(f"agent-{index}")
            return object()

        async def fake_turn(agent: object, prompt: str) -> SimpleNamespace:
            # Returns a distinct thread per prompt in call order.
            idx = len([c for c in calls if c.startswith("agent-")]) - 1
            return _fake_reply(f"outcome-{idx}", f"thread-{idx}")

        session._build_agent = fake_build  # type: ignore[method-assign]
        session._turn = fake_turn  # type: ignore[method-assign]
        settings = TaskBoardSettings(tasks=("a", "b", "c"), window=1, summary_max_chars=200)
        result = await session._run(make_plan(), settings, "rta_threads")
        threads = [step.thread_id for step in result.steps]
        return len(set(threads)) == 3 and result.completed == 3

    record("separate threads per task", asyncio.run(go()))


def test_stop_on_error_halts() -> None:
    # [Hidden Failure] stop_on_error preserves the completed prefix and halts.
    async def go() -> bool:
        session = TaskBoardCodexSession({}, lambda _msg: None)
        session.prepare(make_plan())
        session._build_agent = lambda _i: object()  # type: ignore[method-assign]

        async def fake_turn(agent: object, prompt: str) -> SimpleNamespace:
            # Fails every turn so the board must halt at index 0.
            raise RuntimeError("boom")

        session._turn = fake_turn  # type: ignore[method-assign]
        settings = TaskBoardSettings(
            tasks=("a", "b"), window=1, stop_on_error=True, max_retries_per_task=0
        )
        result = await session._run(make_plan(), settings, "rta_halt")
        return (
            result.completed == 0 and len(result.steps) == 1 and result.steps[0].status == "failed"
        )

    record("stop on error halts", asyncio.run(go()))


def test_continue_on_error_marks_failed() -> None:
    # [Hidden Failure] stop_on_error=false marks failed and continues with placeholder.
    async def go() -> bool:
        session = TaskBoardCodexSession({}, lambda _msg: None)
        session.prepare(make_plan())
        session._build_agent = lambda _i: object()  # type: ignore[method-assign]
        state = {"n": 0}

        async def fake_turn(agent: object, prompt: str) -> SimpleNamespace:
            # Fails first task, succeeds second; second prompt must see the failure placeholder.
            state["n"] += 1
            if state["n"] == 1:
                raise RuntimeError("boom")
            if "Task 0 failed." not in prompt:
                raise AssertionError("missing failure placeholder in window")
            return _fake_reply("recovered", "thread-1")

        session._turn = fake_turn  # type: ignore[method-assign]
        settings = TaskBoardSettings(
            tasks=("a", "b"), window=1, stop_on_error=False, max_retries_per_task=0
        )
        result = await session._run(make_plan(), settings, "rta_cont")
        return result.steps[0].status == "failed" and result.steps[1].status == "completed"

    try:
        record("continue on error marks failed", asyncio.run(go()))
    except AssertionError:
        record("continue on error marks failed", False, "placeholder missing")


def main() -> int:
    # Runs every design-doc Section 10 CLI case and reports the tally.
    test_empty_tasks_rejected()
    test_too_many_tasks_rejected()
    test_single_task_empty_context()
    test_exact_limit_passthrough()
    test_one_over_marks_truncation()
    test_window_slice_exact()
    test_window_clamps_to_prefix()
    test_window_zero_sees_nothing()
    test_head_tail_even_split()
    test_template_braces_not_interpolated()
    test_gate_admits_matching_grant()
    test_gate_rejects_capability_mismatch()
    test_gate_rejects_price_drift()
    test_executor_requires_verdict()
    test_executor_rejects_wrong_capability()
    test_planner_rejects_blank_task()
    test_separate_threads_per_task()
    test_stop_on_error_halts()
    test_continue_on_error_marks_failed()
    passed = sum(1 for status, _, _ in RESULTS if status == PASS)
    print(f"{passed}/{len(RESULTS)} tests passed")
    return 0 if passed == len(RESULTS) else 1


if __name__ == "__main__":
    raise SystemExit(main())
