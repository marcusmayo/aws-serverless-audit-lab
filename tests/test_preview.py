from __future__ import annotations

import pytest

from preview.app import MAX_TEMPLATE_BYTES, audit_payload


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
