from __future__ import annotations

from pathlib import Path

import pytest

from audit.oracle import (
    OracleDefinitionError,
    evaluate_report,
    list_cases,
    main,
    run_case,
    run_suite,
)

ROOT = Path(__file__).parents[1]
BOUNDARY = {
    "static": "VERIFIED",
    "localstack_iam": "UNVERIFIED",
    "real_aws": "NOT_RUN",
}


def _expect(required: list[dict[str, str]] | None = None) -> dict:
    return {
        "decision": "FAIL",
        "required_findings": required or [],
        "forbidden_rule_ids": [],
        "evidence_boundary": BOUNDARY,
    }


def test_full_oracle_suite_matches_trusted_expectations() -> None:
    suite = run_suite(ROOT / "task_cases")

    assert suite["verdict"] == "MATCH"
    assert suite["matched_count"] == suite["case_count"] == 3
    assert suite["evidence_boundary"]["real_aws"] == "NOT_RUN"
    assert all(case["oracle"]["verdict"] == "MATCH" for case in suite["cases"])
    assert all("template" not in case for case in suite["cases"])


def test_oracle_case_catalog_does_not_expose_reports_or_templates() -> None:
    cases = list_cases(ROOT / "task_cases")

    assert [case["case_id"] for case in cases] == [
        "T01_iam_secret",
        "T02_retry_semantics",
        "T03_local_green_cloud_red",
    ]
    assert all("template" not in case and "report" not in case for case in cases)
    assert all(len(case["manifest_sha256"]) == 64 for case in cases)


def test_oracle_mismatches_on_wrong_decision_missing_finding_and_boundary() -> None:
    required = [
        {"rule_id": "IAM001", "severity": "CRITICAL", "path": "Resources.Role"}
    ]
    result = evaluate_report(
        {"decision": "PASS", "findings": [], "evidence_boundary": {}},
        _expect(required),
    )

    assert result["verdict"] == "MISMATCH"
    assert {
        check["check_id"]
        for check in result["checks"]
        if check["status"] == "MISMATCH"
    } == {"decision", "required_findings", "evidence_boundary"}


def test_additional_findings_do_not_weaken_oracle() -> None:
    required = [
        {"rule_id": "IAM001", "severity": "CRITICAL", "path": "Resources.Role"}
    ]
    result = evaluate_report(
        {
            "decision": "FAIL",
            "findings": [
                required[0],
                {"rule_id": "SEC001", "severity": "CRITICAL", "path": "Parameters.Key"},
            ],
            "evidence_boundary": BOUNDARY,
        },
        _expect(required),
    )

    assert result["verdict"] == "MATCH"


def test_forbidden_rule_and_wrong_required_severity_mismatch() -> None:
    required = [{"rule_id": "IAM001", "severity": "HIGH", "path": "Resources.Role"}]
    expect = _expect(required)
    expect["forbidden_rule_ids"] = ["SEC001"]
    result = evaluate_report(
        {
            "decision": "FAIL",
            "findings": [
                {"rule_id": "IAM001", "severity": "CRITICAL", "path": "Resources.Role"},
                {"rule_id": "SEC001", "severity": "CRITICAL", "path": "Parameters.Key"},
            ],
            "evidence_boundary": BOUNDARY,
        },
        expect,
    )

    assert result["verdict"] == "MISMATCH"
    assert result["checks"][1]["missing"] == required
    assert result["checks"][2]["observed"] == ["SEC001"]


def test_oracle_rejects_case_outside_trusted_root(tmp_path: Path) -> None:
    with pytest.raises(OracleDefinitionError, match="inside task_cases"):
        run_case(tmp_path, ROOT / "task_cases")


def test_oracle_rejects_unknown_manifest_key(tmp_path: Path) -> None:
    case_root = tmp_path / "task_cases"
    case = case_root / "bad_case"
    case.mkdir(parents=True)
    (case / "template.yaml").write_text("Resources: {}\n", encoding="utf-8")
    (case / "prompt.md").write_text("# Bad case\n", encoding="utf-8")
    (case / "expected.yaml").write_text(
        """schema_version: "1.0.0"
case_id: bad_case
title: Bad case
expect:
  decision: FAIL
  required_findings: []
  forbidden_rule_ids: []
  evidence_boundary: {}
  ignored_key: true
""",
        encoding="utf-8",
    )

    with pytest.raises(OracleDefinitionError, match="unknown keys"):
        run_suite(case_root)


def test_oracle_rejects_duplicate_yaml_key(tmp_path: Path) -> None:
    case_root = tmp_path / "task_cases"
    case = case_root / "duplicate_case"
    case.mkdir(parents=True)
    (case / "template.yaml").write_text("Resources: {}\n", encoding="utf-8")
    (case / "prompt.md").write_text("# Duplicate case\n", encoding="utf-8")
    (case / "expected.yaml").write_text(
        "schema_version: '1.0.0'\nschema_version: '1.0.0'\n",
        encoding="utf-8",
    )

    with pytest.raises(OracleDefinitionError, match="duplicate YAML key"):
        run_suite(case_root)


def test_oracle_is_byte_deterministic() -> None:
    assert run_suite(ROOT / "task_cases") == run_suite(ROOT / "task_cases")


def test_oracle_cli_summary(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["--case-root", str(ROOT / "task_cases")]) == 0
    assert "ORACLE MATCH: 3/3" in capsys.readouterr().out
