from __future__ import annotations

from math import isfinite
from statistics import mean, pstdev
from typing import Any

from .models import ForecastRequest

TERM_DAYS = {"P1Y": 365, "P3Y": 1095}
SCENARIO_PERCENTILES = {
    "conservative": 0.30,
    "balanced": 0.50,
    "maximumSavings": 0.70,
}


def _percentile(values: list[float], percentile: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    position = (len(ordered) - 1) * percentile
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    fraction = position - lower
    return ordered[lower] * (1 - fraction) + ordered[upper] * fraction


def _round(value: float) -> float:
    return round(value + 1e-10, 2)


def _confidence(costs: list[float]) -> tuple[str, float]:
    average = mean(costs) if costs else 0.0
    if average == 0:
        return "Low", 0.0
    volatility = pstdev(costs) / average * 100 if average else 0.0
    confidence = (
        "High"
        if len(costs) >= 720 and volatility <= 25
        else "Medium"
        if len(costs) >= 168 and volatility <= 50
        else "Low"
    )
    return confidence, volatility


def _validate_values(request: ForecastRequest) -> None:
    if request.term not in TERM_DAYS:
        raise ValueError("term must be P1Y or P3Y.")
    if not request.baseline_hourly_costs:
        raise ValueError("baselineHourlyCosts or csvData is required.")
    if any(
        not isfinite(value) or value < 0
        for value in request.baseline_hourly_costs
    ):
        raise ValueError(
            "baselineHourlyCosts must contain only finite, non-negative values."
        )
    if not isfinite(request.expected_change_percent):
        raise ValueError("expectedChangePercent must be finite.")
    if request.expected_change_percent < -100:
        raise ValueError("expectedChangePercent cannot be less than -100.")
    if request.discount_percent is None:
        raise ValueError(
            "discountPercent is required; do not invent a modeled discount."
        )
    if (
        not isfinite(request.discount_percent)
        or not 0 <= request.discount_percent < 100
    ):
        raise ValueError("discountPercent must be at least 0 and less than 100.")
    if request.hourly_commitment is not None and (
        not isfinite(request.hourly_commitment)
        or request.hourly_commitment < 0
    ):
        raise ValueError("hourlyCommitment must be finite and non-negative.")


def recommend_commitments(
    costs: list[float], discount_percent: float
) -> dict[str, dict[str, float]]:
    discount_factor = 1 - discount_percent / 100
    recommendations: dict[str, dict[str, float]] = {}
    for scenario, percentile in SCENARIO_PERCENTILES.items():
        payg_coverage = _percentile(costs, percentile)
        recommendations[scenario] = {
            "hourlyCommitment": _round(payg_coverage * discount_factor),
            "hourlyPaygCoverageTarget": _round(payg_coverage),
        }
    return recommendations


def _calculate_option(
    *,
    costs: list[float],
    term: str,
    discount_percent: float,
    hourly_commitment: float,
    expected_change_percent: float,
    currency_code: str,
    mode: str,
    scenario: str,
) -> dict[str, Any]:
    if term not in TERM_DAYS:
        raise ValueError("term must be P1Y or P3Y.")
    factor = 1 + expected_change_percent / 100
    projected = [value * factor for value in costs]
    discount_factor = 1 - discount_percent / 100
    payg_coverage_capacity = (
        hourly_commitment / discount_factor if discount_factor else 0
    )

    observed_baseline = sum(costs)
    scenario_baseline = sum(projected)
    commitment_cost = hourly_commitment * len(projected)
    covered_payg = sum(min(value, payg_coverage_capacity) for value in projected)
    remaining_payg = sum(
        max(0.0, value - payg_coverage_capacity) for value in projected
    )
    overage = remaining_payg if hourly_commitment else 0.0
    used_commitment_cost = covered_payg * discount_factor
    unused_commitment_cost = max(
        0.0, commitment_cost - used_commitment_cost
    )
    modeled_cost = commitment_cost + remaining_payg
    net_savings = scenario_baseline - modeled_cost
    utilization = (
        used_commitment_cost / commitment_cost * 100
        if commitment_cost
        else 0.0
    )
    coverage = (
        covered_payg / scenario_baseline * 100 if scenario_baseline else 0.0
    )
    confidence, volatility = _confidence(costs)

    warnings: list[str] = []
    if utilization < 85 and commitment_cost:
        warnings.append(
            "Modeled commitment utilization is below 85%; unused commitment "
            "may reduce or eliminate savings."
        )
    if volatility > 50:
        warnings.append("Historical hourly cost is highly variable.")
    if expected_change_percent < -10:
        warnings.append("The scenario assumes a material usage reduction.")
    if scenario_baseline == 0:
        warnings.append(
            "No eligible PAYG cost remains in this scenario; no savings are modeled."
        )
    if net_savings < 0:
        warnings.append("This modeled commitment costs more than pay-as-you-go.")
    has_commitment = commitment_cost > 0
    risk = (
        "Higher"
        if (has_commitment and utilization < 85)
        or volatility > 50
        or net_savings < 0
        else "Moderate"
        if (has_commitment and utilization < 95) or volatility > 25
        else "Lower"
    )

    annualization = (24 * TERM_DAYS[term]) / len(projected)
    return {
        "mode": mode,
        "term": term,
        "scenario": scenario,
        "currencyCode": currency_code,
        "discountPercent": _round(discount_percent),
        "dataHours": len(projected),
        "hourlyCommitment": _round(hourly_commitment),
        "hourlyPaygCoverageCapacity": _round(payg_coverage_capacity),
        "baselineEligibleCostObserved": _round(observed_baseline),
        "scenarioEligibleCostObserved": _round(scenario_baseline),
        "commitmentCostObserved": _round(commitment_cost),
        "modeledCostObserved": _round(modeled_cost),
        "netSavingsObserved": _round(net_savings),
        "savingsPercent": _round(
            net_savings / scenario_baseline * 100 if scenario_baseline else 0
        ),
        "coveragePercent": _round(coverage),
        "utilizationPercent": _round(utilization),
        "remainingPaygCostObserved": _round(remaining_payg),
        "overageCostObserved": _round(overage),
        "unusedCommitmentCostObserved": _round(unused_commitment_cost),
        "projectedTermBaselineCost": _round(scenario_baseline * annualization),
        "projectedTermModeledCost": _round(modeled_cost * annualization),
        "projectedTermNetSavings": _round(net_savings * annualization),
        "confidence": confidence,
        "risk": risk,
        "volatilityPercent": _round(volatility),
        "warnings": warnings,
        "assumptions": [
            f"Expected usage change: {expected_change_percent}%.",
            f"User-supplied modeled discount: {discount_percent}%.",
            "Hourly commitment is the assumed hourly plan payment; the modeled "
            "PAYG coverage capacity divides it by (1 - discount).",
            "Each supplied cost is treated as one consecutive hourly observation.",
            "Term projections scale the scenario's observed hourly average over "
            "the full term; future usage is not forecast.",
            "Confidence and risk are transparent heuristics based on data volume, "
            "variability, and modeled utilization; they are not Azure scores.",
            "Scenario commitments use sample percentiles; they do not reproduce "
            "Microsoft's recommendation algorithm.",
            "What-if results are planning estimates, not an Azure purchase recommendation.",
        ],
    }


def calculate_forecast(request: ForecastRequest) -> dict[str, Any]:
    _validate_values(request)
    recommendations = recommend_commitments(
        request.baseline_hourly_costs, request.discount_percent
    )
    scenario = request.scenario
    if scenario == "custom":
        if request.hourly_commitment is None:
            raise ValueError(
                "hourlyCommitment is required for the custom scenario."
            )
        commitment = request.hourly_commitment
    elif scenario in recommendations:
        if request.hourly_commitment is not None:
            raise ValueError(
                "hourlyCommitment is only valid with the custom scenario."
            )
        commitment = recommendations[scenario]["hourlyCommitment"]
    else:
        raise ValueError(
            "scenario must be conservative, balanced, maximumSavings, or custom."
        )

    result = _calculate_option(
        costs=request.baseline_hourly_costs,
        term=request.term,
        discount_percent=request.discount_percent,
        hourly_commitment=commitment,
        expected_change_percent=request.expected_change_percent,
        currency_code=request.currency_code,
        mode="what-if",
        scenario=scenario,
    )
    result["scenarioCommitments"] = recommendations
    return result


def calculate_comparison(data: dict[str, Any]) -> dict[str, Any]:
    costs = [float(value) for value in data["baselineHourlyCosts"]]
    expected_change = float(data["expectedChangePercent"])
    currency_code = data["currencyCode"]
    if not costs or any(not isfinite(value) or value < 0 for value in costs):
        raise ValueError(
            "baselineHourlyCosts must contain finite, non-negative hourly values."
        )
    if not isfinite(expected_change) or expected_change < -100:
        raise ValueError(
            "expectedChangePercent must be finite and at least -100."
        )

    projected = [value * (1 + expected_change / 100) for value in costs]
    baseline_observed = sum(costs)
    scenario_baseline = sum(projected)
    confidence, volatility = _confidence(costs)
    comparison_options: list[dict[str, Any]] = [
        {
            "name": "No Commitment",
            "term": "None",
            "currencyCode": currency_code,
            "dataHours": len(costs),
            "baselineEligibleCostObserved": _round(baseline_observed),
            "scenarioEligibleCostObserved": _round(scenario_baseline),
            "commitmentCostObserved": 0.0,
            "modeledCostObserved": _round(scenario_baseline),
            "netSavingsObserved": 0.0,
            "savingsPercent": 0.0,
            "coveragePercent": 0.0,
            "utilizationPercent": 0.0,
            "remainingPaygCostObserved": _round(scenario_baseline),
            "overageCostObserved": 0.0,
            "unusedCommitmentCostObserved": 0.0,
            "projectedTermCostByTerm": {
                term: _round(
                    scenario_baseline * (24 * TERM_DAYS[term]) / len(costs)
                )
                for term in ("P1Y", "P3Y")
            },
            "confidence": confidence,
            "risk": "Lower",
            "volatilityPercent": _round(volatility),
            "warnings": [],
            "assumptions": [
                "Pay-as-you-go baseline; no commitment or modeled discount is applied.",
                f"Historical hourly cost variability: {_round(volatility)}%.",
            ],
        }
    ]

    for term, key in (
        ("P1Y", "discountPercentP1Y"),
        ("P3Y", "discountPercentP3Y"),
    ):
        discount = float(data[key])
        request = ForecastRequest(
            mode="what-if",
            term=term,
            lookback_period="Last30Days",
            hourly_commitment=None,
            baseline_hourly_costs=costs,
            expected_change_percent=expected_change,
            discount_percent=discount,
            scope=None,
            scenario="balanced",
            currency_code=currency_code,
        )
        option = calculate_forecast(request)
        option["name"] = f"{term} Savings Plan"
        comparison_options.append(option)

    return {
        "mode": "comparison",
        "currencyCode": currency_code,
        "dataHours": len(costs),
        "expectedChangePercent": expected_change,
        "options": comparison_options,
        "assumptions": [
            "The expected usage change is applied uniformly to every supplied hour.",
            "Term projections scale the scenario's observed hourly average over "
            "the full term; future usage is not forecast.",
            "Confidence and risk are transparent heuristics based on data volume, "
            "variability, and modeled utilization; they are not Azure scores.",
        ],
        "notice": (
            "This comparison is a planning model based only on the supplied "
            "costs and discount assumptions; it is not an Azure recommendation."
        ),
    }
