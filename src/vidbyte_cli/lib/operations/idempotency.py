"""FILE: src/vidbyte_cli/lib/operations/idempotency.py

PURPOSE: Creates or validates one stable idempotency key for a logical mutation.

ROLE IN CODEBASE: Generic harness and research services create the key once, journal it,
and pass the same value through every HTTP attempt.

TESTS: No feature tests are added under the approved no-tests workflow.
"""

from __future__ import annotations

import re
from uuid import uuid4

from ..errors import usage_error

_VALID_KEY = re.compile(r"^[A-Za-z0-9._:-]{8,128}$")


class IdempotencyKeyFactory:
    def create(self, explicit: str | None = None) -> str:
        if explicit is None:
            return str(uuid4())
        if not _VALID_KEY.fullmatch(explicit):
            raise usage_error(
                "The idempotency key must be 8-128 URL-safe characters.",
                "Use letters, numbers, period, underscore, colon, or hyphen.",
            )
        return explicit
