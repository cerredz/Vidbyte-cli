"""Offline verification for the shared agent attachment contract.

The script exercises path resolution, typed failures, Click option plumbing, manifests, and
Codex conversion with a fake SDK boundary. It never starts a provider or contacts the network.
"""

from __future__ import annotations

import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import click
from click.testing import CliRunner

from vidbyte_cli.commands.agent_options import AgentAttachmentOptions
from vidbyte_cli.lib.constants.runtime import AttachmentLimit
from vidbyte_cli.lib.errors.failures import (
    AttachmentDirectory,
    AttachmentDuplicate,
    AttachmentEmpty,
    AttachmentFileNotFound,
    AttachmentInputInvalid,
    AttachmentLimitExceeded,
    AttachmentTooLarge,
    AttachmentUnreadable,
    AttachmentUnsupported,
)
from vidbyte_cli.lib.io.attachments import AttachmentResolver
from vidbyte_cli.lib.io.codex_attachments import CodexAttachmentInputBuilder
from vidbyte_cli.types.attachments import AttachmentBundle, AttachmentKind

PASS = "PASS"
FAIL = "FAIL"
RESULTS: list[tuple[str, str, str]] = []


def record(name: str, ok: bool, detail: str = "") -> None:
    # Stores one labeled result and prints it immediately for CI diagnostics.
    RESULTS.append((PASS if ok else FAIL, name, detail))
    suffix = f" — {detail}" if detail and not ok else ""
    print(f"{PASS if ok else FAIL} {name}{suffix}")


def expect_failure(name: str, expected: type[Exception], action: object) -> None:
    # Confirms that a callable raises the exact typed failure expected by the contract.
    try:
        action()  # type: ignore[operator]
    except expected:
        record(name, True)
    except Exception as error:
        record(name, False, f"raised {type(error).__name__}")
    else:
        record(name, False, "accepted invalid input")


def make_text(directory: Path, name: str, content: str) -> Path:
    # Writes one explicit UTF-8 fixture and returns its path.
    path = directory / name
    path.write_text(content, encoding="utf-8")
    return path


def test_empty_bundle() -> None:
    # [Edge Case] No paths produce a valid zero-byte bundle without filesystem access.
    bundle = AttachmentResolver().resolve(())
    record("empty bundle", bundle == AttachmentBundle())


def test_text_snapshot_and_manifest() -> None:
    # [Silent Failure] Content, ordering, hash, and body-free manifest must agree.
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        first = make_text(root, "first.md", "first body")
        second = make_text(root, "second.txt", "second body")
        bundle = AttachmentResolver().resolve((first, second))
    record(
        "text snapshot and manifest",
        tuple(item.name for item in bundle.items) == ("first.md", "second.txt")
        and bundle.items[0].content == "first body"
        and len(bundle.items[0].sha256) == 64
        and all("content" not in item for item in bundle.manifest()),
    )


def test_bom_and_image() -> None:
    # [Edge Case] UTF-8 BOM text decodes cleanly and image content stays native.
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        bom = root / "bom.md"
        bom.write_bytes(b"\xef\xbb\xbffile body")
        image = root / "diagram.png"
        image.write_bytes(b"PNG\x00bytes")
        bundle = AttachmentResolver().resolve((bom, image))
    record(
        "BOM and image classification",
        bundle.items[0].content == "file body"
        and bundle.items[1].kind is AttachmentKind.IMAGE
        and bundle.items[1].content is None,
    )


def test_path_failures() -> None:
    # [Hidden Failure] Missing, directory, empty, binary, and unreadable paths fail typed.
    resolver = AttachmentResolver()
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        missing = root / "missing.md"
        folder = root / "folder"
        folder.mkdir()
        empty = root / "empty.md"
        empty.write_bytes(b"")
        bom_only = root / "bom-only.md"
        bom_only.write_bytes(b"\xef\xbb\xbf")
        binary = root / "binary.dat"
        binary.write_bytes(b"\xff\xfe\x00\x01")
        expect_failure("missing path", AttachmentFileNotFound, lambda: resolver.resolve((missing,)))
        expect_failure("directory path", AttachmentDirectory, lambda: resolver.resolve((folder,)))
        expect_failure("empty file", AttachmentEmpty, lambda: resolver.resolve((empty,)))
        expect_failure("BOM-only file", AttachmentEmpty, lambda: resolver.resolve((bom_only,)))
        expect_failure(
            "unsupported binary", AttachmentUnsupported, lambda: resolver.resolve((binary,))
        )
        expect_failure(
            "unreadable read", AttachmentUnreadable, lambda: resolver._read_bytes(folder)
        )


def test_duplicate_and_input_shape() -> None:
    # [Hidden Assumption] Duplicate spellings and non-Click values cannot bypass validation.
    with tempfile.TemporaryDirectory() as directory:
        path = make_text(Path(directory), "one.md", "body")
        alternate = Path(directory) / "." / "one.md"
        expect_failure(
            "duplicate resolved path",
            AttachmentDuplicate,
            lambda: AttachmentResolver().resolve((path, alternate)),
        )
    expect_failure(
        "invalid resolver value",
        AttachmentInputInvalid,
        lambda: AttachmentResolver().resolve([Path("x")]),
    )


