"""Each Lambda artifact must be self-contained and import cleanly."""

from __future__ import annotations

import json
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
import build_lambda  # noqa: E402

HANDLERS = {
    "customer": "services.customer.handler",
    "account": "services.account.handler",
    "ledger": "services.ledger.handler",
    "transfer": "services.transfer.handler",
    "fraud": "services.fraud.handler",
    "notification": "services.notification.handler",
    "audit": "services.audit.handler",
    "outbox-publisher": "workers.outbox_publisher.handler",
    "outbox-reconciliation": "workers.outbox_reconciliation.handler",
    "ledger-reconciliation": "workers.ledger_reconciliation.handler",
}


@pytest.fixture(scope="module")
def dist(tmp_path_factory):
    out = tmp_path_factory.mktemp("dist")
    return out, {build_lambda.build(n, p, out, "test")["service"]: out for n, p in build_lambda.PACKAGES.items()}


@pytest.mark.parametrize("service", sorted(HANDLERS))
def test_artifact_imports_in_isolation(dist, tmp_path, service):
    out, _ = dist
    with zipfile.ZipFile(out / f"{service}.zip") as zf:
        zf.extractall(tmp_path)
        names = zf.namelist()
    # Independence: no other service's code is shipped.
    for other, module in HANDLERS.items():
        if other != service and module.startswith("services.") and other not in {"audit"}:
            assert f"{module.replace('.', '/')}.py" not in names
    code = f"import {HANDLERS[service]} as m; assert callable(m.handler)"
    env = {"PYTHONPATH": str(tmp_path), "PATH": "/usr/bin:/bin", "AWS_DEFAULT_REGION": "us-east-2"}
    if service == "fraud":
        code += "; from services.fraud.rules import load_policy; assert load_policy()['policy_version']"
    result = subprocess.run([sys.executable, "-c", code], cwd=tmp_path, env=env, capture_output=True, text=True, check=False)
    assert result.returncode == 0, result.stderr


def test_build_is_reproducible(tmp_path):
    a = build_lambda.build("ledger", build_lambda.PACKAGES["ledger"], tmp_path, "v1")
    b = build_lambda.build("ledger", build_lambda.PACKAGES["ledger"], tmp_path, "v1")
    assert a["sha256"] == b["sha256"]
    with zipfile.ZipFile(tmp_path / "ledger.zip") as zf:
        assert json.loads(zf.read("BUILD_INFO.json"))["version"] == "v1"
