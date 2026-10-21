import pytest

from api.csv_parser import parse_hourly_cost_csv


def test_parses_hourly_csv_without_changing_financial_values():
    result = parse_hourly_cost_csv(
        "timestamp,eligible PAYG cost,notes\n"
        "2026-01-01T00:00:00Z,12.45,synthetic\n"
        "2026-01-01T01:00:00Z,0,synthetic\n"
    )

    assert result == [12.45, 0]


@pytest.mark.parametrize(
    ("content", "message"),
    [
        ("", "cannot be empty"),
        ("timestamp,cost\n2026-01-01T00:00:00Z,1\n", "missing required"),
        (
            "timestamp,eligible_payg_cost\n"
            "2026-01-01T00:00:00Z,-1\n",
            "cannot be negative",
        ),
        (
            "timestamp,eligible_payg_cost\n"
            "2026-01-01T00:00:00Z,not-a-number\n",
            "must be numeric",
        ),
        (
            "timestamp,eligible_payg_cost\n"
            "2026-01-01T00:00:00,1\n",
            "must include a timezone",
        ),
        (
            "timestamp,eligible_payg_cost\n"
            "2026-01-01T00:00:00Z,1\n"
            "2026-01-01T02:00:00Z,1\n",
            "consecutive hourly",
        ),
        (
            "timestamp,eligible_payg_cost\n"
            "2026-01-01T00:00:00Z,1\n"
            "2026-01-01T00:00:00Z,2\n",
            "strictly increasing",
        ),
        (
            "timestamp,eligible_payg_cost\n"
            "2026-01-01T00:00:00Z\n",
            "missing values",
        ),
        ("timestamp,eligible_payg_cost\n", "at least one"),
        (
            'timestamp,eligible_payg_cost\n'
            '2026-01-01T00:00:00Z,"10\n',
            "syntax is malformed",
        ),
    ],
)
def test_rejects_invalid_csv_without_silent_correction(content, message):
    with pytest.raises(ValueError, match=message):
        parse_hourly_cost_csv(content)


def test_rejects_duplicate_column_names_after_normalization():
    with pytest.raises(ValueError, match="must be unique"):
        parse_hourly_cost_csv(
            "timestamp,eligible_payg_cost,Eligible PAYG Cost\n"
            "2026-01-01T00:00:00Z,1,1\n"
        )
