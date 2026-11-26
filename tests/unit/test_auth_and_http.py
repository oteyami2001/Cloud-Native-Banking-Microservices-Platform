from __future__ import annotations

import base64
import json

import pytest

from shared.auth import Principal, _split_claim
from shared.errors import ForbiddenError, ValidationError
from shared.http import decode_cursor, encode_cursor, page_limit
from tests.support import api_event, claims


@pytest.mark.parametrize(
    "raw,expected", [("[a b]", {"a", "b"}), ("[a, b]", {"a", "b"}), (["a"], {"a"}), (None, set()), ("a b", {"a", "b"})]
)
def test_split_claim_formats(raw, expected):
    assert _split_claim(raw) == expected


def test_principal_scope_and_group_checks():
    p = Principal("s", "u", frozenset({"novabank/read"}), frozenset({"customers"}))
    p.require_scope("novabank/read")
    with pytest.raises(ForbiddenError):
        p.require_scope("novabank/admin")
    with pytest.raises(ForbiddenError):
        p.require_group("fraud-reviewers")


def test_cursor_round_trip_and_tampering():
    key = {"PK": "ACCOUNT#1", "SK": "ENTRY#2"}
    assert decode_cursor(encode_cursor(key), expected={"PK": "ACCOUNT#1"}) == key
    assert encode_cursor(None) is None and decode_cursor(None, expected={}) is None
    with pytest.raises(ValidationError):
        decode_cursor(encode_cursor(key), expected={"PK": "ACCOUNT#2"})
    with pytest.raises(ValidationError):
        decode_cursor("%%%notbase64", expected={})


@pytest.mark.parametrize("raw", ["0", "101", "abc", "-1"])
def test_page_limit_bounds(raw):
    with pytest.raises(ValidationError):
        page_limit({"limit": raw})


def test_body_parsing_edge_cases(aws_env):
    from services.customer.handler import handler

    who = claims("edge-user")
    big = json.dumps({"display_name": "x" * 20_000})
    assert handler(api_event("POST /v1/customers", claims_=who, raw_body=big))["statusCode"] == 400
    assert handler(api_event("POST /v1/customers", claims_=who, raw_body="{not json"))["statusCode"] == 400
    ev = api_event("POST /v1/customers", claims_=who, raw_body=base64.b64encode(b'{"display_name":"B64 User"}').decode())
    ev["isBase64Encoded"] = True
    assert handler(ev)["statusCode"] == 201
    ev = api_event("POST /v1/customers", claims_=claims("edge-2"), raw_body="***")
    ev["isBase64Encoded"] = True
    assert handler(ev)["statusCode"] == 400


def test_ids_are_time_ordered_and_well_formed():
    import time

    from shared.ids import ID_RE, new_id

    a = new_id("TRF")
    time.sleep(0.002)
    b = new_id("TRF")
    assert ID_RE.match(a) and ID_RE.match(b) and a[4:14] <= b[4:14]


def test_structured_log_format(capsys):
    import logging

    from shared.logging import get_logger, log, set_correlation_id

    set_correlation_id("corr-abcdefgh")
    log(get_logger("unit-test"), logging.INFO, "hello", token="secret-value", amount_minor=5)
    line = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    assert line["message"] == "hello" and line["correlation_id"] == "corr-abcdefgh"
    assert line["token"] == "[REDACTED]" and line["amount_minor"] == 5
