"""Static checks over the Terraform source (no AWS, no Terraform binary needed).

Complements the ``terraform test`` suites under terraform/modules/*/tests.
"""

from __future__ import annotations

import re
from pathlib import Path

import hcl2
import pytest

from shared.schema import LOGICAL

ROOT = Path(__file__).resolve().parents[2]
TF = ROOT / "terraform"


def _platform_locals() -> dict:
    doc = hcl2.load((TF / "modules" / "platform" / "main.tf").open())
    merged: dict = {}
    for block in doc["locals"]:
        merged.update(block)
    return merged


def _resolve(entry, locals_):
    if isinstance(entry, str):
        m = re.fullmatch(r"\$\{local\.(\w+)\}", entry)
        assert m, entry
        return locals_[m.group(1)]
    return entry


@pytest.fixture(scope="module")
def services():
    loc = _platform_locals()
    return {name: [_resolve(s, loc) for s in spec["policy"]] for name, spec in loc["services"].items()}


def test_only_ledger_can_write_the_ledger_table(services):
    writes = {"dynamodb:PutItem", "dynamodb:UpdateItem", "dynamodb:DeleteItem"}
    for name, statements in services.items():
        for st in statements:
            touches_ledger = any('t["ledger"]' in r for r in st["resources"])
            if touches_ledger and writes & set(st["actions"]):
                assert name == "ledger", f"{name} can write the ledger table ({st['sid']})"


def test_no_wildcard_actions_or_resources(services):
    for name, statements in services.items():
        for st in statements:
            assert not any(a.endswith(":*") or a == "*" for a in st["actions"]), (name, st["sid"])
            assert "*" not in st["resources"], (name, st["sid"])


def test_identity_lookup_is_restricted_by_leading_keys(services):
    for name, statements in services.items():
        for st in statements:
            if any('t["customers"]' in r for r in st["resources"]) and name != "customer":
                assert st["actions"] == ["dynamodb:GetItem"]
                assert st["conditions"][0]["values"] == ["IDENTITY#*"]


def test_internal_invocation_is_least_privilege(services):
    invokers = {n for n, sts in services.items() for st in sts if "lambda:InvokeFunction" in st["actions"]}
    assert invokers == {"account", "transfer"}


def test_schema_parity_with_terraform():
    text = (TF / "modules" / "dynamodb" / "main.tf").read_text()
    for logical, spec in LOGICAL.items():
        assert re.search(rf"^\s+{logical}\s+=", text, re.M), f"table {logical} missing from Terraform"
        for name, pk, sk in spec["gsis"]:
            assert f'name = "{name}", pk = "{pk}", sk = "{sk}"' in text, f"GSI {name} on {logical} differs"
        assert ("stream = true" in re.search(rf"^\s+{logical}\s+=.*$", text, re.M).group(0)) == spec["stream"]


def test_every_root_pins_provider_and_validates_account():
    for root in ("bootstrap", "envs/dev", "envs/staging", "envs/prod"):
        text = "".join(p.read_text() for p in (TF / root).glob("*.tf"))
        assert 'version = "~> 6.70"' in text, root
        assert "allowed_account_ids" in text, root
        if root.startswith("envs"):
            assert "use_lockfile = true" in text and "encrypt      = true" in text, root


def test_no_persistent_compute_in_mvp():
    forbidden = ("aws_nat_gateway", "aws_lb\"", "aws_instance", "aws_eks_cluster", "aws_rds_cluster", "aws_ecs_service")
    for path in (TF / "modules").rglob("*.tf"):
        text = path.read_text()
        for res in forbidden:
            assert f'resource "{res}' not in text, f"{res} found in {path}"


def test_lambda_code_is_owned_by_deploy_workflow():
    text = (TF / "modules" / "lambda-service" / "main.tf").read_text()
    assert "ignore_changes = [filename, source_code_hash" in text
    assert "ignore_changes = [function_version, routing_config]" in text


def test_deploy_role_can_reach_the_site_bucket():
    """The frontend bucket name built by the platform must match the deploy role's S3 pattern
    (first frontend deploy failed with AccessDenied on s3:ListBucket, 2026-11-26)."""

    import fnmatch

    platform = (TF / "modules" / "platform" / "main.tf").read_text()
    oidc = (TF / "modules" / "iam-oidc" / "main.tf").read_text()
    bucket_expr = re.search(r'bucket_name\s+=\s+"\$\{local\.p\}-site-\$\{local\.account_id\}"', platform)
    assert bucket_expr, "frontend bucket naming changed; update the deploy role pattern and this test"
    example_bucket = "novabank-dev-site-123456789012"
    frontend_sync = re.split(r'sid\s+=\s+"FrontendSync"', oidc)[1]
    pattern = re.search(r'"arn:aws:s3:::\$\{var\.name_prefix\}([^"/]*)"', frontend_sync).group(1)
    assert fnmatch.fnmatch(example_bucket, "novabank" + pattern), pattern


def test_no_plan_time_generated_files():
    """Saved plans are applied on a different runner, so every file a resource
    reads must be committed rather than generated during plan."""

    for path in (TF / "modules").rglob("*.tf"):
        assert 'data "archive_file"' not in path.read_text(), path
    assert (TF / "modules" / "lambda-service" / "placeholder.zip").is_file()
