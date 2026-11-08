"""How the newsroom scan authenticates to the Claude API.

In the `scan` workflow the scan signs in by workload identity federation: the
job's GitHub OIDC token is exchanged for a short-lived Anthropic access token
under a federation rule that names this repository's `scan` environment, so no
static key is needed. Each exchange asks GitHub for a fresh OIDC token, since
GitHub's tokens expire in minutes and Anthropic accepts each one only once,
while a scan can run for most of an hour.

The federation identifiers arrive as environment variables. They are
identifiers, not credentials. With no rule named, the client falls back to the
SDK's own resolution, which reads an API key from the environment: that is a
local run, and the workflow while its environment still holds the key.
"""

from __future__ import annotations

import json
import os
import time
import urllib.parse
import urllib.request
from collections.abc import Mapping
from typing import TYPE_CHECKING

from anthropic import Anthropic
from anthropic.lib.credentials import WorkloadIdentityCredentials

if TYPE_CHECKING:
    import httpx2

OIDC_AUDIENCE = "https://api.anthropic.com"
RULE_ENV = "ANTHROPIC_FEDERATION_RULE_ID"
ORGANIZATION_ENV = "ANTHROPIC_ORGANIZATION_ID"
SERVICE_ACCOUNT_ENV = "ANTHROPIC_SERVICE_ACCOUNT_ID"
WORKSPACE_ENV = "ANTHROPIC_WORKSPACE_ID"
REQUEST_URL_ENV = "ACTIONS_ID_TOKEN_REQUEST_URL"
REQUEST_TOKEN_ENV = "ACTIONS_ID_TOKEN_REQUEST_TOKEN"
OIDC_TIMEOUT_S = 30
OIDC_ATTEMPTS = 3


class FederationConfigError(RuntimeError):
    """A federation rule is named but the run cannot complete the exchange."""


def _env(environ: Mapping[str, str], name: str) -> str:
    return environ.get(name, "").strip()


def oidc_request_url(request_url: str, audience: str = OIDC_AUDIENCE) -> str:
    """The Actions token endpoint, asked for a token with the given audience."""
    separator = "&" if "?" in request_url else "?"
    return f"{request_url}{separator}audience={urllib.parse.quote(audience, safe='')}"


def github_identity_token(environ: Mapping[str, str] | None = None) -> str:
    """A fresh GitHub Actions OIDC token for the Claude API's audience."""
    env = os.environ if environ is None else environ
    url, bearer = _env(env, REQUEST_URL_ENV), _env(env, REQUEST_TOKEN_ENV)
    if not url or not bearer:
        raise FederationConfigError(
            "a federation rule is named, but this job cannot request a GitHub OIDC "
            "token: the job needs `id-token: write`"
        )
    request = urllib.request.Request(
        oidc_request_url(url), headers={"Authorization": f"Bearer {bearer}"}
    )
    for attempt in range(OIDC_ATTEMPTS):
        try:
            with urllib.request.urlopen(request, timeout=OIDC_TIMEOUT_S) as response:
                value = json.load(response).get("value")
            break
        except OSError:
            if attempt == OIDC_ATTEMPTS - 1:
                raise
            time.sleep(2**attempt)
    if not isinstance(value, str) or not value:
        raise FederationConfigError("the GitHub OIDC endpoint returned no token")
    return value


def federation_credentials(
    environ: Mapping[str, str] | None = None,
    http_client: httpx2.Client | None = None,
) -> WorkloadIdentityCredentials | None:
    """The federated credential the environment names, or None for none.

    ``http_client`` carries the token exchange; the SDK's own by default.
    """
    env = os.environ if environ is None else environ
    rule = _env(env, RULE_ENV)
    if not rule:
        return None
    organization = _env(env, ORGANIZATION_ENV)
    if not organization:
        raise FederationConfigError(f"{RULE_ENV} is set without {ORGANIZATION_ENV}")
    return WorkloadIdentityCredentials(
        identity_token_provider=lambda: github_identity_token(env),
        federation_rule_id=rule,
        organization_id=organization,
        service_account_id=_env(env, SERVICE_ACCOUNT_ENV) or None,
        workspace_id=_env(env, WORKSPACE_ENV) or None,
        http_client=http_client,
    )


def client(environ: Mapping[str, str] | None = None) -> Anthropic:
    """The Claude API client the scan calls through."""
    credentials = federation_credentials(environ)
    if credentials is None:
        return Anthropic()
    return Anthropic(credentials=credentials)
