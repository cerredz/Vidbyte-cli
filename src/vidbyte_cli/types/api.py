"""The transport envelope and generic API resources shared by every backend route.

This is *how* the CLI talks to the backend, independent of any one domain. Harness run
models live in types/harness.py (split per the types/api.ts:38 review comment) so this file
never grows a per-feature dependency. Keep field names in sync with the backend response
wrapper; the ApiClient unwraps `data` so callers only ever see the typed payload.
"""

from __future__ import annotations

from typing import Generic, TypeVar

from pydantic import BaseModel

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


class WhoAmI(BaseModel):
    user_id: str
    email: str | None = None
