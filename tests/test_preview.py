from __future__ import annotations

import hashlib
import json
import re

import pytest
import yaml

from audit.oracle import run_suite
from preview.app import ASSETS, CASE_ROOT, MAX_TEMPLATE_BYTES, audit_payload, demo_payload


def _finding_identity(finding: dict[str, str]) -> tuple[str, str, str]:
    return finding["rule_id"], finding["severity"], finding["path"]


def test_preview_audits_template_without_deploying() -> None:
    report = audit_payload(
        {
            "source": "browser.yaml",
            "template": "Resources:\n  Api:\n    Type: AWS::Serverless::HttpApi\n    Properties: {}\n",
        }
    )

    assert report["source"] == "browser.yaml"
    assert report["evidence_boundary"]["real_aws"] == "NOT_RUN"
    assert any(finding["rule_id"] == "API001" for finding in report["findings"])


@pytest.mark.parametrize(
    "payload",
    [None, {}, {"template": ""}, {"template": "Resources: {}", "source": 7}],
)
def test_preview_rejects_invalid_payload(payload: object) -> None:
    with pytest.raises(ValueError):
        audit_payload(payload)


def test_preview_enforces_size_limit() -> None:
    with pytest.raises(ValueError, match="512 KiB"):
        audit_payload({"template": "x" * (MAX_TEMPLATE_BYTES + 1)})


def test_preview_oracle_uses_repository_owned_cases() -> None:
    suite = run_suite(CASE_ROOT)

    assert suite["verdict"] == "MATCH"
    assert suite["matched_count"] == 3
    assert suite["case_count"] == 3
    assert all(case["oracle"]["summary"] == {"matched": 4, "total": 4} for case in suite["cases"])


def test_portfolio_demo_matches_its_exact_repository_owned_contract() -> None:
    preview_dir = CASE_ROOT.parent / "preview"
    expected = yaml.safe_load((preview_dir / "demo" / "expected.yaml").read_text(encoding="utf-8"))
    payload = demo_payload()
    report = payload["report"]

    assert payload["source"] == expected["source"]
    assert payload["template"] == (preview_dir / "demo" / "template.yaml").read_text(encoding="utf-8")
    assert report["decision"] == expected["expect"]["decision"]
    assert report["score"] == expected["expect"]["score"]
    assert report["finding_count"] == expected["expect"]["finding_count"]
    assert report["evidence_boundary"] == expected["expect"]["evidence_boundary"]
    assert [_finding_identity(finding) for finding in report["findings"]] == [
        _finding_identity(finding) for finding in expected["expect"]["findings"]
    ]


def test_t03_drill_down_matches_the_supplied_screenshot_state() -> None:
    suite = run_suite(CASE_ROOT)
    case = next(item for item in suite["cases"] if item["case_id"] == "T03_local_green_cloud_red")
    report = case["report"]

    assert (report["decision"], report["score"], report["finding_count"]) == ("FAIL", 71, 3)
    assert [finding["rule_id"] for finding in report["findings"]] == [
        "API001",
        "COST001",
        "OBS001",
    ]
    assert report["evidence_boundary"] == {
        "static": "VERIFIED",
        "localstack_iam": "UNVERIFIED",
        "real_aws": "NOT_RUN",
    }


def test_github_screenshot_has_machine_checked_provenance() -> None:
    docs_dir = CASE_ROOT.parent / "docs"
    evidence = json.loads(
        (docs_dir / "browser-preview-evidence.json").read_text(encoding="utf-8")
    )
    screenshot = docs_dir / evidence["screenshot"]
    assert screenshot.read_bytes().startswith(b"\x89PNG\r\n\x1a\n")
    assert hashlib.sha256(screenshot.read_bytes()).hexdigest() == evidence["screenshot_sha256"]

    suite = run_suite(CASE_ROOT)
    case = next(item for item in suite["cases"] if item["report"]["source"] == evidence["report_source"])
    report = case["report"]
    assert report["decision"] == evidence["report"]["decision"]
    assert report["score"] == evidence["report"]["score"]
    assert report["finding_count"] == evidence["report"]["finding_count"]
    assert [finding["rule_id"] for finding in report["findings"]] == evidence["report"]["rule_ids"]
    assert report["evidence_boundary"] == evidence["report"]["evidence_boundary"]
    assert suite["verdict"] == evidence["oracle"]["verdict"]
    assert suite["matched_count"] == evidence["oracle"]["matched_count"]
    assert suite["case_count"] == evidence["oracle"]["case_count"]
    assert all(
        item["oracle"]["summary"]["total"] == evidence["oracle"]["checks_per_case"]
        for item in suite["cases"]
    )


def test_visible_preview_assets_are_registered_and_nonempty() -> None:
    assert set(ASSETS) == {"/", "/app.js", "/styles.css"}
    for filename, _content_type in ASSETS.values():
        assert (CASE_ROOT.parent / "preview" / filename).read_text(encoding="utf-8").strip()


def test_browser_script_targets_controls_rendered_by_the_frontend() -> None:
    preview_dir = CASE_ROOT.parent / "preview"
    html = (preview_dir / "index.html").read_text(encoding="utf-8")
    javascript = (preview_dir / "app.js").read_text(encoding="utf-8")
    html_ids = set(re.findall(r'id="([^"]+)"', html))
    script_ids = set(re.findall(r'querySelector\("#([^"]+)"\)', javascript))

    assert script_ids <= html_ids
    assert {"activity", "api-state", "fixture-count", "report-context", "run-demo"} <= html_ids
    assert "SUBMITTED TEMPLATE" in javascript
    assert "ORACLE FIXTURE" in javascript
    assert "EDITOR INPUT UNCHANGED" in javascript
