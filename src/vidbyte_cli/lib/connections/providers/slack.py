"""Slack PKCE adapter and bounded channel-history reads.

The local flow requests user scopes from a PKCE-enabled public Slack app. Bot installations and
hosted OAuth relays are intentionally outside this first local connection implementation.
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import TYPE_CHECKING
from urllib.parse import urlencode

from pydantic import SecretStr, ValidationError

from ....types.connection import (
    ConnectionIdentity,
    ConnectionProvider,
    ConnectionRead,
    ConnectionResource,
    ConnectionToken,
)
from ...errors.failures import (
    ConnectionAuthenticationRequired,
    ConnectionConfigurationInvalid,
    ConnectionOAuthFailed,
    ConnectionProtocolError,
    ConnectionReauthenticationRequired,
    ConnectionResourceUnavailable,
    ConnectionScopeInsufficient,
)
from ..oauth import OAuthBrowser, OAuthCallbackServer, PkceChallenge
from .base import AuthenticatedConnection, ProviderAdapterBase

if TYPE_CHECKING:
    from ...runtime.context import ApplicationContext

_SLACK_PROVIDER = "slack"
_SLACK_AUTHORIZE_URL = "https://slack.com/oauth/v2/authorize"
_SLACK_TOKEN_URL = "https://slack.com/api/oauth.v2.access"
_SLACK_AUTH_TEST_URL = "https://slack.com/api/auth.test"
_SLACK_HISTORY_URL = "https://slack.com/api/conversations.history"
_SLACK_REVOKE_URL = "https://slack.com/api/auth.revoke"
_DEFAULT_SCOPES = (
    "channels:read",
    "channels:history",
    "groups:read",
    "groups:history",
    "im:read",
    "im:history",
    "mpim:read",
    "mpim:history",
    "users:read",
    "team:read",
)


class SlackConnectionAdapter(ProviderAdapterBase):
    """Authenticates a Slack workspace with PKCE and reads channel history."""

    provider = ConnectionProvider.SLACK

    def login(self, context: ApplicationContext, scopes: tuple[str, ...], client_secrets_path: Path | None = None) -> AuthenticatedConnection:  # fmt: skip  # noqa: E501
        # Runs Slack user-scope PKCE authorization and verifies workspace identity.
        del client_secrets_path
        client_id = context.environment.get("VIDBYTE_SLACK_CLIENT_ID", "").strip()
        if not client_id:
            raise ConnectionConfigurationInvalid(_SLACK_PROVIDER)
        requested_scopes = scopes or _DEFAULT_SCOPES
        flow = PkceChallenge.generate()
        with OAuthCallbackServer(_SLACK_PROVIDER, redirect_host="localhost") as callback:
            query = {
                "client_id": client_id,
                "redirect_uri": callback.redirect_uri,
                "user_scope": ",".join(requested_scopes),
                "state": flow.state,
                "code_challenge": flow.challenge,
                "code_challenge_method": "S256",
            }
            authorization_url = f"{_SLACK_AUTHORIZE_URL}?{urlencode(query)}"
            OAuthBrowser().open(authorization_url, context.streams)
            callback_query = callback.wait(context.options.request_timeout_seconds)
        self._validate_callback(callback_query, flow.state)
        code = callback_query.get("code")
        if not code:
            raise ConnectionOAuthFailed(_SLACK_PROVIDER)
        payload = self._client(context, _SLACK_PROVIDER).post_form(
            _SLACK_TOKEN_URL,
            {
                "client_id": client_id,
                "code": code,
                "redirect_uri": callback.redirect_uri,
                "code_verifier": flow.verifier,
            },
        )
        self._require_ok(payload)
        token = self._token_from_payload(payload, requested_scopes)
        return AuthenticatedConnection(token=token, identity=self.verify(context, token))

    def verify(self, context: ApplicationContext, token: ConnectionToken) -> ConnectionIdentity:
        # Calls auth.test and returns only Slack user and workspace identifiers.
        payload = self._client(context, _SLACK_PROVIDER).post_form(
            _SLACK_AUTH_TEST_URL,
            {},
            self._headers(token),
        )
        self._require_ok(payload)
        user_id = self._text(payload, "user_id", _SLACK_PROVIDER)
        team_id = self._text(payload, "team_id", _SLACK_PROVIDER)
        return ConnectionIdentity(
            provider=self.provider,
            account_id=user_id,
            account_label=self._optional_text(payload, "user"),
            workspace_id=team_id,
            workspace_label=self._optional_text(payload, "team"),
            scopes=self._scopes(token.provider_data.get("scopes")),
        )

    def refresh(self, context: ApplicationContext, token: ConnectionToken) -> ConnectionToken:
        # Rotates a Slack user token with its refresh token and client ID.
        refresh_token = token.refresh_secret()
        if refresh_token is None:
            raise ConnectionReauthenticationRequired(_SLACK_PROVIDER)
        client_id = context.environment.get("VIDBYTE_SLACK_CLIENT_ID", "").strip()
        if not client_id:
            raise ConnectionConfigurationInvalid(_SLACK_PROVIDER)
        payload = self._client(context, _SLACK_PROVIDER).post_form(
            _SLACK_TOKEN_URL,
            {
                "client_id": client_id,
                "grant_type": "refresh_token",
                "refresh_token": refresh_token,
            },
        )
        self._require_ok(payload)
        return self._token_from_payload(
            payload,
            self._scopes(payload.get("scope")) or self._scopes(token.provider_data.get("scopes")),
            old_refresh=refresh_token,
        )

    def read(self, context: ApplicationContext, token: ConnectionToken, resource: ConnectionResource) -> ConnectionRead:  # fmt: skip  # noqa: E501
        # Reads a bounded first page of history for one Slack channel ID.
        self._resource_for(resource, self.provider)
        if resource.resource_type != "channel":
            raise ConnectionResourceUnavailable(_SLACK_PROVIDER)
        channel_id = self._channel_id(resource.identifier)
        payload = self._client(context, _SLACK_PROVIDER).get_json(
            _SLACK_HISTORY_URL,
            self._headers(token),
            {"channel": channel_id, "limit": str(resource.limit)},
        )
        self._require_ok(payload)
        return ConnectionRead(
            provider=self.provider,
            resource_type=resource.resource_type,
            identifier=channel_id,
            data=self._json_data(payload, _SLACK_PROVIDER),
        )

    def revoke(self, context: ApplicationContext, token: ConnectionToken) -> None:
        # Revokes the user token through Slack's auth.revoke endpoint.
        payload = self._client(context, _SLACK_PROVIDER).post_form(
            _SLACK_REVOKE_URL,
            {"token": token.access_secret()},
        )
        self._require_ok(payload)

    def _validate_callback(self, query: dict[str, str], expected_state: str) -> None:
        # Checks state and provider denial before any token exchange.
        if query.get("state") != expected_state:
            from ...errors.failures import ConnectionOAuthStateInvalid

            raise ConnectionOAuthStateInvalid(_SLACK_PROVIDER)
        if query.get("error"):
            raise ConnectionOAuthFailed(_SLACK_PROVIDER)

    def _require_ok(self, payload: dict[str, object]) -> None:
        # Converts Slack's HTTP-200 error envelope into a typed CLI failure.
        if payload.get("ok") is not True:
            error = payload.get("error")
            if error == "missing_scope":
                raise ConnectionScopeInsufficient(_SLACK_PROVIDER)
            if error in {"invalid_auth", "token_revoked", "account_inactive"}:
                raise ConnectionAuthenticationRequired(_SLACK_PROVIDER)
            if error in {"channel_not_found", "not_in_channel", "is_archived"}:
                raise ConnectionResourceUnavailable(_SLACK_PROVIDER)
            raise ConnectionOAuthFailed(_SLACK_PROVIDER)

    def _token_from_payload(self, payload: dict[str, object], scopes: tuple[str, ...], old_refresh: str | None = None) -> ConnectionToken:  # fmt: skip  # noqa: E501
        # Extracts the user token and preserves a refresh token during rotation.
        user = payload.get("authed_user")
        if not isinstance(user, dict):
            raise ConnectionProtocolError(_SLACK_PROVIDER, ValueError("missing authed_user"))
        access_token = user.get("access_token")
        if not isinstance(access_token, str) or not access_token:
            raise ConnectionProtocolError(_SLACK_PROVIDER, ValueError("missing user token"))
        refresh_token = user.get("refresh_token")
        if not isinstance(refresh_token, str) or not refresh_token:
            refresh_token = old_refresh
        expires_in = user.get("expires_in")
        if not isinstance(expires_in, int) or isinstance(expires_in, bool) or expires_in < 0:
            expires_in = None
        granted = self._scopes(user.get("scope")) or self._scopes(payload.get("scope")) or scopes
        try:
            return ConnectionToken(
                access_token=SecretStr(access_token),
                refresh_token=SecretStr(refresh_token) if refresh_token is not None else None,
                token_type=self._optional_text(user, "token_type") or "Bearer",
                expires_at=int(time.time()) + expires_in if expires_in is not None else None,
                provider_data={"scopes": " ".join(granted)},
            )
        except ValidationError as error:
            raise ConnectionProtocolError(_SLACK_PROVIDER, error) from error

    def _channel_id(self, value: str) -> str:
        # Accepts Slack channel IDs and rejects arbitrary URL/path input.
        if not value or len(value) > 32 or value[0] not in "CDG":
            raise ConnectionProtocolError(_SLACK_PROVIDER, ValueError("invalid channel id"))
        if not value[1:].isalnum():
            raise ConnectionProtocolError(_SLACK_PROVIDER, ValueError("invalid channel id"))
        return value
