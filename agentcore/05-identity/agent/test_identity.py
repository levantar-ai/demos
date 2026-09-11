"""The exact AgentCore Identity calls behind orders_token, without AWS."""

import os

import identity

os.environ.update({"WORKLOAD_NAME": "demos_agentcore_05_agent",
                   "OBO_PROVIDER_NAME": "demos_agentcore_05_obo",
                   "ORDERS_SCOPE": "orders/read"})


class FakeAgentCore:
    def __init__(self):
        self.calls = []

    def get_workload_access_token_for_jwt(self, **kw):
        self.calls.append(("wat", kw))
        return {"workloadAccessToken": "wat-123"}

    def get_resource_oauth2_token(self, **kw):
        self.calls.append(("obo", kw))
        return {"accessToken": "minted-456"}


def test_orders_token_drives_the_on_behalf_of_chain(monkeypatch):
    fake = FakeAgentCore()
    monkeypatch.setattr(identity, "_client", lambda: fake)
    assert identity.orders_token("inbound-jwt") == "minted-456"
    assert fake.calls == [
        ("wat", {"workloadName": "demos_agentcore_05_agent", "userToken": "inbound-jwt"}),
        ("obo", {"workloadIdentityToken": "wat-123",
                 "resourceCredentialProviderName": "demos_agentcore_05_obo",
                 "scopes": ["orders/read"],
                 "oauth2Flow": "ON_BEHALF_OF_TOKEN_EXCHANGE"}),
    ]


def test_orders_token_fails_closed_without_a_token(monkeypatch):
    fake = FakeAgentCore()
    fake.get_resource_oauth2_token = lambda **kw: {"sessionStatus": "FAILED"}
    monkeypatch.setattr(identity, "_client", lambda: fake)
    import pytest
    with pytest.raises(RuntimeError):
        identity.orders_token("inbound-jwt")
