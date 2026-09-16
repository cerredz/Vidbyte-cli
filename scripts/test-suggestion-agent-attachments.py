"""Offline verification for suggestion-agent attachment orchestration.

The script exercises request resolution, repeated-stage forwarding, native Codex conversion,
dry-run output, and the body-free result manifest. It reuses the existing suggestion fake so no
provider, credentials, or network access are needed.
"""

from __future__ import annotations

import hashlib
import json
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT / "src"))

from test_suggestions import FakeSdk, _attachment_bundle, _request, _run_cli  # noqa: E402

from vidbyte_cli.commands.agents.suggestion.render import SuggestionRenderer  # noqa: E402
from vidbyte_cli.commands.agents.suggestion.request_builder import (  # noqa: E402
    SuggestionRequestBuilder,
)
from vidbyte_cli.lib.errors.failures import AttachmentFileNotFound  # noqa: E402
from vidbyte_cli.lib.io.attachments import AttachmentResolver  # noqa: E402
from vidbyte_cli.lib.io.codex_attachments import CodexAttachmentInputBuilder  # noqa: E402
from vidbyte_cli.services.suggestions.service import SuggestionService  # noqa: E402
from vidbyte_cli.types.attachments import AttachmentBundle  # noqa: E402


class Results:
    """Prints one result for each assertion and returns the process status."""

    def __init__(self) -> None:
        # Starts counters used for the final pass/fail status.
        self.passed = 0
        self.failed = 0

    def check(self, name: str, condition: bool, detail: str = "") -> None:
        if condition:
            self.passed += 1
            print(f"PASS: {name}")
        else:
            self.failed += 1
            suffix = f" - {detail}" if detail else ""
            print(f"FAIL: {name}{suffix}", file=sys.stderr)

    def summary(self) -> int:
        total = self.passed + self.failed
        print(f"\n{self.passed}/{total} tests passed")
        return int(self.failed > 0)


@dataclass(frozen=True)
class FakeText:
    """Represents a native SDK text item for adapter assertions."""

    text: str


@dataclass(frozen=True)
class FakeImage:
    """Represents a native SDK image item for adapter assertions."""

    path: str


@dataclass(frozen=True)
class FakeFile:
    """Represents an SDK file context item for adapter assertions."""

    path: str
    absolute_path: str
    size_bytes: int
    content: str | None
    language: str | None
    metadata: dict[str, str]


@dataclass(frozen=True)
class FakeRun:
    """Represents a native SDK run input containing items and context."""

    items: tuple[object, ...]
    context_items: tuple[object, ...]