def test_limits() -> None:
    # [Edge Case] Exact per-file, file-count, and total limits pass; one over fails.
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        exact = root / "exact.txt"
        exact.write_bytes(b"x" * int(AttachmentLimit.MAX_FILE_BYTES))
        record("exact per-file limit", len(AttachmentResolver().resolve((exact,)).items) == 1)
        over = root / "over.txt"
        over.write_bytes(b"x" * (int(AttachmentLimit.MAX_FILE_BYTES) + 1))
        expect_failure(
            "per-file limit exceeded",
            AttachmentTooLarge,
            lambda: AttachmentResolver().resolve((over,)),
        )

        paths = tuple(
            make_text(root, f"file-{index}.txt", "x")
            for index in range(int(AttachmentLimit.MAX_FILES) + 1)
        )
        expect_failure(
            "file-count limit exceeded",
            AttachmentLimitExceeded,
            lambda: AttachmentResolver().resolve(paths),
        )

        total_paths = []
        for index in range(
            int(AttachmentLimit.MAX_TOTAL_BYTES) // int(AttachmentLimit.MAX_FILE_BYTES)
        ):
            path = root / f"total-{index}.txt"
            path.write_bytes(b"x" * int(AttachmentLimit.MAX_FILE_BYTES))
            total_paths.append(path)
        exact_bundle = AttachmentResolver().resolve(tuple(total_paths))
        record(
            "exact total limit", exact_bundle.total_bytes == int(AttachmentLimit.MAX_TOTAL_BYTES)
        )
        extra = root / "total-extra.txt"
        extra.write_bytes(b"x")
        expect_failure(
            "total limit exceeded",
            AttachmentLimitExceeded,
            lambda: AttachmentResolver().resolve(tuple(total_paths) + (extra,)),
        )


def test_click_option() -> None:
    # [Silent Failure] Click preserves repeated option order and help exposes the shared flag.
    @click.command()
    @AgentAttachmentOptions().apply
    def command(attachments: tuple[Path, ...]) -> None:
        click.echo("|".join(path.name for path in attachments))

    runner = CliRunner()
    help_result = runner.invoke(command, ["--help"])
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        first = make_text(root, "first.md", "one")
        second = make_text(root, "second.md", "two")
        result = runner.invoke(command, ["--attach", str(first), "--attach", str(second)])
    record(
        "Click option order and help",
        "--attach PATH" in help_result.output and result.output.strip() == "first.md|second.md",
    )


def install_fake_codex() -> None:
    # Installs the minimal SDK-shaped modules needed to test the lazy adapter boundary.
    @dataclass(frozen=True)
    class FakeText:
        text: str

    @dataclass(frozen=True)
    class FakeImage:
        path: str

    @dataclass(frozen=True)
    class FakeFile:
        path: str
        absolute_path: str
        size_bytes: int
        content: str | None
        language: str | None
        metadata: dict[str, str]

    @dataclass(frozen=True)
    class FakeRun:
        items: tuple[object, ...]
        context_items: tuple[object, ...]

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


def test_codex_adapter_snapshot() -> None:
    # [Hidden Failure] Codex mapping uses the resolved snapshot and native image input once.
    install_fake_codex()
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        text = make_text(root, "spec.md", "before mutation")
        image = root / "screen.png"
        image.write_bytes(b"image")
        bundle = AttachmentResolver().resolve((text, image))
        text.write_text("after mutation", encoding="utf-8")
        request = CodexAttachmentInputBuilder().build("do work", bundle)
    record(
        "Codex adapter preserves snapshot",
        len(request.items) == 2
        and len(request.context_items) == 1
        and request.context_items[0].content == "before mutation"
        and request.items[1].path.endswith("screen.png"),
    )


def test_models_reject_unknown_fields() -> None:
    # [Hidden Assumption] Strict models reject fields future callers did not declare.
    try:
        AttachmentBundle(extra_field="wrong")  # type: ignore[call-arg]
    except Exception:
        record("models reject unknown fields", True)
    else:
        record("models reject unknown fields", False, "accepted an extra field")


def main() -> int:
    # Runs every design-doc Section 10 case and reports a machine-readable tally.
    test_empty_bundle()
    test_text_snapshot_and_manifest()
    test_bom_and_image()
    test_path_failures()
    test_duplicate_and_input_shape()
    test_limits()
    test_click_option()
    test_codex_adapter_snapshot()
    test_models_reject_unknown_fields()
    passed = sum(1 for status, _, _ in RESULTS if status == PASS)
    print(f"{passed}/{len(RESULTS)} tests passed")
    return 0 if passed == len(RESULTS) else 1


if __name__ == "__main__":
    raise SystemExit(main())
