"""Deploy script: alias moves, smoke test and automatic rollback (T27 logic)."""

from __future__ import annotations

import io
import json
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
import deploy_lambda


class FakeLambda:
    def __init__(self, smoke_status="BALANCED"):
        self.aliases: dict[str, str] = {}
        self.versions: dict[str, int] = {}
        self.smoke_status = smoke_status

    def update_function_code(self, **_):
        return {}

    def get_waiter(self, _):
        return type("W", (), {"wait": lambda *_a, **_k: None})()

    def publish_version(self, FunctionName, **_):
        self.versions[FunctionName] = self.versions.get(FunctionName, 1) + 1
        return {"Version": str(self.versions[FunctionName])}

    def get_alias(self, FunctionName, Name):
        return {"FunctionVersion": self.aliases.get(FunctionName, "1")}

    def update_alias(self, FunctionName, Name, FunctionVersion):
        self.aliases[FunctionName] = FunctionVersion

    def invoke(self, FunctionName, Payload):
        body = {"status": self.smoke_status, "run_id": "REC-1", "accounts_checked": 0}
        return {"Payload": io.BytesIO(json.dumps(body).encode())}


class FakeS3:
    def upload_file(self, *_a, **_k):
        return None


class FakeCW:
    def __init__(self, alarms):
        self.alarms = alarms

    def describe_alarms(self, **_):
        return {"MetricAlarms": self.alarms}


@pytest.fixture
def manifest(tmp_path):
    pkgs = [{"service": s, "file": f"{s}.zip", "sha256": "0" * 64} for s in ("ledger", "ledger-reconciliation")]
    for p in pkgs:
        (tmp_path / p["file"]).write_bytes(b"zip")
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps({"version": "abc", "packages": pkgs}))
    return path


def run(monkeypatch, manifest, lam, cw):
    clients = {"lambda": lam, "s3": FakeS3(), "cloudwatch": cw}
    monkeypatch.setattr(deploy_lambda.boto3, "client", lambda name: clients[name])
    monkeypatch.setenv("NAME_PREFIX", "novabank-dev")
    monkeypatch.setenv("ARTIFACT_BUCKET", "bucket")
    monkeypatch.setenv("BAKE_SECONDS", "0")
    monkeypatch.setattr(sys, "argv", ["deploy_lambda.py", "--manifest", str(manifest)])
    return deploy_lambda.main()


def test_successful_deploy_moves_aliases(monkeypatch, manifest):
    lam = FakeLambda()
    old_alarm = {
        "AlarmName": "novabank-dev-lambda-errors-novabank-dev-ledger",
        "StateUpdatedTimestamp": datetime.now(UTC) - timedelta(hours=1),
    }
    assert run(monkeypatch, manifest, lam, FakeCW([old_alarm])) == 0  # pre-existing alarm ignored
    assert lam.aliases == {"novabank-dev-ledger": "2", "novabank-dev-ledger-reconciliation": "2"}


def test_failed_smoke_test_rolls_back(monkeypatch, manifest):
    lam = FakeLambda(smoke_status="ERROR")
    assert run(monkeypatch, manifest, lam, FakeCW([])) == 1
    assert lam.aliases == {"novabank-dev-ledger": "1", "novabank-dev-ledger-reconciliation": "1"}


def test_new_error_alarm_rolls_back(monkeypatch, manifest):
    lam = FakeLambda()
    new_alarm = {
        "AlarmName": "novabank-dev-lambda-errors-novabank-dev-ledger",
        "StateUpdatedTimestamp": datetime.now(UTC) + timedelta(seconds=5),
    }
    assert run(monkeypatch, manifest, lam, FakeCW([new_alarm])) == 1
    assert lam.aliases["novabank-dev-ledger"] == "1"
