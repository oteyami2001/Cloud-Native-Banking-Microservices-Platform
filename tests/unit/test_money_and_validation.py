from __future__ import annotations

import pytest
from hypothesis import given
from hypothesis import strategies as st

from shared.errors import ValidationError
from shared.money import Money, format_minor, parse_decimal_amount, validate_amount_minor, validate_currency


@pytest.mark.parametrize("text,expected", [("250", 25_000), ("250.00", 25_000), ("0.01", 1), ("1234.5", 123_450), ("  9.99 ", 999)])
def test_parse_decimal_amount(text, expected):
    assert parse_decimal_amount(text) == expected


@pytest.mark.parametrize("text", ["", "-1", "1.001", "1e3", "abc", "0", "0.00", "01.00", "1,000.00", "NaN", "Infinity"])
def test_parse_decimal_amount_rejects(text):
    with pytest.raises(ValidationError):
        parse_decimal_amount(text)


@given(st.integers(min_value=1, max_value=100_000_000))
def test_format_and_parse_round_trip(minor):
    assert parse_decimal_amount(format_minor(minor)) == minor


def test_format_negative():
    assert format_minor(-150) == "-1.50"


@pytest.mark.parametrize("value", [0, -1, 1.0, True, "1", None, 100_000_001])
def test_validate_amount_minor_rejects(value):
    with pytest.raises(ValidationError):
        validate_amount_minor(value)


def test_money_arithmetic_is_integer_only_and_currency_safe():
    a, b = Money(1_000, "USD"), Money(250, "USD")
    assert (a - b).amount_minor == 750 and str(a + b) == "12.50 USD"
    with pytest.raises(ValidationError):
        Money(1.5, "USD")  # type: ignore[arg-type]
    with pytest.raises(ValidationError):
        validate_currency("GBP")


def test_float_arithmetic_would_have_been_wrong():
    """Why integer minor units: 0.1 + 0.2 != 0.3 in binary floating point."""

    assert 0.1 + 0.2 != 0.3
    assert parse_decimal_amount("0.10") + parse_decimal_amount("0.20") == parse_decimal_amount("0.30")


def test_validate_object_rules():
    from shared.validation import boolean, integer, string, validate_object

    rules = {"a": string(max_len=3), "n": integer(minimum=1, maximum=5)}
    assert validate_object({"a": "abc", "n": 2}, required=rules) == {"a": "abc", "n": 2}
    for bad in ({"a": "abcd", "n": 2}, {"a": "a", "n": 9}, {"a": "a"}, {"a": "a", "n": 1, "x": 1}, [], {"a": 1, "n": 1}):
        with pytest.raises(ValidationError):
            validate_object(bad, required=rules)
    with pytest.raises(ValidationError):
        validate_object({"b": "yes"}, required={}, optional={"b": boolean()})
    with pytest.raises(ValidationError):
        validate_object({"c": "z"}, required={"c": string(choices={"x"})})
