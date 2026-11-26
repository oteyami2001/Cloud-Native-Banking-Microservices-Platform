"""API and event contract tests."""

from __future__ import annotations

import json
from pathlib import Path

import jsonschema
import pytest
import yaml
from openapi_spec_validator import validate

from shared.contracts import EVENT_SCHEMAS, load_schema
from tests.support import ROUTES

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="module")
def spec():
    return yaml.safe_load((ROOT / "contracts" / "openapi.yaml").read_text())


def test_openapi_document_is_valid(spec):
    validate(spec)


def test_every_implemented_route_is_documented_and_vice_versa(spec):
    documented = {f"{m.upper()} {p}" for p, ops in spec["paths"].items() for m in ops if m in {"get", "post", "patch", "put", "delete"}}
    assert documented == set(ROUTES)


def test_terraform_routes_match_contract(spec):
    tf = (ROOT / "terraform" / "envs" / "dev" / "main.tf").read_text()
    for route in ROUTES:
        assert f'"{route}"' in tf, f"route {route} missing from terraform/envs/dev/main.tf"


def test_event_schemas_are_valid_json_schema():
    for event_type in EVENT_SCHEMAS:
        jsonschema.Draft202012Validator.check_schema(load_schema(event_type))


def test_emitted_events_conform_to_published_schemas(bank):
    c = bank.customer()
    other = bank.customer()
    src, dst = bank.account(c, opening_minor=2_500_000), bank.account(c)
    far = bank.account(other)
    bank.transfer(c, src, dst, 1_000)  # completed
    bank.transfer(c, src, dst, 99_999_999)  # insufficient funds -> rejected
    bank.transfer(c, src, far, 600_000)  # held -> pending review + fraud alert
    events = [json.loads(i["payload"]) for i in bank.scan("outbox")]
    seen = set()
    for event in events:
        if event["event_type"] in EVENT_SCHEMAS:
            jsonschema.validate(event, load_schema(event["event_type"]))
            seen.add(event["event_type"])
    assert seen == set(EVENT_SCHEMAS)


def test_transfer_response_matches_openapi_schema(bank, spec):
    c = bank.customer()
    src, dst = bank.account(c, opening_minor=10_000), bank.account(c)
    _, body = bank.transfer(c, src, dst, 100)
    schema = dict(spec["components"]["schemas"]["Transfer"])
    jsonschema.validate(body, {**schema, "$defs": {}})
