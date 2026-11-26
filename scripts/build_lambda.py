#!/usr/bin/env python3
"""Build immutable, reproducible Lambda packages.

Every package contains ``shared/`` plus only the service's own code, so each
microservice is deployed independently. Archives are deterministic (fixed
timestamps, sorted entries) so the SHA-256 of a package identifies its exact
contents; deploy-services verifies that hash before publishing.

Usage: python scripts/build_lambda.py [--out dist] [--version <git sha>]
"""

from __future__ import annotations

import argparse
import hashlib
import json
import zipfile
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
FIXED_TIME = (2020, 1, 1, 0, 0, 0)

PACKAGES = {
    "customer": ["services/customer"],
    "account": ["services/account"],
    "ledger": ["services/ledger"],
    "transfer": ["services/transfer"],
    "fraud": ["services/fraud"],
    "notification": ["services/notification"],
    "audit": ["services/audit"],
    "outbox-publisher": ["workers/outbox_publisher"],
    "outbox-reconciliation": ["workers/outbox_reconciliation", "workers/outbox_publisher"],
    "ledger-reconciliation": ["workers/ledger_reconciliation", "services/audit"],
}


def _files(paths: list[str]) -> list[Path]:
    out: set[Path] = set()
    for rel in ["shared", *paths]:
        for p in (ROOT / rel).rglob("*.py"):
            if "__pycache__" not in p.parts:
                out.add(p)
    for pkg in ("services", "workers"):
        out.add(ROOT / pkg / "__init__.py")
    return sorted(out)


def build(name: str, paths: list[str], out_dir: Path, version: str) -> dict[str, str]:
    target = out_dir / f"{name}.zip"
    with zipfile.ZipFile(target, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for f in _files(paths):
            info = zipfile.ZipInfo(str(f.relative_to(ROOT)), FIXED_TIME)
            info.external_attr = 0o644 << 16
            zf.writestr(info, f.read_bytes())
        if name == "fraud":
            policy = yaml.safe_load((ROOT / "policies" / "fraud-rules.yaml").read_text())
            info = zipfile.ZipInfo("services/fraud/fraud-rules.json", FIXED_TIME)
            info.external_attr = 0o644 << 16
            zf.writestr(info, json.dumps(policy, sort_keys=True, indent=2))
        info = zipfile.ZipInfo("BUILD_INFO.json", FIXED_TIME)
        zf.writestr(info, json.dumps({"service": name, "version": version}, sort_keys=True))
    digest = hashlib.sha256(target.read_bytes()).hexdigest()
    return {"service": name, "file": target.name, "sha256": digest, "version": version}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default="dist")
    parser.add_argument("--version", default="local")
    args = parser.parse_args()
    out = ROOT / args.out
    out.mkdir(parents=True, exist_ok=True)
    manifest = [build(n, p, out, args.version) for n, p in PACKAGES.items()]
    (out / "manifest.json").write_text(json.dumps({"version": args.version, "packages": manifest}, indent=2) + "\n")
    for m in manifest:
        print(f"{m['sha256']}  {m['file']}")


if __name__ == "__main__":
    main()
