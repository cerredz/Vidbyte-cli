"""The transport envelope and the identity behind a validated API key.

This is *how* the CLI talks to the backend, independent of any one domain — a product's own
wire shapes belong beside that product, the way types/research.py owns the research surface.
Keep the envelope field names in sync with the backend response wrapper; the ApiClient
unwraps `data` so callers only ever see the typed payload.
"""

from __future__ import annotations

from typing import Generic, Literal, TypeVar

from pydantic import BaseModel, ConfigDict, Field

T = TypeVar("T")


class ApiError(BaseModel):
    # Structured backend error; mapped to a CliError before it ever reaches the user.
    code: str
    title: str
    detail: str


class ApiUsageRemediation(BaseModel):
    """Safe, bounded instructions for restoring a Vidbyte API balance."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    action: Literal["top_up_api_balance"]
    requires_user_approval: bool
    topup_method: Literal["POST"]
    topup_path: str = Field(min_length=1, max_length=128, pattern=r"^/[A-Za-z0-9_./{}-]+$")
    cli_command: Literal["vidbyte-cli billing top-up --confirm"]
    minimum_topup_cents: int = Field(ge=1, le=1_000_000)
    supported_payment_methods: tuple[Literal["x402", "mpp"], ...] = Field(
        min_length=1, max_length=4
    )
    browser_url: str = Field(min_length=1, max_length=512, pattern=r"^https://")
    retry_original_operation: bool
    steps: tuple[str, ...] = Field(min_length=1, max_length=20)


class ApiUsageExhaustedProblem(BaseModel):
    """The backend's allowlisted HTTP 402 account-balance problem."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    error: Literal[True]
    title: str = Field(min_length=1, max_length=256)
    subtitle: str = Field(min_length=1, max_length=512)
    description: str = Field(min_length=1, max_length=8192)
    code: Literal["api_usage_exhausted", "usage_credit_exhausted"]
    incident_id: str = Field(min_length=1, max_length=64)
    remediation: ApiUsageRemediation


class BillingTopUpResult(BaseModel):
    """The safe success fields returned after an API-balance top-up."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    credited_cents: int = Field(ge=1)
    rail: str = Field(min_length=1, max_length=32)
    payment_ref: str | None = Field(default=None, max_length=256)
    available_balance_cents: int = Field(ge=0)


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
