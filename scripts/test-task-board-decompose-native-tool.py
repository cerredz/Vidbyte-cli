"""Offline verification for native task-board decomposition.

The script drives the real SDK-decorated tool, CLI settings, prompts, and mutable session with
fake turns only at the transport seam. It never starts Codex, calls the backend, or spends money.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from vidbyte.tools import ToolCall, ToolStatus  # noqa: E402

from vidbyte_cli.commands.runtime.task_board import (  # noqa: E402
    TaskBoardCommand,
    TaskBoardOptions,
)
from vidbyte_cli.lib.constants.runtime import TaskBoardLimit  # noqa: E402
from vidbyte_cli.lib.errors.failures import TaskBoardDecomposeInvalid  # noqa: E402
from vidbyte_cli.lib.runtime_primitives.task_board import (  # noqa: E402
    TaskBoardCodexSession,
    TaskBoardDecomposeCapture,
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
        task="Task board with native decomposition",
    )


def fake_reply(text: str, thread: str) -> SimpleNamespace:
    # Builds the minimal SDK reply shape the session validates.
    return SimpleNamespace(
        content=text,
        codex=SimpleNamespace(status="completed", final_response=text, thread_id=thread),
    )


def scripted_session(
    replies: list[str], tool_calls: dict[int, list[str]] | None = None
) -> tuple[TaskBoardCodexSession, list[str], list[int]]:
    # Builds a fake session that invokes native tools when a parent index is configured.
    session = TaskBoardCodexSession({}, lambda _message: None)
    session.prepare(make_plan())
    prompts: list[str] = []
    tool_indices: list[int] = []
    calls = tool_calls or {}
    state = {"reply": 0}

    def fake_build(index: int, settings: object, decompose_tool: object | None = None) -> object:
        # Simulates Codex issuing the configured native call before its final response.
        if decompose_tool is not None and index in calls:
            tool_indices.append(index)
            decompose_tool(subtasks=calls[index])  # type: ignore[operator]
        return object()

    async def fake_turn(agent: object, prompt: str, settings: object) -> SimpleNamespace:
        # Returns one deterministic completed turn per agent construction.
        del agent, settings
        prompts.append(prompt)
        number = state["reply"]
        state["reply"] += 1
        return fake_reply(replies[number], f"thread-{number}")

    session._build_agent = fake_build  # type: ignore[method-assign]
    session._turn = fake_turn  # type: ignore[method-assign]
    return session, prompts, tool_indices


def test_defaults_and_bounds() -> None:
    # [Edge Case] Decomposition stays off by default and max-subtasks is bounded 2..10.
    settings = TaskBoardSettings(tasks=("a",))
    ok = not settings.allow_decompose and settings.max_subtasks == 5
    for value in (1, 11):
        try:
            TaskBoardSettings(tasks=("a",), max_subtasks=value)
            ok = False
        except Exception:
            pass
    for value in (2, 10):
        try:
            TaskBoardSettings(tasks=("a",), max_subtasks=value)
        except Exception:
            ok = False
    record("defaults and bounds", ok)


def test_native_schema() -> None:
    # [Hidden Assumption] The public SDK decorator produces the expected native tool schema.
    capture = TaskBoardDecomposeCapture(5)
    tool = capture.build_tool()
    spec = tool.spec()  # type: ignore[attr-defined]
    schema = spec.input_schema or {}
    property_schema = schema.get("properties", {}).get("subtasks", {})
    record(
        "native tool schema",
        spec.name == "decompose_tool"
        and spec.permission.value == "safe"
        and "self-contained" in spec.description
        and property_schema.get("type") == "array"
        and "subtasks" in schema.get("required", []),
    )


def test_agent_wiring() -> None:
    # [Hidden Assumption] The CLI passes the public tool into the Codex facade with the flag on.
    session = TaskBoardCodexSession({}, lambda _message: None)
    session.prepare(make_plan())
    tool = TaskBoardDecomposeCapture(5).build_tool()
    agent = session._build_agent(
        0,
        TaskBoardSettings(tasks=("a",), allow_decompose=True),
        tool,
    )
    record(
        "agent native-tool wiring",
        len(agent.settings.tools) == 1
        and agent.settings.tools[0].spec().name == "decompose_tool"
        and agent.settings.codex.client.experimental_api,
    )


def test_native_capture_and_duplicate_guard() -> None:
    # [Hidden Failure] One accepted native call is captured and later calls cannot overwrite it.
    capture = TaskBoardDecomposeCapture(5)
    tool = capture.build_tool()
    first = tool(subtasks=[" A ", "B"])  # type: ignore[operator]
    second = tool(subtasks=["C", "D"])  # type: ignore[operator]
    record(
        "native capture and duplicate guard",
        "Accepted 2" in first
        and "already accepted" in second
        and capture.accepted_subtasks == ("A", "B"),
    )


def test_malformed_tool_arguments() -> None:
    # [Hidden Failure] SDK validation rejects a malformed call without mutating the board capture.
    async def go() -> bool:
        capture = TaskBoardDecomposeCapture(5)
        tool = capture.build_tool()
        result = await tool.execute(ToolCall("decompose_tool", {"subtasks": 7}))  # type: ignore[attr-defined]
        return result.status is ToolStatus.ERROR and capture.accepted_subtasks == ()

    record("malformed tool arguments", asyncio.run(go()))


def test_candidate_normalization() -> None:
    # [Silent Failure] Invalid candidates are dropped while order, deduplication, and cap hold.
    capture = TaskBoardDecomposeCapture(3)
    tool = capture.build_tool()
    tool(  # type: ignore[operator]
        subtasks=[" A ", "a", "", "x" * (int(TaskBoardLimit.MAX_TASK_CHARS) + 1), "B", "C", "D"]
    )
    record("candidate normalization", capture.accepted_subtasks == ("A", "B", "C"))


def test_minimum_and_plain_text() -> None:
    # [Edge Case] A single valid candidate and a normal final reply keep the parent whole.
    capture = TaskBoardDecomposeCapture(5)
    capture.build_tool()(subtasks=["only"])  # type: ignore[operator]
    session, _prompts, _indices = scripted_session(["normal final text"])
    result = asyncio.run(
        session._run(
            make_plan(),
            TaskBoardSettings(tasks=("parent",), allow_decompose=True, max_retries_per_task=0),
            "rta_plain",
        )
    )
    record(
        "minimum and plain text",
        capture.accepted_subtasks == ()
        and [step.task for step in result.steps] == ["parent"]
        and result.steps[0].summary == "normal final text",
    )


def test_exact_splice() -> None:
    # [Hidden Assumption] A parent is replaced at its index and later tasks shift right.
    session, _prompts, indices = scripted_session(
        ["a", "parent", "child one", "child two", "c"], {1: ["k1", "k2"]}
    )
    settings = TaskBoardSettings(
        tasks=("A", "B", "C"), allow_decompose=True, max_retries_per_task=0
    )
    result = asyncio.run(session._run(make_plan(), settings, "rta_splice"))
    record(
        "exact in-place splice",
        [step.task for step in result.steps] == ["A", "B", "k1", "k2", "C"]
        and [step.index for step in result.steps] == [0, 1, 1, 2, 3]
        and indices == [1],
    )


def test_isolated_prompts() -> None:
    # [Silent Failure] Parent and child prompts contain no prior or sibling context.
    session, prompts, _indices = scripted_session(
        ["parent", "child one", "child two"], {0: ["k1", "k2"]}
    )
    asyncio.run(
        session._run(
            make_plan(),
            TaskBoardSettings(tasks=("parent-work",), allow_decompose=True, max_retries_per_task=0),
            "rta_isolated",
        )
    )
    record(
        "isolated prompts",
        len(prompts) == 3
        and all("Prior summaries" not in prompt for prompt in prompts)
        and "parent-work" not in prompts[1]
        and "parent-work" not in prompts[2]
        and "k1" in prompts[1]
        and "k2" in prompts[2],
    )


def test_depth_one() -> None:
    # [Hidden Failure] Child agents receive no tool, so a child cannot create grandchildren.
    session, _prompts, indices = scripted_session(
        ["parent", "child one", "child two"], {0: ["k1", "k2"]}
    )
    result = asyncio.run(
        session._run(
            make_plan(),
            TaskBoardSettings(tasks=("parent",), allow_decompose=True, max_retries_per_task=0),
            "rta_depth",
        )
    )
    record(
        "depth one",
        [step.task for step in result.steps] == ["parent", "k1", "k2"] and indices == [0],
    )


def test_retry_and_failure() -> None:
    # [Hidden Failure] Failed attempts discard captures and failed parents never splice.
    session = TaskBoardCodexSession({}, lambda _message: None)
    session.prepare(make_plan())
    builds = {"count": 0}

    def fake_build(index: int, settings: object, decompose_tool: object | None = None) -> object:
        # Accepts the same split on both attempts; only the successful attempt may survive.
        del index, settings
        builds["count"] += 1
        if decompose_tool is not None:
            decompose_tool(subtasks=["k1", "k2"])  # type: ignore[operator]
        return object()

    state = {"turn": 0}

    async def fake_turn(agent: object, prompt: str, settings: object) -> SimpleNamespace:
        # Fails the first attempt after the tool call, then completes the retry and children.
        del agent, prompt, settings
        state["turn"] += 1
        if state["turn"] == 1:
            raise RuntimeError("failed parent")
        return fake_reply(f"done-{state['turn']}", f"thread-{state['turn']}")

    session._build_agent = fake_build  # type: ignore[method-assign]
    session._turn = fake_turn  # type: ignore[method-assign]
    result = asyncio.run(
        session._run(
            make_plan(),
            TaskBoardSettings(tasks=("P",), allow_decompose=True, max_retries_per_task=1),
            "rta_retry",
        )
    )
    retry_ok = [step.task for step in result.steps] == ["P", "k1", "k2"] and builds["count"] == 4

    failed_session = TaskBoardCodexSession({}, lambda _message: None)
    failed_session.prepare(make_plan())
    failed_session._build_agent = lambda _index, _settings, _tool=None: object()  # type: ignore[method-assign]

    async def failed_turn(agent: object, prompt: str, settings: object) -> SimpleNamespace:
        # Fails the only parent attempt.
        del agent, prompt, settings
        raise RuntimeError("failed parent")

    failed_session._turn = failed_turn  # type: ignore[method-assign]
    failed = asyncio.run(
        failed_session._run(
            make_plan(),
            TaskBoardSettings(tasks=("P",), allow_decompose=True, max_retries_per_task=0),
            "rta_failed",
        )
    )
    record(
        "retry and failure",
        retry_ok
        and failed.failed == 1
        and len(failed.steps) == 1
        and failed.steps[0].status == "failed",
    )


def test_board_ceiling() -> None:
    # [Edge Case] Tool availability shrinks with the live board and never exceeds 500 entries.
    settings = TaskBoardSettings(tasks=("a",), allow_decompose=True)
    record(
        "board ceiling",
        TaskBoardLimit.MAX_TASKS - 500 + 1 == 1
        and TaskBoardCodexSession({}, lambda _message: None)._decompose_limit(500, 0, settings)
        is None
        and TaskBoardCodexSession({}, lambda _message: None)._decompose_limit(499, 0, settings)
        == 2,
    )


def _options(**overrides: object) -> TaskBoardOptions:
    # Builds a parsed run invocation for pre-admission conflict tests.
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
        "execution_type": "linear",
        "depends_on": (),
        "allow_decompose": True,
        "max_subtasks": 5,
        "model": "",
        "sandbox": "workspace-write",
        "reasoning_effort": "",
        "turn_timeout": 600,
        "key": None,
        "checkpoint": False,
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


def test_index_conflicts_and_literal_rendering() -> None:
    # [Hidden Assumption] Mutable indices refuse checkpoint/DAG state and preserve literal braces.
    command = TaskBoardCommand()
    conflicts: list[str] = []
    for override in ({"execution_type": "dag"}, {"checkpoint": True}):
        try:
            command._settings(("a", "b"), _options(**override))
        except TaskBoardDecomposeInvalid as error:
            conflicts.append(error.message)
    session, prompts, _indices = scripted_session(["done"])
    asyncio.run(
        session._run(
            make_plan(),
            TaskBoardSettings(
                tasks=("use {{value}} here",), allow_decompose=True, max_retries_per_task=0
            ),
            "rta_literal",
        )
    )
    record(
        "index conflicts and literal rendering",
        len(conflicts) == 2
        and "--type dag" in conflicts[0]
        and "checkpointing" in conflicts[1]
        and "{{value}}" in prompts[0],
    )


def main() -> int:
    # Runs every native decomposition design-doc case and reports the tally.
    test_defaults_and_bounds()
    test_native_schema()
    test_agent_wiring()
    test_native_capture_and_duplicate_guard()
    test_malformed_tool_arguments()
    test_candidate_normalization()
    test_minimum_and_plain_text()
    test_exact_splice()
    test_isolated_prompts()
    test_depth_one()
    test_retry_and_failure()
    test_board_ceiling()
    test_index_conflicts_and_literal_rendering()
    passed = sum(1 for status, _name, _detail in RESULTS if status == PASS)
    print(f"{passed}/{len(RESULTS)} tests passed")
    return 0 if passed == len(RESULTS) else 1


if __name__ == "__main__":
    raise SystemExit(main())
