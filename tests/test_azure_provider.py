import pytest

from api import azure_provider


class _Credential:
    def get_token(self, _scope):
        return type("AccessToken", (), {"token": "test-access-token"})()

    def close(self):
        return None


class _Response:
    def raise_for_status(self):
        return None

    def json(self):
        return {
            "value": [
                {
                    "id": "/recommendation/1",
                    "kind": "SavingsPlan",
                    "properties": {
                        "term": "P1Y",
                        "lookBackPeriod": "Last30Days",
                        "currencyCode": "USD",
                        "costWithoutBenefit": 218.267,
                        "totalHours": 168,
                        "recommendationDetails": {
                            "averageUtilizationPercentage": 99.33,
                            "benefitCost": 52.002,
                            "commitmentAmount": 5.5,
                            "coveragePercentage": 54.609,
                            "overageCost": 144.841,
                            "savingsAmount": 21.424,
                            "savingsPercentage": 18.2,
                            "totalCost": 196.843,
                            "wastageCost": 0.035,
                            "customerData": "must not be forwarded",
                        },
                        "allRecommendationDetails": {
                            "value": [
                                {
                                    "commitmentAmount": 5.5,
                                    "savingsPercentage": 18.2,
                                    "customerData": "must not be forwarded",
                                }
                            ]
                        },
                        "customerData": "must not be forwarded",
                    },
                }
            ]
        }


class _EmptyResponse:
    def raise_for_status(self):
        return None

    def json(self):
        return {"value": []}


def test_connected_results_are_normalized_and_use_bearer_token(
    monkeypatch,
):
    monkeypatch.setenv("AZURE_AUTH_MODE", "developer")
    monkeypatch.setattr(
        azure_provider, "DefaultAzureCredential", lambda: _Credential()
    )
    captured = {}

    def fake_get(url, **kwargs):
        captured["url"] = url
        captured.update(kwargs)
        return _Response()

    monkeypatch.setattr(azure_provider.requests, "get", fake_get)
    result = azure_provider.get_benefit_recommendations(
        scope="/subscriptions/00000000-0000-0000-0000-000000000000",
        term="P1Y",
        lookback="Last30Days",
        recommendation_scope="Shared",
    )

    assert captured["headers"]["Authorization"] == "Bearer test-access-token"
    assert captured["params"]["$expand"] == "properties/allRecommendationDetails"
    assert result["recommendationCount"] == 1
    recommendation = result["recommendations"][0]
    assert recommendation["costWithoutBenefit"] == 218.267
    assert recommendation["recommendationDetails"] == {
        "averageUtilizationPercentage": 99.33,
        "benefitCost": 52.002,
        "commitmentAmount": 5.5,
        "coveragePercentage": 54.609,
        "overageCost": 144.841,
        "savingsAmount": 21.424,
        "savingsPercentage": 18.2,
        "totalCost": 196.843,
        "wastageCost": 0.035,
    }
    assert recommendation["alternatives"] == [
        {"commitmentAmount": 5.5, "savingsPercentage": 18.2}
    ]
    assert recommendation["kind"] == "SavingsPlan"
    assert "recommendationReference" in recommendation
    assert "id" not in recommendation
    assert "customerData" not in recommendation
    assert "customerData" not in recommendation["alternatives"][0]


def test_empty_azure_result_is_not_replaced_with_an_estimate(monkeypatch):
    monkeypatch.setenv("AZURE_AUTH_MODE", "developer")
    monkeypatch.setattr(
        azure_provider, "DefaultAzureCredential", lambda: _Credential()
    )
    monkeypatch.setattr(
        azure_provider.requests, "get", lambda *_args, **_kwargs: _EmptyResponse()
    )

    result = azure_provider.get_benefit_recommendations(
        scope="/subscriptions/00000000-0000-0000-0000-000000000000",
        term="P1Y",
        lookback="Last30Days",
        recommendation_scope="Shared",
    )

    assert result["recommendationCount"] == 0
    assert result["recommendations"] == []
    assert "no estimate was substituted" in result["notice"]


def test_connected_mode_exchanges_the_user_assertion_with_obo(
    monkeypatch,
):
    monkeypatch.setenv("AZURE_AUTH_MODE", "obo")
    monkeypatch.setenv("AZURE_TENANT_ID", "tenant-placeholder")
    monkeypatch.setenv("AZURE_CLIENT_ID", "client-placeholder")
    monkeypatch.setenv("AZURE_CLIENT_SECRET", "secret-placeholder")
    captured = {}

    class OnBehalfOfCredential:
        def __init__(self, **kwargs):
            captured["credential"] = kwargs

        def get_token(self, scope):
            captured["scope"] = scope
            return type("AccessToken", (), {"token": "arm-token"})()

        def close(self):
            captured["closed"] = True

    monkeypatch.setattr(
        azure_provider, "OnBehalfOfCredential", OnBehalfOfCredential
    )

    def fake_get(_url, **kwargs):
        captured["headers"] = kwargs["headers"]
        return _Response()

    monkeypatch.setattr(azure_provider.requests, "get", fake_get)
    azure_provider.get_benefit_recommendations(
        scope="/subscriptions/00000000-0000-0000-0000-000000000000",
        term="P1Y",
        lookback="Last30Days",
        recommendation_scope="Shared",
        authorization_header="Bearer user-assertion",
    )

    assert captured["credential"]["user_assertion"] == "user-assertion"
    assert captured["scope"] == azure_provider.MANAGEMENT_RESOURCE
    assert captured["headers"]["Authorization"] == "Bearer arm-token"
    assert captured["closed"] is True


@pytest.mark.parametrize(
    "scope",
    [
        "https://example.invalid/subscriptions/00000000-0000-0000-0000-000000000000",
        "/subscriptions/00000000-0000-0000-0000-000000000000?x=1",
        "/subscriptions/../billing",
        "/providers/Microsoft.Billing/billingAccounts/a' OR '1'='1",
    ],
)
def test_rejects_untrusted_scope_before_request(scope):
    with pytest.raises(ValueError, match="scope"):
        azure_provider.get_benefit_recommendations(
            scope,
            "P1Y",
            "Last30Days",
            recommendation_scope="Shared",
        )
