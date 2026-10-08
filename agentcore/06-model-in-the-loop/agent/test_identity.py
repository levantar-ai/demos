"""The exact AgentCore Identity calls behind orders_token, without AWS."""

import os

import identity

os.environ.update({"WORKLOAD_NAME": "demos_agentcore_06_agent",
                   "OBO_PROVIDER_NAME": "demos_agentcore_06_obo",
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
        ("wat", {"workloadName": "demos_agentcore_06_agent", "userToken": "inbound-jwt"}),
        ("obo", {"workloadIdentityToken": "wat-123",
                 "resourceCredentialProviderName": "demos_agentcore_06_obo",
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


def _token_endpoint_failure():
    from botocore.exceptions import ClientError
    return ClientError({"Error": {"Code": "ValidationException",
                                  "Message": "HTTP request failed against Token endpoint"}},
                       "GetResourceOauth2Token")


def test_a_transient_exchange_failure_is_retried_once_after_the_pause(monkeypatch):
    fake = FakeAgentCore()
    calls, slept = [], []

    def flaky(**kw):
        calls.append(kw)
        if len(calls) == 1:
            raise _token_endpoint_failure()
        return {"accessToken": "minted-789"}

    fake.get_resource_oauth2_token = flaky
    monkeypatch.setattr(identity, "_client", lambda: fake)
    monkeypatch.setattr(identity.time, "sleep", lambda s: slept.append(s))
    assert identity.orders_token("inbound-jwt") == "minted-789"
    assert len(calls) == 2 and calls[0] == calls[1]
    assert slept == [identity.RETRY_AFTER_SECONDS]


def test_a_second_transient_failure_is_raised_with_no_third_attempt(monkeypatch):
    import pytest
    from botocore.exceptions import ClientError

    fake = FakeAgentCore()
    calls = []

    def always(**kw):
        calls.append(kw)
        raise _token_endpoint_failure()

    fake.get_resource_oauth2_token = always
    monkeypatch.setattr(identity, "_client", lambda: fake)
    monkeypatch.setattr(identity.time, "sleep", lambda s: None)
    with pytest.raises(ClientError):
        identity.orders_token("inbound-jwt")
    assert len(calls) == 2


def test_a_validation_exception_about_something_else_is_not_retried(monkeypatch):
    import pytest
    from botocore.exceptions import ClientError

    fake = FakeAgentCore()
    calls = []

    def other(**kw):
        calls.append(kw)
        raise ClientError({"Error": {"Code": "ValidationException", "Message": "scopes invalid"}},
                          "GetResourceOauth2Token")

    fake.get_resource_oauth2_token = other
    monkeypatch.setattr(identity, "_client", lambda: fake)
    with pytest.raises(ClientError):
        identity.orders_token("inbound-jwt")
    assert len(calls) == 1


def test_other_exchange_errors_are_not_retried(monkeypatch):
    import pytest
    from botocore.exceptions import ClientError

    fake = FakeAgentCore()
    calls = []

    def denied(**kw):
        calls.append(kw)
        raise ClientError({"Error": {"Code": "AccessDeniedException", "Message": "no"}}, "GetResourceOauth2Token")

    fake.get_resource_oauth2_token = denied
    monkeypatch.setattr(identity, "_client", lambda: fake)
    with pytest.raises(ClientError):
        identity.orders_token("inbound-jwt")
    assert len(calls) == 1
