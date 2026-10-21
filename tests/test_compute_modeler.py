import json

import pytest

from api.compute_modeler import calculate_compute_model, copilot_prompt
from api.calculator import calculate_forecast
from api.models import ForecastRequest


def model(**overrides):
    return calculate_compute_model(**{
        "period_hours": 100, "compute_hours": 90, "payg_rate": 10,
        "discount_percent": 20, "hourly_commitment": 8, "currency_code": "USD", "term": "P1Y",
        **overrides,
    })


def test_commitment_is_charged_during_idle_hours_and_break_even_is_runtime():
    result = model()
    assert result["baselineCost"] == 900
    assert result["commitmentCost"] == result["modeledCost"] == 800
    assert result["savingsAmount"] == 100
    assert result["unusedCommitment"] == 80
    assert result["remainingPaygCost"] == 0
    assert result["breakEvenHours"] == 80
    assert result["breakEvenRuntimePercent"] == 80
    assert result["runtimeMarginHours"] == 10
    assert result["projectedTermSavings"] == 8760
    assert result["outcome"] == "Savings"
    assert result["breakEvenAttainable"] and result["positiveSavingsPossible"]
    assert "elapsed hours" in " ".join(result["guidance"])
    assert json.loads(json.dumps(result, allow_nan=False)) == result


@pytest.mark.parametrize("runtime,savings,outcome", [(0, -800, "Loss"), (79, -10, "Loss"), (80, 0, "Break-even"), (100, 200, "Savings")])
def test_exact_break_even_and_loss_boundaries(runtime, savings, outcome):
    result = model(compute_hours=runtime)
    assert result["savingsAmount"] == savings
    assert result["outcome"] == outcome


def test_undercommitment_retains_uncovered_payg():
    result = model(hourly_commitment=4)
    assert result["remainingPaygCost"] == 450
    assert result["modeledCost"] == 850
    assert result["savingsAmount"] == 50
    assert result["breakEvenHours"] == 80
    assert result["utilizationPercent"] == 90
    assert result["coveragePercent"] == 50


def test_overcommitment_makes_break_even_impossible():
    result = model(hourly_commitment=12, compute_hours=100)
    assert result["breakEvenHours"] == 120
    assert not result["breakEvenAttainable"] and not result["positiveSavingsPossible"]
    assert result["savingsAmount"] == -200
    assert "cannot break even" in " ".join(result["guidance"])


def test_commitment_above_discounted_running_cost_can_still_save_with_enough_runtime():
    result = model(hourly_commitment=9, compute_hours=100)
    assert result["breakEvenHours"] == 90
    assert result["breakEvenAttainable"]
    assert result["savingsAmount"] == 100
    assert result["unusedCommitment"] == 100


@pytest.mark.parametrize("commitment", [0, 4, 8, 9, 12])
@pytest.mark.parametrize("runtime", [0, 50, 100])
def test_compute_model_matches_existing_hourly_calculator(commitment, runtime):
    actual = model(hourly_commitment=commitment, compute_hours=runtime)
    hourly = calculate_forecast(ForecastRequest.from_dict({
        "mode": "what-if", "term": "P1Y", "scenario": "custom",
        "currencyCode": "USD", "expectedChangePercent": 0,
        "discountPercent": 20, "hourlyCommitment": commitment,
        "baselineHourlyCosts": [10] * runtime + [0] * (100 - runtime),
    }))
    for key, original in (
        ("baselineCost", "scenarioEligibleCostObserved"),
        ("modeledCost", "modeledCostObserved"), ("savingsAmount", "netSavingsObserved"),
        ("unusedCommitment", "unusedCommitmentCostObserved"), ("remainingPaygCost", "remainingPaygCostObserved"),
        ("projectedTermSavings", "projectedTermNetSavings"),
    ):
        assert actual[key] == pytest.approx(hourly[original])


def test_zero_commitment_is_payg_not_free_discount():
    result = model(hourly_commitment=0)
    assert result["modeledCost"] == result["baselineCost"] == 900
    assert result["savingsAmount"] == result["unusedCommitment"] == 0
    assert result["breakEvenHours"] is None
    assert result["runtimeMarginHours"] is None
    assert "no meaningful break-even" in " ".join(result["guidance"])


def test_zero_discount_can_only_break_even_not_save():
    result = model(discount_percent=0, compute_hours=100)
    assert result["breakEvenHours"] == 100
    assert not result["positiveSavingsPossible"]
    assert result["savingsAmount"] == 0
    assert "no positive savings" in " ".join(result["guidance"])


def test_fractional_hours_and_three_year_projection():
    result = model(period_hours=1.5, compute_hours=1.25, term="P3Y")
    assert result["commitmentCost"] == 12
    assert result["savingsAmount"] == .5
    assert result["breakEvenHours"] == 1.2
    assert result["termHours"] == 26280
    assert result["projectedTermSavings"] == 8760


@pytest.mark.parametrize("field,value", [
    ("period_hours", 0), ("period_hours", 9000), ("compute_hours", 101),
    ("compute_hours", -1), ("compute_hours", True), ("compute_hours", "10"),
    ("payg_rate", 0), ("payg_rate", float("nan")), ("hourly_commitment", float("inf")),
    ("hourly_commitment", -1), ("hourly_commitment", 1e10), ("discount_percent", 100),
    ("discount_percent", -1), ("currency_code", "usd"), ("currency_code", "=X"),
    ("term", "monthly"),
    ("payg_rate", 1e-320), ("hourly_commitment", 1e-320),
])
def test_invalid_inputs_have_explicit_errors(field, value):
    with pytest.raises(ValueError):
        model(**{field: value})


def test_sensitivity_uses_same_formula_includes_actual_and_does_not_add_options():
    result = model()
    points = result["sensitivity"]
    assert [point["computeHours"] for point in points] == [0, 50, 80, 90, 100]
    assert [point["savingsAmount"] for point in points] == [-800, -300, 0, 100, 200]
    assert points[3]["savingsAmount"] == result["savingsAmount"]
    for point in points:
        assert point["baselineCost"] - point["modeledCost"] == pytest.approx(point["savingsAmount"])


def test_copilot_handoff_contains_calculated_figures_and_limitations():
    prompt = copilot_prompt(model())
    assert '"breakEvenHours": 80.0' in prompt
    assert "not generated by Copilot" in prompt
    assert "do not invent" in prompt
    assert "not purchase instructions" in prompt
    with pytest.raises(ValueError):
        copilot_prompt({"mode": "connected"})
