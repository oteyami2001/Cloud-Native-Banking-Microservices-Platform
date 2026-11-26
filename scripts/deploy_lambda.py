#!/usr/bin/env python3
"""Deploy verified Lambda packages with versioned aliases and automatic rollback.

For each service:
  1. upload the package to the artifact bucket under its SHA-256 (immutable key)
  2. update function code, wait, publish an immutable version
  3. record the alias's previous version, then point "live" at the new one
After all services: smoke-test with the ledger-reconciliation job (exercises IAM,
DynamoDB, S3 evidence and the outbox end to end; the deploy role may invoke only
that function) and check that no Lambda error alarm for a deployed function has
entered ALARM since this deployment started (alarms already firing from the
previous code, e.g. placeholders, are ignored).
If anything fails, every alias already moved is pointed back to its previous
version (T27). Output is Markdown for the GitHub step summary.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

import boto3

SMOKE_FUNCTION = "ledger-reconciliation"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--services", default="all")
    args = parser.parse_args()

    prefix = os.environ["NAME_PREFIX"]
    bucket = os.environ["ARTIFACT_BUCKET"]
    lam, s3, cw = boto3.client("lambda"), boto3.client("s3"), boto3.client("cloudwatch")
    manifest_path = Path(args.manifest)
    manifest = json.loads(manifest_path.read_text())
    wanted = None if args.services == "all" else set(args.services.split(","))
    moved: list[tuple[str, str, str]] = []  # (function, previous, new)
    started = datetime.now(UTC)

    print(f"## Deployment of build `{manifest['version']}`\n\n| Service | Previous | New | Status |\n|---|---|---|---|")
    try:
        for pkg in manifest["packages"]:
            if wanted and pkg["service"] not in wanted:
                continue
            fn = f"{prefix}-{pkg['service']}"
            key = f"lambda/{pkg['service']}/{pkg['sha256']}.zip"
            s3.upload_file(str(manifest_path.parent / pkg["file"]), bucket, key, ExtraArgs={"ServerSideEncryption": "aws:kms"})
            lam.update_function_code(FunctionName=fn, S3Bucket=bucket, S3Key=key)
            lam.get_waiter("function_updated_v2").wait(FunctionName=fn)
            version = lam.publish_version(FunctionName=fn, Description=f"{manifest['version']} sha256:{pkg['sha256'][:16]}")["Version"]
            previous = lam.get_alias(FunctionName=fn, Name="live")["FunctionVersion"]
            lam.update_alias(FunctionName=fn, Name="live", FunctionVersion=version)
            moved.append((fn, previous, version))
            print(f"| {pkg['service']} | {previous} | {version} | alias moved |")

        if not wanted or SMOKE_FUNCTION in wanted:
            out = lam.invoke(FunctionName=f"{prefix}-{SMOKE_FUNCTION}:live", Payload=json.dumps({"trigger": "deploy-smoke"}).encode())
            body = json.loads(out["Payload"].read())
            if out.get("FunctionError") or body.get("status") not in {"BALANCED", "DISCREPANCIES_FOUND"}:
                raise RuntimeError(f"smoke test failed: {body}")
            print(f"\nSmoke test: reconciliation `{body['run_id']}` -> **{body['status']}** ({body['accounts_checked']} accounts)")
        time.sleep(int(os.environ.get("BAKE_SECONDS", "90")))
        deployed = {fn for fn, _, _ in moved}
        new_alarms = [
            a["AlarmName"]
            for a in cw.describe_alarms(AlarmNamePrefix=f"{prefix}-lambda-errors", StateValue="ALARM")["MetricAlarms"]
            if a["AlarmName"].removeprefix(f"{prefix}-lambda-errors-") in deployed and a["StateUpdatedTimestamp"] >= started
        ]
        if new_alarms:
            raise RuntimeError("error alarms raised after deploy: " + ", ".join(new_alarms))
        print("\nSmoke tests and alarm checks passed.")
        return 0
    except Exception as exc:  # noqa: BLE001 - any failure triggers rollback
        print(f"\n**Deployment failed:** {exc}\n\nRolling back:")
        print(f"::error::Deployment failed, rolling back: {exc}", file=sys.stderr)
        for fn, previous, new in reversed(moved):
            lam.update_alias(FunctionName=fn, Name="live", FunctionVersion=previous)
            print(f"- {fn}: live {new} -> {previous}")
            print(f"rolled back {fn}: live {new} -> {previous}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
