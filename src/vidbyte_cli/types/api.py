"""The transport envelope and generic API resources shared by every backend route.

This is *how* the CLI talks to the backend, independent of any one domain. Harness run
models live in types/harness.py (split per the types/api.ts:38 review comment) so this file
never grows a per-feature dependency. Keep field names in sync with the backend response
wrapper; the ApiClient unwraps `data` so callers only ever see the typed payload.
"""

from __future__ import annotations

from typing import Generic, TypeVar

from pydantic import BaseModel, ConfigDict, Field

T = TypeVar("T")


class ApiError(BaseModel):
    # Structured backend error; mapped to a CliError before it ever reaches the user.
    code: str
    title: str
    detail: str


class ApiPagination(BaseModel):
    limit: int
    page: int
    total: int | None = None


class ApiEnvelope(BaseModel, Generic[T]):
    # Standard response wrapper the ApiClient unwraps so callers see only `data`.
    success: bool
    message: str | None = None
    data: T | None = None
    error: ApiError | None = None
    pagination: ApiPagination | None = None


class KeyIdentity(BaseModel):
    """Non-secret identity behind a validated API key.

    `extra="ignore"` is the one deliberate departure from this repo's `extra="forbid"` default.
    The success body also carries a live, long-lived session token this CLI has no use for, and
    ignoring it keeps that token out of every modelled field, output document, and log line.
    The body's `email` is dropped for a different reason: the backend sets it to the user id,
    so presenting it as an email address would be a lie.

    `success` is modelled rather than ignored so a response that declares its own failure is a
    detectable protocol violation instead of a silent approval.
    """

    model_config = ConfigDict(extra="ignore", frozen=True)

    success: bool
    username: str = Field(min_length=1, max_length=256)
    account_tier: str = Field(min_length=1, max_length=64)
