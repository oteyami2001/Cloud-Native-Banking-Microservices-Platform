"""Supply-chain and pipeline guardrails (BANK-SEC-015/016/017)."""

from __future__ import annotations

import re
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
WORKFLOWS = sorted((ROOT / ".github" / "workflows").glob("*.yml"))
PRIVILEGED_ROLES = ("novabank-github-apply", "novabank-github-deploy", "novabank-github-cleanup")


def _load(path: Path) -> dict:
    doc = yaml.safe_load(path.read_text())
    doc["on"] = doc.pop(True, doc.get("on"))  # YAML 1.1 parses `on` as True
    return doc


def test_all_third_party_actions_are_pinned_to_commit_shas():
    for wf in WORKFLOWS:
        for line in wf.read_text().splitlines():
            m = re.search(r"uses:\s*([^\s#]+)", line)
            if not m or m.group(1).startswith("./"):
                continue
            ref = m.group(1).split("@")[1]
            assert re.fullmatch(r"[0-9a-f]{40}", ref), f"{wf.name}: {m.group(1)} is not pinned to a SHA"


def test_workflows_default_to_read_only_permissions():
    for wf in WORKFLOWS:
        assert _load(wf)["permissions"] == {"contents": "read"}, wf.name


def test_privileged_roles_only_used_in_protected_environments():
    for wf in WORKFLOWS:
        doc = _load(wf)
        for name, job in doc["jobs"].items():
            text = yaml.safe_dump(job)
            if any(role in text for role in PRIVILEGED_ROLES):
                assert job.get("environment") in {"dev", "cleanup", "${{ inputs.environment }}"}, f"{wf.name}:{name}"
                assert "pull_request" not in doc["on"], f"{wf.name} exposes a privileged role to pull requests"


def test_no_static_aws_credentials_in_workflows():
    for wf in WORKFLOWS:
        text = wf.read_text()
        assert "aws-access-key-id" not in text and "AWS_SECRET_ACCESS_KEY" not in text, wf.name


def test_checkout_does_not_persist_credentials():
    for wf in WORKFLOWS:
        for job in _load(wf)["jobs"].values():
            for step in job.get("steps", []):
                if str(step.get("uses", "")).startswith("actions/checkout@"):
                    assert step.get("with", {}).get("persist-credentials") is False, wf.name


def test_cleanup_requires_confirmation_phrase():
    doc = _load(ROOT / ".github" / "workflows" / "cleanup.yml")
    assert "inputs.confirm == 'destroy-novabank-dev'" in doc["jobs"]["destroy"]["if"]


def test_apply_verifies_plan_integrity():
    text = (ROOT / ".github" / "workflows" / "terraform-apply.yml").read_text()
    assert "sha256sum -c tfplan.sha256" in text and "planned_commit" in text


def test_every_inline_checkov_skip_is_catalogued():
    catalogue = yaml.safe_load((ROOT / "policies" / "exceptions" / "checkov.yaml").read_text())
    documented = {e["check_id"] for e in catalogue["exceptions"]}
    found = set()
    for tf in (ROOT / "terraform").rglob("*.tf"):
        found |= set(re.findall(r"#checkov:skip=(CKV2?_AWS_\d+):", tf.read_text()))
    assert found <= documented, sorted(found - documented)
    assert all(e.get("reason") and e.get("review_by") for e in catalogue["exceptions"])
