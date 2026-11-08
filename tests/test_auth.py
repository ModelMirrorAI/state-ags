"""The scan's Claude API sign-in: federation when a rule is named, else the key."""

from __future__ import annotations

import io
import json
import urllib.request
from typing import Any

import httpx2
import pytest
from anthropic import Anthropic

from stateags import auth

FEDERATED = {
    auth.RULE_ENV: "fdrl_test",
    auth.ORGANIZATION_ENV: "00000000-0000-0000-0000-000000000000",
    auth.SERVICE_ACCOUNT_ENV: "svac_test",
    auth.WORKSPACE_ENV: "wrkspc_test",
    auth.REQUEST_URL_ENV: "https://oidc.example/token?api-version=2.0",
    auth.REQUEST_TOKEN_ENV: "request-bearer",
}


class FakeOidc:
    """The Actions token endpoint: a new token on every request."""

    def __init__(self) -> None:
        self.requests: list[urllib.request.Request] = []

    def __call__(self, request: urllib.request.Request, timeout: float) -> io.BytesIO:
        self.requests.append(request)
        return io.BytesIO(json.dumps({"value": f"jwt-{len(self.requests)}"}).encode())


@pytest.fixture
def oidc(monkeypatch: pytest.MonkeyPatch) -> FakeOidc:
    fake = FakeOidc()
    monkeypatch.setattr(urllib.request, "urlopen", fake)
    return fake


def test_no_rule_means_no_federation() -> None:
    assert auth.federation_credentials({}) is None
    assert auth.federation_credentials({auth.RULE_ENV: "  "}) is None


def test_no_rule_falls_back_to_the_environment_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(auth.RULE_ENV, raising=False)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    assert auth.client({}).api_key == "sk-ant-test"


def test_a_rule_without_its_organization_is_refused() -> None:
    with pytest.raises(auth.FederationConfigError, match=auth.ORGANIZATION_ENV):
        auth.federation_credentials({auth.RULE_ENV: "fdrl_test"})


def test_a_job_without_id_token_write_is_refused(oidc: FakeOidc) -> None:
    env = {k: v for k, v in FEDERATED.items() if k != auth.REQUEST_TOKEN_ENV}
    with pytest.raises(auth.FederationConfigError, match="id-token: write"):
        auth.github_identity_token(env)
    assert oidc.requests == []


def test_the_oidc_request_names_the_claude_audience(oidc: FakeOidc) -> None:
    assert auth.github_identity_token(FEDERATED) == "jwt-1"
    (request,) = oidc.requests
    assert request.full_url == (
        "https://oidc.example/token?api-version=2.0&audience=https%3A%2F%2Fapi.anthropic.com"
    )
    assert request.get_header("Authorization") == "Bearer request-bearer"
    assert (
        auth.oidc_request_url("https://x/t")
        == "https://x/t?audience=https%3A%2F%2Fapi.anthropic.com"
    )


def test_each_exchange_asks_github_for_a_fresh_token(oidc: FakeOidc) -> None:
    """GitHub's tokens expire in minutes and each is accepted once."""
    exchanges: list[dict[str, Any]] = []
    messages: list[httpx2.Request] = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        if request.url.path == "/v1/oauth/token":
            exchanges.append(json.loads(request.content))
            n = len(exchanges)
            return httpx2.Response(
                200,
                json={
                    "access_token": f"sk-ant-oat01-{n}",
                    "token_type": "Bearer",
                    "expires_in": 600,
                },
            )
        messages.append(request)
        return httpx2.Response(
            200,
            json={
                "id": "msg_1",
                "type": "message",
                "role": "assistant",
                "model": "claude-test",
                "content": [{"type": "text", "text": "ok"}],
                "stop_reason": "end_turn",
                "stop_sequence": None,
                "usage": {"input_tokens": 1, "output_tokens": 1},
            },
        )

    transport = httpx2.MockTransport(handler)
    credentials = auth.federation_credentials(
        FEDERATED, http_client=httpx2.Client(transport=transport)
    )
    assert credentials is not None
    first, second = credentials(), credentials()
    assert [first.token, second.token] == ["sk-ant-oat01-1", "sk-ant-oat01-2"]
    assert [e["assertion"] for e in exchanges] == ["jwt-1", "jwt-2"]
    assert exchanges[0] == {
        "grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer",
        "assertion": "jwt-1",
        "federation_rule_id": "fdrl_test",
        "organization_id": "00000000-0000-0000-0000-000000000000",
        "service_account_id": "svac_test",
        "workspace_id": "wrkspc_test",
    }

    # Through the client the scan uses, the minted token is the bearer.
    credentials = auth.federation_credentials(
        FEDERATED, http_client=httpx2.Client(transport=transport)
    )
    client = Anthropic(credentials=credentials, http_client=httpx2.Client(transport=transport))
    client.messages.create(
        model="claude-test", max_tokens=1, messages=[{"role": "user", "content": "hi"}]
    )
    (sent,) = messages
    assert sent.headers["authorization"] == "Bearer sk-ant-oat01-3"
    assert "x-api-key" not in sent.headers


def test_a_transient_oidc_failure_is_retried(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[int] = []

    def flaky(request: urllib.request.Request, timeout: float) -> io.BytesIO:
        calls.append(1)
        if len(calls) == 1:
            raise OSError("connection reset")
        return io.BytesIO(json.dumps({"value": "jwt-ok"}).encode())

    monkeypatch.setattr(urllib.request, "urlopen", flaky)
    monkeypatch.setattr("stateags.auth.time.sleep", lambda s: None)
    assert auth.github_identity_token(FEDERATED) == "jwt-ok"
    assert len(calls) == 2
