#!/usr/bin/env python3
"""Fail closed unless every package matches the build manifest checksum."""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path


def main(manifest_path: str) -> int:
    manifest_file = Path(manifest_path)
    manifest = json.loads(manifest_file.read_text())
    ok = True
    for pkg in manifest["packages"]:
        path = manifest_file.parent / pkg["file"]
        digest = hashlib.sha256(path.read_bytes()).hexdigest() if path.exists() else "missing"
        status = "OK" if digest == pkg["sha256"] else "MISMATCH"
        ok &= status == "OK"
        print(f"{status} {pkg['file']} {digest}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1]))
