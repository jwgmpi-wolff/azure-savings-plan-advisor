import pytest

from api.calculator import calculate_comparison, calculate_forecast
from api.models import ForecastRequest, validate_request


def _request(
    costs,
    *,
    discount=20,
    commitment=None,
    scenario=None,
    change=0,
    term="P1Y",
):
    return ForecastRequest(
        mode="what-if",
        term=term,
        lookback_period="Last30Days",
        hourly_commitment=commitment,
        baseline_hourly_costs=costs,
        expected_change_percent=change,
        discount_percent=discount,
        scope=None,
        scenario=scenario or ("custom" if commitment is not None else "balanced"),
        currency_code="USD",
    )


def test_balanced_forecast_is_deterministic():
    request = _request([10, 12, 8, 14] * 180)
    result = calculate_forecast(request)

    assert result["dataHours"] == 720
    assert result["hourlyCommitment"] == 8.8
    assert result["confidence"] == "High"
    assert result["scenario"] == "balanced"
    assert "projectedTermNetSavings" in result
    assert result["modeledCostObserved"] == 7056


def test_zero_usage_does_not_create_savings_or_commitment():
    result = calculate_forecast(_request([0] * 24))

    assert result["baselineEligibleCostObserved"] == 0
    assert result["hourlyCommitment"] == 0
    assert result["netSavingsObserved"] == 0
    assert result["coveragePercent"] == 0
    assert result["confidence"] == "Low"
    assert any("no savings are modeled" in warning for warning in result["warnings"])


def test_volatile_usage_adds_a_warning():
    result = calculate_forecast(_request([0, 100] * 100))

    assert result["confidence"] == "Low"
    assert any("highly variable" in warning for warning in result["warnings"])


def test_falling_usage_is_applied_and_disclosed():
    result = calculate_forecast(_request([10] * 48, change=-20))

    assert result["baselineEligibleCostObserved"] == 480
    assert result["scenarioEligibleCostObserved"] == 384
    assert any("usage reduction" in warning for warning in result["warnings"])


def test_explicit_custom_commitment_models_overage_and_unused_amounts():
    result = calculate_forecast(_request([20, 0], commitment=8))

    assert result["hourlyPaygCoverageCapacity"] == 10
    assert result["commitmentCostObserved"] == 16
    assert result["overageCostObserved"] == 10
    assert result["unusedCommitmentCostObserved"] == 8
    assert result["netSavingsObserved"] == -6


@pytest.mark.parametrize(
    ("costs", "discount", "change", "commitment"),
    [
        ([-1], 20, 0, None),
        ([float("inf")], 20, 0, None),
        ([1], 100, 0, None),
        ([1], 20, -101, None),
        ([1], 20, 0, -1),
    ],
)
def test_invalid_calculation_inputs_are_rejected(
    costs, discount, change, commitment
):
    with pytest.raises(ValueError):
        calculate_forecast(
            _request(
                costs,
                discount=discount,
                change=change,
                commitment=commitment,
            )
        )


def test_custom_scenario_requires_an_explicit_commitment():
    with pytest.raises(ValueError, match="hourlyCommitment"):
        calculate_forecast(
            _request([1], scenario="custom", commitment=None)
        )


def test_comparison_contains_no_commitment_and_both_terms():
    result = calculate_comparison(
        {
            "baselineHourlyCosts": [10] * 24,
            "currencyCode": "USD",
            "discountPercentP1Y": 15,
            "discountPercentP3Y": 25,
            "expectedChangePercent": 0,
        }
    )

    assert [option["term"] for option in result["options"]] == [
        "None",
        "P1Y",
        "P3Y",
    ]
    assert result["options"][0]["netSavingsObserved"] == 0
    assert result["options"][1]["name"] == "P1Y Savings Plan"
    assert result["options"][2]["name"] == "P3Y Savings Plan"


def test_request_schema_rejects_missing_discount_and_unknown_fields():
    with pytest.raises(ValueError, match="discountPercent"):
        validate_request(
            {
                "mode": "what-if",
                "term": "P1Y",
                "currencyCode": "USD",
                "expectedChangePercent": 0,
                "scenario": "balanced",
                "baselineHourlyCosts": [1],
            }
        )
    with pytest.raises(ValueError, match="not allowed"):
        validate_request(
            {
                "mode": "what-if",
                "term": "P1Y",
                "currencyCode": "USD",
                "expectedChangePercent": 0,
                "discountPercent": 20,
                "scenario": "balanced",
                "baselineHourlyCosts": [1],
                "discount": 20,
            }
        )


def test_connected_and_comparison_requests_are_validated_by_mode():
    connected = validate_request(
        {
            "mode": "connected",
            "scope": "/subscriptions/00000000-0000-0000-0000-000000000000",
            "term": "P3Y",
            "lookbackPeriod": "Last60Days",
            "recommendationScope": "Single",
        }
    )
    comparison = validate_request(
        {
            "mode": "comparison",
            "currencyCode": "USD",
            "expectedChangePercent": 0,
            "discountPercentP1Y": 10,
            "discountPercentP3Y": 20,
            "baselineHourlyCosts": [1, 2],
        }
    )

    assert connected["mode"] == "connected"
    assert comparison["mode"] == "comparison"
    with pytest.raises(ValueError, match="scope"):
        validate_request({"mode": "connected"})
    with pytest.raises(ValueError, match="discountPercentP3Y"):
        validate_request(
            {
                "mode": "comparison",
                "currencyCode": "USD",
                "expectedChangePercent": 0,
                "discountPercentP1Y": 10,
                "baselineHourlyCosts": [1, 2],
            }
        )
