from __future__ import annotations

import pytest

from audit.oracle import run_suite
from preview.app import CASE_ROOT, MAX_TEMPLATE_BYTES, audit_payload


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
