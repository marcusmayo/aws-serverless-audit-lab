from __future__ import annotations

import re

import pytest

from audit.oracle import run_suite
from preview.app import ASSETS, CASE_ROOT, MAX_TEMPLATE_BYTES, audit_payload


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
    assert {"activity", "api-state", "fixture-count", "run-demo"} <= html_ids
