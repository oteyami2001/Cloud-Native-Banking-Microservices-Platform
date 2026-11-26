#!/usr/bin/env python3
"""Deploy verified Lambda packages with versioned aliases and automatic rollback.

For each service:
  1. upload the package to the artifact bucket under its SHA-256 (immutable key)
  2. update function code, wait, publish an immutable version
  3. record the alias's previous version, then point "live" at the new one
After all services: smoke-invoke internal services and check CloudWatch alarms.
If anything fails, every alias already moved is pointed back to its previous
version (T27). Output is Markdown for the GitHub step summary.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

import boto3

SMOKE = {"ledger": {"action": "get_balance", "payload": {"account_id": "GL-1000"}}}


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

        for svc, request in SMOKE.items():
            if wanted and svc not in wanted:
                continue
            out = lam.invoke(FunctionName=f"{prefix}-{svc}:live", Payload=json.dumps(request).encode())
            body = json.loads(out["Payload"].read())
            # A NOT_FOUND domain error still proves code, IAM and DynamoDB access work.
            healthy = body.get("ok") or body.get("error", {}).get("code") == "NOT_FOUND"
            if out.get("FunctionError") or not healthy:
                raise RuntimeError(f"smoke test failed for {svc}: {body}")
        time.sleep(int(os.environ.get("BAKE_SECONDS", "60")))
        alarms = cw.describe_alarms(AlarmNamePrefix=f"{prefix}-lambda-errors", StateValue="ALARM")["MetricAlarms"]
        if alarms:
            raise RuntimeError("alarms firing after deploy: " + ", ".join(a["AlarmName"] for a in alarms))
        print("\nSmoke tests and alarm checks passed.")
        return 0
    except Exception as exc:  # noqa: BLE001 - any failure triggers rollback
        print(f"\n**Deployment failed:** {exc}\n\nRolling back:")
        for fn, previous, new in reversed(moved):
            lam.update_alias(FunctionName=fn, Name="live", FunctionVersion=previous)
            print(f"- {fn}: live {new} -> {previous}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
