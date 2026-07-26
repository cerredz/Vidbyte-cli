"""FILE: src/vidbyte_cli/features/research/presentation/presenter.py

PURPOSE: Produces versioned research result documents, compact human views, coarse progress
transitions, and explicitly requested artifact files.

ROLE IN CODEBASE: Research commands pass service results here and then give the paired
document/text to OutputManager. ResearchWatcher uses ResearchProgressObserver.

ARCHITECTURE NOTE: Prompts are deliberately absent from every view. Large artifact payloads
do not enter terminals or pipes accidentally; an explicit path and overwrite flag are
required.

TESTS: No feature tests are added under the approved no-tests workflow. PR 6 smoke renders
the command tree while strict typing covers every presentation branch.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TypeVar, cast

from pydantic import BaseModel, JsonValue

from ....lib.config.atomic import AtomicFileWriter
from ....lib.errors import CliError, CliErrorCode, usage_error
from ....lib.output import OutputDocument, OutputManager
from ..application import ResearchMutationResult
from ..domain import (
    Page,
    ResearchArtifact,
    ResearchCapabilities,
    ResearchExport,
    ResearchRun,
    ResearchSource,
    ResearchThread,
)

_MAX_INLINE_ARTIFACT_BYTES = 50_000
_ModelItem = TypeVar("_ModelItem", bound=BaseModel)


@dataclass(frozen=True)
class PresentedResult:
    """One machine document paired with its human representation."""

    document: OutputDocument
    human: str


class ArtifactOutputWriter:
    """Atomic explicit-path writer with opt-in replacement."""

    def __init__(self, writer: AtomicFileWriter | None = None) -> None:
        self._writer = writer or AtomicFileWriter()

    def write(self, path: Path, content: bytes, *, force: bool) -> None:
        # @intent explicit-artifact-overwrite
        # Artifact exports can be large and valuable; replacement always needs --force.
        if path.exists() and not force:
            raise usage_error(
                f"Output path '{path}' already exists.",
                "Choose another path or pass --force to replace it.",
            )
        if path.is_dir():
            raise usage_error(f"Output path '{path}' is a directory.")
        try:
            self._writer.write(path, content)
        except CliError as error:
            raise CliError(
                CliErrorCode.OPERATION_FAILED,
                "The artifact output could not be written.",
                hint="Check the output path and available disk space, then retry.",
                cause=error,
            ) from error


class ResearchPresenter:
    """Pure research renderers plus the explicit large-artifact output boundary."""

    def __init__(self, artifact_writer: ArtifactOutputWriter | None = None) -> None:
        self._artifact_writer = artifact_writer or ArtifactOutputWriter()

    def mutation(self, result: ResearchMutationResult) -> PresentedResult:
        if result.run is not None:
            data = self._model_data(result.run)
            kind = "research.run"
            human = self._run_human(result.run)
        else:
            data = self._model_data(result.accepted)
            kind = "research.run.accepted"
            human = "\n".join(
                (
                    f"Run accepted: {result.accepted.run_id}",
                    f"Thread: {result.accepted.thread_id}",
                    f"Status: {result.accepted.status.value}",
                    f"Watch: vidbyte-cli research watch {result.accepted.run_id}",
                )
            )
        data["idempotency_key"] = result.idempotency_key
        return PresentedResult(OutputDocument(kind=kind, data=data), human)

    def run(self, value: ResearchRun) -> PresentedResult:
        return PresentedResult(
            OutputDocument(kind="research.run", data=self._model_data(value)),
            self._run_human(value),
        )

    def run_transition(self, value: ResearchRun) -> PresentedResult:
        return PresentedResult(
            OutputDocument(kind="research.run.transition", data=self._model_data(value)),
            (
                f"Research {value.status.value}: {value.discovered_sources} sources, "
                f"{value.generated_artifacts} artifacts"
            ),
        )

    def runs(self, value: Page[ResearchRun]) -> PresentedResult:
        lines = ["RUN ID  STATUS  SOURCES  ARTIFACTS"]
        lines.extend(
            f"{item.run_id}  {item.status.value}  "
            f"{item.discovered_sources}  {item.generated_artifacts}"
            for item in value.items
        )
        return self._page("research.runs", value, lines, "No research runs found.")

    def threads(self, value: Page[ResearchThread]) -> PresentedResult:
        lines = ["THREAD ID  RUNS  SOURCES  ARTIFACTS  TITLE"]
        lines.extend(
            f"{item.thread_id}  {item.run_count}  {item.source_count}  "
            f"{item.artifact_count}  {item.title or '-'}"
            for item in value.items
        )
        return self._page("research.threads", value, lines, "No research threads found.")

    def sources(self, value: Page[ResearchSource]) -> PresentedResult:
        lines = ["SOURCE ID  KIND  TITLE  URL"]
        lines.extend(
            f"{item.source_id}  "
            f"{item.resource_kind.value if item.resource_kind is not None else '-'}  "
            f"{item.title}  {item.url}"
            for item in value.items
        )
        return self._page("research.sources", value, lines, "No research sources found.")

    def artifacts(self, value: Page[ResearchArtifact]) -> PresentedResult:
        lines = ["ARTIFACT ID  FAVORITE  TITLE"]
        lines.extend(
            f"{item.artifact_id}  {'yes' if item.favorite else 'no'}  {item.title}"
            for item in value.items
        )
        return self._page("research.artifacts", value, lines, "No research artifacts found.")

    def artifact(
        self,
        value: ResearchArtifact,
        output_path: Path | None,
        *,
        force: bool,
    ) -> PresentedResult:
        encoded = value.model_dump_json(indent=2, exclude_none=True).encode("utf-8") + b"\n"
        if output_path is not None:
            self._artifact_writer.write(output_path, encoded, force=force)
            data: dict[str, JsonValue] = {
                "artifact_id": value.artifact_id,
                "path": str(output_path),
                "written": True,
            }
            return PresentedResult(
                OutputDocument(kind="research.artifact.written", data=data),
                f"Wrote artifact {value.artifact_id} to {output_path}",
            )
        if len(encoded) > _MAX_INLINE_ARTIFACT_BYTES:
            raise usage_error(
                "The artifact is too large for inline output.",
                "Pass --output PATH to write it explicitly.",
            )
        lines = [f"Artifact: {value.artifact_id}", f"Title: {value.title}"]
        if value.source_url is not None:
            lines.append(f"Source: {value.source_url}")
        if value.summary is not None:
            lines.extend(("Summary:", value.summary))
        if value.relevance is not None:
            lines.extend(("Relevance:", value.relevance))
        if value.recommendations:
            lines.append("Recommendations:")
            lines.extend(f"- {item}" for item in value.recommendations)
        return PresentedResult(
            OutputDocument(kind="research.artifact", data=self._model_data(value)),
            "\n".join(lines),
        )

    def capabilities(self, value: ResearchCapabilities) -> PresentedResult:
        kinds = ", ".join(item.value for item in value.resource_kinds) or "none"
        providers = ", ".join(value.export_providers) or "none"
        return PresentedResult(
            OutputDocument(kind="research.capabilities", data=self._model_data(value)),
            "\n".join((f"Resource kinds: {kinds}", f"Export providers: {providers}")),
        )

    def export(self, value: ResearchExport) -> PresentedResult:
        lines = [
            f"Export: {value.export_id}",
            f"Provider: {value.provider}",
            f"Scope: {value.scope.value}",
            f"Status: {value.status}",
        ]
        if value.destination_url is not None:
            lines.append(f"Destination: {value.destination_url}")
        return PresentedResult(
            OutputDocument(kind="research.export", data=self._model_data(value)),
            "\n".join(lines),
        )

    def _page(
        self,
        kind: str,
        value: Page[_ModelItem],
        lines: list[str],
        empty: str,
    ) -> PresentedResult:
        data: dict[str, JsonValue] = {
            "items": [self._model_data(item) for item in value.items],
            "next_cursor": value.next_cursor,
        }
        return PresentedResult(
            OutputDocument(kind=kind, data=data),
            "\n".join(lines) if value.items else empty,
        )

    def _run_human(self, value: ResearchRun) -> str:
        lines = [
            f"Run: {value.run_id}",
            f"Thread: {value.thread_id}",
            f"Status: {value.status.value}",
            f"Sources: {value.discovered_sources}",
            f"Artifacts: {value.generated_artifacts}",
        ]
        if value.requested_sources is not None:
            lines.append(f"Requested sources: {value.requested_sources}")
        if value.message is not None:
            lines.append(f"Message: {value.message}")
        return "\n".join(lines)

    def _model_data(self, value: BaseModel) -> dict[str, JsonValue]:
        return cast(
            dict[str, JsonValue],
            value.model_dump(mode="json", exclude_none=True),
        )


class ResearchProgressObserver:
    """Render deduplicated polling transitions through the shared output policy."""

    def __init__(
        self,
        output: OutputManager,
        presenter: ResearchPresenter | None = None,
    ) -> None:
        self._output = output
        self._presenter = presenter or ResearchPresenter()

    def transition(self, run: ResearchRun) -> None:
        presented = self._presenter.run_transition(run)
        self._output.transition(presented.document, presented.human)
