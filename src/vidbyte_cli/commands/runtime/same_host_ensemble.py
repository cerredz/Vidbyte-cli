"""Command shell for the second local runtime primitive: a role-differentiated ensemble.

Reads roles from repeatable --role flags or a --roles-file, then reaches the same inert
executor boundary adversarial-team already has. It cannot request paid admission or spawn
agents in this release.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping
from pathlib import Path

import click
from pydantic import ValidationError

from ...lib.errors.failures import (
    EnsembleHostUnsupported,
    EnsembleRoleInvalid,
    EnsembleRolesFileInvalid,
    EnsembleRolesFileNotValidJson,
    EnsembleRolesFileUnreadable,
    EnsembleRoleSourceConflict,
)
from ...lib.runtime.context import ApplicationContext
from ...types.runtime import EnsembleRole, EnsembleRoster, RuntimeCapabilityId, RuntimeHost

CommandCallback = Callable[..., None]
OptionDecorator = Callable[[CommandCallback], CommandCallback]

_ENSEMBLE_HOSTS = (RuntimeHost.CODEX, RuntimeHost.CLAUDE)
_DEFAULT_ROLES: tuple[EnsembleRole, ...] = (
    EnsembleRole(
        name="correctness",
        system_prompt=(
            "Review the task for correctness risks. Propose an approach; do not implement it."
        ),
    ),
    EnsembleRole(
        name="simplification",
        system_prompt=(
            "Review the task for the simplest complete approach. Propose it; do not implement it."
        ),
    ),
    EnsembleRole(
        name="security",
        system_prompt=(
            "Review the task for security risks. Propose a safe approach; do not implement it."
        ),
    ),
)
_DEFAULT_IMPLEMENTER_PROMPT = (
    "You are the implementer. Use your team's proposals to do the real work."
)


class SameHostEnsembleCommand:
    """Builds a launch plan and role roster for the unimplemented ensemble executor."""

    def register(self, parent: click.Group) -> None:
        # Options are attached before the group takes the callback, so help lists them in order.
        def _run(context: ApplicationContext, /, **values: object) -> None:
            self.execute(context, values)

        callback = click.argument("task")(click.pass_obj(_run))
        parent.command(
            name="same-host-ensemble", help="Run a role-differentiated agent ensemble locally"
        )(self._apply(callback))

    def execute(self, context: ApplicationContext, values: Mapping[str, object]) -> None:
        # Validates the roster and plan first; the stub executor rejects before any side effect.
        roster = self._build_roster(values)
        task = str(values.get("task", ""))
        host = str(values.get("host") or "auto")
        requested = None if host == "auto" else RuntimeHost(host)
        plan = context.runtime_launch_planner().build(
            RuntimeCapabilityId.SAME_HOST_ENSEMBLE, task, requested, Path.cwd()
        )
        if plan.host not in _ENSEMBLE_HOSTS:
            raise EnsembleHostUnsupported(plan.host.value)
        context.runtime_executor().execute_ensemble(plan, roster)

    def _apply(self, callback: CommandCallback) -> CommandCallback:
        # Click decorators apply bottom-up, so this reverses them to match the help listing.
        for decorate in reversed(self._decorators()):
            callback = decorate(callback)
        return callback

    def _decorators(self) -> tuple[OptionDecorator, ...]:
        return (
            click.option(
                "--host",
                type=click.Choice(("auto", *(host.value for host in _ENSEMBLE_HOSTS))),
                default="auto",
                show_default=True,
                help="Native host to run on. Only hosts with verified fork/sandbox support.",
            ),
            click.option("--role", multiple=True, help="NAME:SYSTEM_PROMPT. Repeatable."),
            click.option(
                "--roles-file",
                type=click.Path(dir_okay=False),
                help="JSON array of {'name', 'system_prompt'} objects. Conflicts with --role.",
            ),
            click.option("--implementer-prompt", help="System prompt for the implementer role."),
            click.option("--model", help="Optional provider model override."),
            click.option("--reasoning-effort", help="Optional provider reasoning-effort override."),
        )

    def _build_roster(self, values: Mapping[str, object]) -> EnsembleRoster:
        # Resolves roles from exactly one source, then wraps the fixed remaining settings.
        role = values.get("role")
        roles_file = values.get("roles_file")
        role_flags = role if isinstance(role, tuple) else ()
        if role_flags and roles_file is not None:
            raise EnsembleRoleSourceConflict()
        if isinstance(roles_file, str):
            roles = self._read_roles_file(Path(roles_file))
        elif role_flags:
            roles = tuple(self._parse_role(str(entry)) for entry in role_flags)
        else:
            roles = _DEFAULT_ROLES
        names = [resolved.name for resolved in roles]
        if len(names) != len(set(names)):
            raise EnsembleRoleInvalid(f"duplicate name among {names}")
        return self._finish_roster(values, roles)

    def _finish_roster(
        self, values: Mapping[str, object], roles: tuple[EnsembleRole, ...]
    ) -> EnsembleRoster:
        # Isolated so a bound violation (role count) fails with an ensemble-specific message.
        implementer_prompt = values.get("implementer_prompt")
        model = values.get("model")
        reasoning_effort = values.get("reasoning_effort")
        try:
            return EnsembleRoster(
                roles=roles,
                implementer_prompt=str(implementer_prompt)
                if implementer_prompt
                else (_DEFAULT_IMPLEMENTER_PROMPT),
                model=str(model) if model else None,
                reasoning_effort=str(reasoning_effort) if reasoning_effort else None,
            )
        except ValidationError as error:
            raise EnsembleRoleInvalid(f"{len(roles)} roles is outside the 1-8 bound") from error

    def _parse_role(self, entry: str) -> EnsembleRole:
        # NAME:SYSTEM_PROMPT, split on the first colon only.
        name, separator, prompt = entry.partition(":")
        if not separator or not name.strip() or not prompt.strip():
            raise EnsembleRoleInvalid(f"'{entry}' is not NAME:SYSTEM_PROMPT")
        return EnsembleRole(name=name.strip(), system_prompt=prompt.strip())

    def _read_roles_file(self, path: Path) -> tuple[EnsembleRole, ...]:
        # UTF-8 is explicit so machine behavior does not depend on the host locale.
        try:
            with path.open("r", encoding="utf-8") as handle:
                raw = json.load(handle)
        except json.JSONDecodeError as error:
            raise EnsembleRolesFileNotValidJson(str(path), error) from error
        except (OSError, UnicodeDecodeError, ValueError) as error:
            raise EnsembleRolesFileUnreadable(str(path), error) from error
        try:
            return tuple(EnsembleRole.model_validate(item) for item in raw)
        except (ValidationError, TypeError) as error:
            raise EnsembleRolesFileInvalid(str(path), error) from error
