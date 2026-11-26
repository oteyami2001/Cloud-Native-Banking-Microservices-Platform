from __future__ import annotations

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]


def test_catalog_has_twenty_controls_with_existing_evidence():
    controls = yaml.safe_load((ROOT / "policies" / "security-controls.yaml").read_text())["controls"]
    assert [c["id"] for c in controls] == [f"BANK-SEC-{i:03d}" for i in range(1, 21)]
    for c in controls:
        assert c["status"] in {"implemented_offline", "designed", "planned"}
        for path in c["evidence"] + c["tests"]:
            assert (ROOT / path).exists(), f"{c['id']}: {path} missing"


def test_every_control_is_mapped_and_no_compliance_claim_is_made():
    doc = yaml.safe_load((ROOT / "policies" / "compliance-mapping.yaml").read_text())
    assert set(doc["mappings"]) == {f"BANK-SEC-{i:03d}" for i in range(1, 21)}
    assert "not a compliance claim" in doc["disclaimer"]
