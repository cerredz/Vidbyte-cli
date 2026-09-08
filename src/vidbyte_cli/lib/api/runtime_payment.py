"""Explicit, bounded x402 authorization for one runtime admission.

The API client owns HTTP and retries. This object validates the challenge and signs
once; it never funds a wallet, launches an agent, or logs payment credentials.
"""

from collections.abc import Mapping
from urllib.parse import urlsplit

import httpx
from eth_account import Account
from eth_utils.address import is_address
from x402 import x402ClientSync
from x402.http import x402HTTPClientSync
from x402.mechanisms.evm.constants import NETWORK_CONFIGS
from x402.mechanisms.evm.exact import register_exact_evm_client
from x402.schemas import PaymentRequired, PaymentRequirements

from ..constants.runtime import RuntimePaymentConfig as Config
from ..errors.failures import RuntimePaymentFailed


class RuntimePayment:
    """Invocation-owned signer with an exact price and allowed network."""

    def __init__(self, environment: Mapping[str, str], cents: int) -> None:
        # Validate opt-in credentials before sending the admission request.
        self._network = environment.get(Config.NETWORK_ENV, Config.DEFAULT_NETWORK)
        self._cents = cents
        self._signed = False
        if self._network not in Config.NETWORKS or cents <= 0:
            raise RuntimePaymentFailed("configuration_invalid")
        try:
            signer = Account.from_key(environment.get(Config.PRIVATE_KEY_ENV, ""))
            client = register_exact_evm_client(x402ClientSync(), signer, self._network)
            self._http = x402HTTPClientSync(client)
        except Exception as error:
            raise RuntimePaymentFailed("signer_unavailable") from error

    def headers(self, response: httpx.Response) -> dict[str, str]:
        # Never create another authorization after a paid attempt fails or times out.
        if self._signed:
            raise RuntimePaymentFailed("authorization_already_created")
        header = response.headers.get("PAYMENT-REQUIRED", "")
        if not header or len(header) > Config.MAX_CHALLENGE_CHARACTERS:
            raise RuntimePaymentFailed("challenge_missing_or_oversized")
        try:
            required = self._http.get_payment_required_response(response.headers.get)
            self._validate(required, str(response.request.url))
            self._signed = True
            payload = self._http.create_payment_payload(required)
            return self._http.encode_payment_signature_header(payload)
        except RuntimePaymentFailed:
            raise
        except Exception as error:
            raise RuntimePaymentFailed("challenge_or_signing_failed") from error

    def _validate(self, required: object, url: str) -> None:
        # Bind the authorization to the requested origin/resource and one reviewed exact price.
        if not isinstance(required, PaymentRequired) or required.x402_version != 2:
            raise RuntimePaymentFailed("protocol_invalid")
        if required.resource is None or len(required.accepts) != 1:
            raise RuntimePaymentFailed("resource_or_options_invalid")
        resource, requested = urlsplit(required.resource.url), urlsplit(url)
        if resource.scheme or resource.netloc:
            matches = resource == requested
        else:
            matches = (
                resource.path == requested.path and not resource.query and not resource.fragment
            )
        if not matches:
            raise RuntimePaymentFailed("resource_mismatch")
        self._validate_requirement(required.accepts[0])

    def _validate_requirement(self, item: PaymentRequirements) -> None:
        # Canonical six-decimal USDC and EIP-712 metadata prevent arbitrary-token authorization.
        asset = NETWORK_CONFIGS[self._network]["default_asset"]
        expected = str(self._cents * Config.MICROUNITS_PER_CENT)
        if item.network != self._network or item.scheme != "exact" or item.amount != expected:
            raise RuntimePaymentFailed("price_or_network_mismatch")
        if item.asset.lower() != asset["address"].lower():
            raise RuntimePaymentFailed("asset_mismatch")
        extra = item.extra or {}
        if extra.get("name") != asset["name"] or extra.get("version") != asset["version"]:
            raise RuntimePaymentFailed("token_domain_mismatch")
        if not is_address(item.pay_to) or int(item.pay_to, 16) == 0:
            raise RuntimePaymentFailed("recipient_invalid")
        if not 0 < item.max_timeout_seconds <= Config.MAX_AUTHORIZATION_SECONDS:
            raise RuntimePaymentFailed("authorization_duration_invalid")
