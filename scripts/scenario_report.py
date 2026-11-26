#!/usr/bin/env python3
"""Summarise validation scenarios (T01..T30) from a pytest JUnit report.

Scenario IDs come from ``@pytest.mark.scenario("Txx")`` markers. Only
scenarios with a passing test are reported as verified — and only as
verified *offline/in CI*; live AWS verification is recorded separately in
docs/validation-scenarios.md.
"""

from __future__ import annotations

import ast
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def scenario_map() -> dict[tuple[str, str], str]:
    """(module path, test name) -> scenario id, read from test source."""

    out: dict[tuple[str, str], str] = {}
    for path in (ROOT / "tests").rglob("test_*.py"):
        tree = ast.parse(path.read_text())
        module = ".".join(path.relative_to(ROOT).with_suffix("").parts)
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef):
                for dec in node.decorator_list:
                    if (
                        isinstance(dec, ast.Call)
                        and getattr(dec.func, "attr", "") == "scenario"
                        and dec.args
                        and isinstance(dec.args[0], ast.Constant)
                    ):
                        out[(module, node.name)] = dec.args[0].value
    return out


def main(report: str) -> None:
    mapping = scenario_map()
    results: dict[str, list[bool]] = {}
    for case in ET.parse(report).getroot().iter("testcase"):
        name = case.get("name", "").split("[")[0]
        sid = mapping.get((case.get("classname", ""), name))
        if sid:
            failed = any(child.tag in {"failure", "error", "skipped"} for child in case)
            results.setdefault(sid, []).append(not failed)
    print("## Validation scenarios verified in this run (offline / GitHub CI)\n")
    print("| Scenario | Tests | Result |\n|---|---|---|")
    for sid in sorted(results):
        ok = all(results[sid])
        print(f"| {sid} | {len(results[sid])} | {'PASS' if ok else 'FAIL'} |")
    print(f"\n{sum(all(v) for v in results.values())} scenario(s) passed. Scenarios not listed require live AWS verification.")


if __name__ == "__main__":
    main(sys.argv[1])