class AttachmentIntegrationSuite:
    """Runs all suggestion-specific attachment checks against local collaborators."""

    def __init__(self, results: Results) -> None:
        # Stores the reporter shared by every focused attachment case.
        self.results = results

    def run(self) -> None:
        # Executes request, provider, output, and compatibility checks in order.
        self.check_request_resolution()
        self.check_preflight_failure()
        self.check_stage_forwarding()
        self.check_native_adapter()
        self.check_dry_run_and_output()
        self.check_existing_files_semantics()

    def check_request_resolution(self) -> None:
        # [Silent Failure] Request order, snapshot bytes, and hashes must remain aligned.
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            first = root / "first.md"
            second = root / "second.txt"
            first.write_text("first snapshot", encoding="utf-8")
            second.write_text("second snapshot", encoding="utf-8")
            request = SuggestionRequestBuilder().build(
                {
                    "goal": "Use attached evidence",
                    "count": 2,
                    "attachments": (first, second),
                }
            )
            first.write_text("changed after resolve", encoding="utf-8")
        items = request.attachments.items
        self.results.check(
            "request stores ordered immutable snapshots",
            tuple(item.name for item in items) == ("first.md", "second.txt")
            and items[0].content == "first snapshot"
            and items[0].sha256 == hashlib.sha256(b"first snapshot").hexdigest(),
        )

    def check_preflight_failure(self) -> None:
        # [Hidden Failure] Invalid files fail before a service could load its provider SDK.
        with tempfile.TemporaryDirectory() as temporary:
            missing = Path(temporary) / "missing.md"
            try:
                SuggestionRequestBuilder().build(
                    {"goal": "Preflight", "count": 2, "attachments": (missing,)}
                )
            except AttachmentFileNotFound:
                failed_closed = True
            else:
                failed_closed = False
        self.results.check("missing attachment fails during request preflight", failed_closed)

    def check_stage_forwarding(self) -> None:
        # [Hidden Assumption] Every independent generator and critic turn receives the bundle.
        bundle = _attachment_bundle()
        fake = FakeSdk(revision=True)
        result = SuggestionService(sdk=fake).run(_request(rounds=2, items=(), attachments=bundle))
        self.results.check(
            "generator critic and revision share one attachment bundle",
            bool(fake.inputs) and all(input_.attachments is bundle for input_ in fake.inputs),
        )
        self.results.check(
            "result manifest is ordered and body-free",
            result.attachment_manifest == bundle.manifest()
            and all("content" not in entry for entry in result.attachment_manifest),
        )
        extra = FakeSdk(extra_compute=True)
        SuggestionService(sdk=extra).run(
            _request(
                categories=("verification",),
                count=2,
                extra_compute=True,
                attachments=bundle,
            )
        )
        self.results.check(
            "extra-compute generator turns share the same attachment bundle",
            bool(extra.inputs) and all(input_.attachments is bundle for input_ in extra.inputs),
        )

    def check_native_adapter(self) -> None:
        # [Silent Failure] Text and image attachments must map to their native SDK modalities.
        self.install_fake_codex()
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            text = root / "spec.md"
            image = root / "screen.png"
            text.write_text("before mutation", encoding="utf-8")
            image.write_bytes(b"image bytes")
            bundle = AttachmentResolver().resolve((text, image))
            text.write_text("after mutation", encoding="utf-8")
            run = CodexAttachmentInputBuilder().build("inspect files", bundle)
        self.results.check(
            "adapter preserves text snapshot and native image",
            isinstance(run.items[0], FakeText)
            and isinstance(run.items[1], FakeImage)
            and run.context_items[0].content == "before mutation"
            and run.items[1].path.endswith("screen.png"),
        )
        empty = CodexAttachmentInputBuilder().build("text only", AttachmentBundle())
        self.results.check(
            "empty bundle keeps one text-only run input",
            len(empty.items) == 1
            and not empty.context_items
            and empty.items[0].text == "text only",
        )

    def install_fake_codex(self) -> None:
        # Installs only the SDK-shaped classes required by the lazy attachment adapter.
        primitives = ModuleType("vidbyte.context.primitives")
        primitives.FileContextItem = FakeFile  # type: ignore[attr-defined]
        codex = ModuleType("vidbyte.lib.dataclasses.codex")
        codex.CodexLocalImageInput = FakeImage  # type: ignore[attr-defined]
        codex.CodexRunInput = FakeRun  # type: ignore[attr-defined]
        codex.CodexTextInput = FakeText  # type: ignore[attr-defined]
        sys.modules["vidbyte"] = ModuleType("vidbyte")
        sys.modules["vidbyte.context"] = ModuleType("vidbyte.context")
        sys.modules["vidbyte.context.primitives"] = primitives
        sys.modules["vidbyte.lib"] = ModuleType("vidbyte.lib")
        sys.modules["vidbyte.lib.dataclasses"] = ModuleType("vidbyte.lib.dataclasses")
        sys.modules["vidbyte.lib.dataclasses.codex"] = codex

    def check_dry_run_and_output(self) -> None:
        # [Edge Case] Dry-run resolves files but never needs provider execution.
        with tempfile.TemporaryDirectory() as temporary:
            attachment = Path(temporary) / "dry-run.txt"
            attachment.write_text("private attachment body", encoding="utf-8")
            completed = _run_cli(
                [
                    "--json",
                    "agents",
                    "suggest",
                    "run",
                    "--goal",
                    "Dry run",
                    "--dry-run",
                    "--attach",
                    str(attachment),
                ]
            )
        try:
            data = json.loads(completed.stdout).get("data", {})
        except json.JSONDecodeError:
            data = {}
        manifest = data.get("attachment_manifest", [])
        self.results.check(
            "dry-run returns attachment metadata without a body",
            completed.returncode == 0
            and len(manifest) == 1
            and manifest[0].get("name") == "dry-run.txt"
            and "content" not in manifest[0],
        )
        result = SuggestionService(sdk=FakeSdk()).run(_request(attachments=_attachment_bundle()))
        human = SuggestionRenderer()._human_result(result)
        self.results.check(
            "human output names attachments without printing bodies",
            "notes.md" in human and "attachment snapshot" not in human,
        )
        text_only = SuggestionService(sdk=FakeSdk()).run(_request())
        text_only_human = SuggestionRenderer()._human_result(text_only)
        self.results.check(
            "text-only human output keeps its existing shape",
            "Attachments:" not in text_only_human,
        )

    def check_existing_files_semantics(self) -> None:
        # [Hidden Assumption] Existing --files remains semantic context, not generic input.
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "context.md"
            path.write_text("semantic context", encoding="utf-8")
            request = SuggestionRequestBuilder().build(
                {"goal": "Keep files semantics", "count": 2, "files": (path,)}
            )
        self.results.check(
            "existing files remain context items and not attachments",
            request.attachments == AttachmentBundle()
            and request.context_items[0].kind == "file"
            and request.context_items[0].content == "semantic context",
        )


def main() -> int:
    # Runs every suggestion attachment case and returns a CI-friendly status.
    results = Results()
    AttachmentIntegrationSuite(results).run()
    return results.summary()


if __name__ == "__main__":
    raise SystemExit(main())
