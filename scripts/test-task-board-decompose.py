"""Verification for task-board decomposition: isolated prompts, in-place splice.

Run with `python scripts/test-task-board-decompose.py`. Every case drives the real
TaskBoardDecomposeParser, TaskBoardSummarizer, TaskBoardSettings, and
TaskBoardCodexSession with fakes only at the SDK transport boundary. No network.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from vidbyte_cli.lib.runtime_primitives.task_board import (  # noqa: E402
    TaskBoardCodexSession,
    TaskBoardDecomposeParser,
)
from vidbyte_cli.types.runtime import (  # noqa: E402
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
        task="Task board with 3 tasks starting with: a",
    )


def _fake_reply(text: str, thread: str) -> SimpleNamespace:
    # Builds the minimal SDK reply shape the session validates.
    return SimpleNamespace(
        content=text,
        codex=SimpleNamespace(status="completed", final_response=text, thread_id=thread),
    )


def _session_with_script(replies: list[str]) -> tuple[TaskBoardCodexSession, list[str]]:
    # Fake session whose turns replay one reply body per call in order.
    session = TaskBoardCodexSession({}, lambda _msg: None)
    session.prepare(make_plan())
    session._build_agent = lambda _i: object()  # type: ignore[method-assign]
    seen: list[str] = []
    state = {"n": 0}

    async def fake_turn(agent: object, prompt: str) -> SimpleNamespace:
        seen.append(prompt)
        body = replies[state["n"]] if state["n"] < len(replies) else f"plain-{state['n']}"
        state["n"] += 1
        return _fake_reply(body, f"thread-{state['n']}")

    session._turn = fake_turn  # type: ignore[method-assign]
    return session, seen


def test_defaults_off() -> None:
    # [Edge Case] Decomposition is off unless the caller opts in.
    settings = TaskBoardSettings(tasks=("a",))
    record(
        "decomposition off by default",
        settings.allow_decompose is False and settings.max_subtasks == 5,
    )


def test_max_subtasks_bounds() -> None:
    # [Edge Case] Per-parent bound holds 2..10 and rejects 1 and 11.
    ok = True
    try:
        TaskBoardSettings(tasks=("a",), allow_decompose=True, max_subtasks=1)
        ok = False
    except Exception:
        pass
    try:
        TaskBoardSettings(tasks=("a",), allow_decompose=True, max_subtasks=11)
        ok = False
    except Exception:
        pass
    try:
        TaskBoardSettings(tasks=("a",), allow_decompose=True, max_subtasks=2)
        TaskBoardSettings(tasks=("a",), allow_decompose=True, max_subtasks=10)
    except Exception:
        ok = False
    record("max subtasks bounded 2..10", ok)


def test_no_block_means_no_decompose() -> None:
    # [Edge Case] Plain final text with no fenced block completes normally.
    parser = TaskBoardDecomposeParser()
    record("plain text parses empty", parser.parse_final_text("did the work", 5) == ())


def test_valid_block_parses_in_order() -> None:
    # [Edge Case] A valid two-item block returns both subtasks in order.
    parser = TaskBoardDecomposeParser()
    text = 'Done.\n```decompose\n["first subtask", "second subtask"]\n```'
    record(
        "valid block parses in order",
        parser.parse_final_text(text, 5) == ("first subtask", "second subtask"),
    )


def test_single_candidate_dropped() -> None:
    # [Edge Case] One candidate is below the minimum of two, so no split happens.
    parser = TaskBoardDecomposeParser()
    record(
        "single candidate dropped", parser.parse_final_text('```decompose\n["only"]\n```', 5) == ()
    )


def test_malformed_blocks_parse_empty() -> None:
    # [Silent Failure] Bad fences, bad JSON, and non-array JSON never decompose.
    parser = TaskBoardDecomposeParser()
    cases = [
        "no fence at all",
        "```decompose\n[unclosed",
        '```decompose\n{"a": 1}\n```',
        '```decompose\n"scalar"\n```',
        "```decompose\n[1, 2]\n```",
    ]
    record("malformed blocks parse empty", all(parser.parse_final_text(c, 5) == () for c in cases))


def test_dedupe_and_truncation() -> None:
    # [Silent Failure] Case-insensitive duplicates collapse; count caps at max.
    parser = TaskBoardDecomposeParser()
    text = '```decompose\n["A", "a", "B", "C", "D"]\n```'
    record("dedupe and cap applied", parser.parse_final_text(text, 3) == ("A", "B", "C"))


def test_overlong_candidate_dropped() -> None:
    # [Silent Failure] A >20k-char candidate drops while valid siblings survive.
    parser = TaskBoardDecomposeParser()
    text = '```decompose\n["ok one", "' + "x" * 20_001 + '", "ok two"]\n```'
    record("overlong candidate dropped", parser.parse_final_text(text, 5) == ("ok one", "ok two"))


def test_strip_block_removes_fence() -> None:
    # [Hidden Assumption] Stored summaries hold outcome text, never the fence.
    parser = TaskBoardDecomposeParser()
    text = 'outcome here\n```decompose\n["a", "b"]\n```'
    stripped = parser.strip_block(text)
    record("block stripped from text", stripped == "outcome here" and "decompose" not in stripped)


def test_splice_positions_exact() -> None:
    # [Silent Failure] Decomposing index 1 of [A,B,C] yields [A,K1,K2,K3,C].
    async def go() -> bool:
        session, _seen = _session_with_script(
            ["plain-a", 'done\n```decompose\n["k1", "k2", "k3"]\n```', "c1", "c2", "c3", "plain-c"]
        )
        settings = TaskBoardSettings(
            tasks=("A", "B", "C"), allow_decompose=True, stop_on_error=False, max_retries_per_task=0
        )
        result = await session._run(make_plan(), settings, "rta_splice")
        tasks = [step.task for step in result.steps]
        indices = [step.index for step in result.steps]
        return tasks == ["A", "B", "k1", "k2", "k3", "C"] and indices == [0, 1, 1, 2, 3, 4]

    record("splice positions exact", asyncio.run(go()))


def test_child_prompts_isolated() -> None:
    # [Silent Failure] Child prompts carry only their own subtask text.
    async def go() -> bool:
        session, seen = _session_with_script(['done\n```decompose\n["k1", "k2"]\n```', "c1", "c2"])
        settings = TaskBoardSettings(
            tasks=("parent-work",), allow_decompose=True, max_retries_per_task=0
        )
        await session._run(make_plan(), settings, "rta_iso")
        if len(seen) != 3:
            return False
        if "parent-work" in seen[1] or "parent-work" in seen[2]:
            return False
        if "Prior summaries" in seen[1] or "Prior summaries" in seen[2]:
            return False
        return "k1" in seen[1] and "k2" in seen[2] and "sibling" not in seen[1].lower()

    record("child prompts isolated", asyncio.run(go()))


def test_window_ignored_when_on() -> None:
    # [Silent Failure] Window 0 vs 10 render identical decompose prompts.
    async def go() -> bool:
        first, seen_first = _session_with_script(["plain"])
        await first._run(
            make_plan(),
            TaskBoardSettings(
                tasks=("a", "b"), window=0, allow_decompose=True, max_retries_per_task=0
            ),
            "rta_w0",
        )
        second, seen_second = _session_with_script(["plain"])
        await second._run(
            make_plan(),
            TaskBoardSettings(
                tasks=("a", "b"), window=10, allow_decompose=True, max_retries_per_task=0
            ),
            "rta_w10",
        )
        return seen_first == seen_second

    record("window ignored when on", asyncio.run(go()))


def test_depth_one_children_ignore_blocks() -> None:
    # [Silent Failure] A child carrying its own block still runs as normal work.
    async def go() -> bool:
        session, _seen = _session_with_script(
            ['p\n```decompose\n["k1", "k2"]\n```', 'c\n```decompose\n["x", "y", "z"]\n```', "c2"]
        )
        settings = TaskBoardSettings(tasks=("P",), allow_decompose=True, max_retries_per_task=0)
        result = await session._run(make_plan(), settings, "rta_depth")
        tasks = [step.task for step in result.steps]
        return tasks == ["P", "k1", "k2"] and result.completed == 3

    record("depth one enforced", asyncio.run(go()))


def test_failed_parent_never_splices() -> None:
    # [Hidden Failure] A parent that exhausts retries records failure with no children.
    async def go() -> bool:
        session = TaskBoardCodexSession({}, lambda _msg: None)
        session.prepare(make_plan())
        session._build_agent = lambda _i: object()  # type: ignore[method-assign]

        async def fake_turn(agent: object, prompt: str) -> SimpleNamespace:
            raise RuntimeError("boom")

        session._turn = fake_turn  # type: ignore[method-assign]
        settings = TaskBoardSettings(
            tasks=("P",), allow_decompose=True, stop_on_error=True, max_retries_per_task=0
        )
        result = await session._run(make_plan(), settings, "rta_fail")
        return result.failed == 1 and len(result.steps) == 1 and result.steps[0].status == "failed"

    record("failed parent never splices", asyncio.run(go()))


def test_retry_yields_single_splice() -> None:
    # [Hidden Failure] A first-attempt crash then success splices exactly once.
    async def go() -> bool:
        session = TaskBoardCodexSession({}, lambda _msg: None)
        session.prepare(make_plan())
        session._build_agent = lambda _i: object()  # type: ignore[method-assign]
        state = {"n": 0}

        async def fake_turn(agent: object, prompt: str) -> SimpleNamespace:
            state["n"] += 1
            if state["n"] == 1:
                raise RuntimeError("boom")
            if state["n"] == 2:
                return _fake_reply('p\n```decompose\n["k1", "k2"]\n```', "t2")
            return _fake_reply("child done", f"t{state['n']}")

        session._turn = fake_turn  # type: ignore[method-assign]
        settings = TaskBoardSettings(tasks=("P",), allow_decompose=True, max_retries_per_task=1)
        result = await session._run(make_plan(), settings, "rta_retry")
        return [s.task for s in result.steps] == ["P", "k1", "k2"]

    record("retry yields single splice", asyncio.run(go()))


def test_braces_not_interpolated() -> None:
    # [Hidden Assumption] Task text with {{...}} reaches the prompt verbatim.
    async def go() -> bool:
        session, seen = _session_with_script(["plain"])
        settings = TaskBoardSettings(
            tasks=("use {{value}} here",), allow_decompose=True, max_retries_per_task=0
        )
        await session._run(make_plan(), settings, "rta_braces")
        return "{{value}}" in seen[0]

    record("braces not interpolated", asyncio.run(go()))


def main() -> int:
    # Runs every design-doc Section 10 decompose case and reports the tally.
    test_defaults_off()
    test_max_subtasks_bounds()
    test_no_block_means_no_decompose()
    test_valid_block_parses_in_order()
    test_single_candidate_dropped()
    test_malformed_blocks_parse_empty()
    test_dedupe_and_truncation()
    test_overlong_candidate_dropped()
    test_strip_block_removes_fence()
    test_splice_positions_exact()
    test_child_prompts_isolated()
    test_window_ignored_when_on()
    test_depth_one_children_ignore_blocks()
    test_failed_parent_never_splices()
    test_retry_yields_single_splice()
    test_braces_not_interpolated()
    passed = sum(1 for status, _, _ in RESULTS if status == PASS)
    print(f"{passed}/{len(RESULTS)} tests passed")
    return 0 if passed == len(RESULTS) else 1


if __name__ == "__main__":
    raise SystemExit(main())
