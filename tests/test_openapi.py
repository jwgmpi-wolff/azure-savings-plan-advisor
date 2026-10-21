import json
from pathlib import Path


def test_openapi_describes_supported_endpoints_and_security():
    specification = json.loads(
        (Path(__file__).parents[1] / "agent" / "openapi-v2.json").read_text(
            encoding="utf-8"
        )
    )

    assert specification["swagger"] == "2.0"
    assert set(specification["paths"]) == {
        "/health",
        "/analyze-savings-plan",
        "/analyze-savings-plan-csv",
    }
    assert (
        specification["paths"]["/analyze-savings-plan"]["post"]["operationId"]
        == "AnalyzeSavingsPlan"
    )
    assert "entraOAuth" in specification["paths"][
        "/analyze-savings-plan"
    ]["post"]["security"][0]
    assert specification["paths"]["/analyze-savings-plan-csv"]["post"][
        "consumes"
    ] == ["multipart/form-data"]
    csv_parameters = specification["paths"]["/analyze-savings-plan-csv"][
        "post"
    ]["parameters"]
    required_csv_fields = {
        parameter["name"]
        for parameter in csv_parameters
        if parameter["required"]
    }
    assert {
        "csvFile",
        "term",
        "currencyCode",
        "discountPercent",
        "scenario",
        "expectedChangePercent",
    }.issubset(required_csv_fields)

    properties = specification["definitions"]["AnalyzeRequest"]["properties"]
    assert {
        "baselineHourlyCosts",
        "currencyCode",
        "discountPercent",
        "discountPercentP1Y",
        "discountPercentP3Y",
        "csvData",
        "expectedChangePercent",
        "scenario",
    }.issubset(properties)
