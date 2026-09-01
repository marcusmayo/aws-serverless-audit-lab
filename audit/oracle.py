from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from typing import Any

import yaml

from .audit_template import audit_text

ORACLE_SCHEMA_VERSION = "1.0.0"
RULE_ID = re.compile(r"^[A-Z][A-Z0-9]{1,11}\d{3}$")
DEFAULT_CASE_ROOT = Path(__file__).parents[1] / "task_cases"
MAX_CASE_BYTES = 512 * 1024
EXPECTED_TOP_LEVEL = {"schema_version", "case_id", "title", "expect", "context"}
EXPECT_KEYS = {
    "decision",
    "required_findings",
    "forbidden_rule_ids",
    "evidence_boundary",
}
FINDING_KEYS = {"rule_id", "severity", "path"}
DECISIONS = {"PASS", "PASS_WITH_NOTES", "FAIL"}
SEVERITIES = {"CRITICAL", "HIGH", "MEDIUM", "LOW", "INFO"}


class OracleDefinitionError(ValueError):
    """Raised when trusted oracle data is incomplete or malformed."""


class UniqueKeyLoader(yaml.SafeLoader):
    """Safe YAML loader that rejects duplicate keys in trusted manifests."""


def _construct_unique_mapping(
    loader: UniqueKeyLoader, node: yaml.MappingNode, deep: bool = False
) -> dict[Any, Any]:
    mapping: dict[Any, Any] = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        if key in mapping:
            raise OracleDefinitionError(f"duplicate YAML key: {key}")
        mapping[key] = loader.construct_object(value_node, deep=deep)
    return mapping


UniqueKeyLoader.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG,
    _construct_unique_mapping,
)


def _load_manifest(path: Path) -> tuple[dict[str, Any], str]:
    try:
        raw = path.read_text(encoding="utf-8")
        loader = UniqueKeyLoader(raw)
        try:
            document = loader.get_single_data()
        finally:
            loader.dispose()
    except OracleDefinitionError:
        raise
    except (OSError, yaml.YAMLError) as exc:
        raise OracleDefinitionError(f"could not load {path.name}: {type(exc).__name__}") from exc
    if not isinstance(document, dict):
        raise OracleDefinitionError(f"{path.name} must contain a YAML mapping")
    return document, hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _reject_unknown(actual: set[str], allowed: set[str], label: str) -> None:
    unknown = actual - allowed
    if unknown:
        raise OracleDefinitionError(f"{label} contains unknown keys: {sorted(unknown)}")


def _validate_manifest(manifest: dict[str, Any], case_id: str) -> None:
    if any(not isinstance(key, str) for key in manifest):
        raise OracleDefinitionError(f"{case_id}: manifest keys must be strings")
    _reject_unknown(set(manifest), EXPECTED_TOP_LEVEL, f"{case_id}: manifest")
    required_top_level = EXPECTED_TOP_LEVEL - {"context"}
    missing_top_level = required_top_level - set(manifest)
    if missing_top_level:
        raise OracleDefinitionError(
            f"{case_id}: manifest is missing keys: {sorted(missing_top_level)}"
        )
    if manifest["schema_version"] != ORACLE_SCHEMA_VERSION:
        raise OracleDefinitionError(f"{case_id}: unsupported oracle schema_version")
    if manifest["case_id"] != case_id:
        raise OracleDefinitionError(f"{case_id}: manifest case_id does not match directory")
    if not isinstance(manifest["title"], str) or not manifest["title"].strip():
        raise OracleDefinitionError(f"{case_id}: title must be a non-empty string")
    if "context" in manifest and not isinstance(manifest["context"], dict):
        raise OracleDefinitionError(f"{case_id}: context must be a mapping")

    expect = manifest["expect"]
    if not isinstance(expect, dict) or any(not isinstance(key, str) for key in expect):
        raise OracleDefinitionError(f"{case_id}: expect must be a string-keyed mapping")
    _reject_unknown(set(expect), EXPECT_KEYS, f"{case_id}: expect")
    if set(expect) != EXPECT_KEYS:
        raise OracleDefinitionError(
            f"{case_id}: expect is missing keys: {sorted(EXPECT_KEYS - set(expect))}"
        )
    if expect["decision"] not in DECISIONS:
        raise OracleDefinitionError(f"{case_id}: expected decision is invalid")

    required_findings = expect["required_findings"]
    if not isinstance(required_findings, list):
        raise OracleDefinitionError(f"{case_id}: required_findings must be a list")
    identities: set[tuple[str, str, str]] = set()
    for index, finding in enumerate(required_findings):
        if not isinstance(finding, dict) or any(not isinstance(key, str) for key in finding):
            raise OracleDefinitionError(f"{case_id}: required_findings[{index}] must be a mapping")
        _reject_unknown(set(finding), FINDING_KEYS, f"{case_id}: required_findings[{index}]")
        if set(finding) != FINDING_KEYS:
            raise OracleDefinitionError(
                f"{case_id}: required_findings[{index}] must define rule_id, severity, and path"
            )
        rule_id = finding["rule_id"]
        severity = finding["severity"]
        path = finding["path"]
        if not isinstance(rule_id, str) or not RULE_ID.fullmatch(rule_id):
            raise OracleDefinitionError(f"{case_id}: required finding rule_id is invalid")
        if severity not in SEVERITIES:
            raise OracleDefinitionError(f"{case_id}: required finding severity is invalid")
        if not isinstance(path, str) or not path:
            raise OracleDefinitionError(f"{case_id}: required finding path is invalid")
        identity = (rule_id, severity, path)
        if identity in identities:
            raise OracleDefinitionError(f"{case_id}: required_findings contains duplicates")
        identities.add(identity)

    forbidden = expect["forbidden_rule_ids"]
    if not isinstance(forbidden, list) or any(
        not isinstance(rule_id, str) or not RULE_ID.fullmatch(rule_id) for rule_id in forbidden
    ):
        raise OracleDefinitionError(f"{case_id}: forbidden_rule_ids must be valid rule IDs")
    if len(set(forbidden)) != len(forbidden):
        raise OracleDefinitionError(f"{case_id}: forbidden_rule_ids contains duplicates")

    boundary = expect["evidence_boundary"]
    if not isinstance(boundary, dict) or any(
        not isinstance(key, str) or not isinstance(value, str) for key, value in boundary.items()
    ):
        raise OracleDefinitionError(f"{case_id}: evidence_boundary must be a string mapping")


def evaluate_report(report: dict[str, Any], expect: dict[str, Any]) -> dict[str, Any]:
    """Compare output with trusted expectations without reusing audit rule logic."""
    observed_findings = [
        finding for finding in report.get("findings", []) if isinstance(finding, dict)
    ]
    observed_rule_ids = {
        finding.get("rule_id")
        for finding in observed_findings
        if isinstance(finding.get("rule_id"), str)
    }
    checks: list[dict[str, Any]] = []

    checks.append(
        {
            "check_id": "decision",
            "status": "MATCH" if report.get("decision") == expect["decision"] else "MISMATCH",
            "expected": expect["decision"],
            "observed": report.get("decision"),
        }
    )

    missing_findings = []
    for required in expect["required_findings"]:
        matched = any(
            all(finding.get(key) == required[key] for key in FINDING_KEYS)
            for finding in observed_findings
        )
        if not matched:
            missing_findings.append(required)
    checks.append(
        {
            "check_id": "required_findings",
            "status": "MATCH" if not missing_findings else "MISMATCH",
            "expected": expect["required_findings"],
            "observed_rule_ids": sorted(observed_rule_ids),
            "missing": missing_findings,
        }
    )

    forbidden_observed = sorted(set(expect["forbidden_rule_ids"]) & observed_rule_ids)
    checks.append(
        {
            "check_id": "forbidden_rule_ids",
            "status": "MATCH" if not forbidden_observed else "MISMATCH",
            "expected": expect["forbidden_rule_ids"],
            "observed": forbidden_observed,
        }
    )

    observed_boundary = report.get("evidence_boundary", {})
    boundary_mismatches = {
        key: {"expected": value, "observed": observed_boundary.get(key)}
        for key, value in expect["evidence_boundary"].items()
        if observed_boundary.get(key) != value
    }
    checks.append(
        {
            "check_id": "evidence_boundary",
            "status": "MATCH" if not boundary_mismatches else "MISMATCH",
            "expected": expect["evidence_boundary"],
            "observed": observed_boundary,
            "mismatches": boundary_mismatches,
        }
    )

    matched_count = sum(check["status"] == "MATCH" for check in checks)
    return {
        "schema_version": ORACLE_SCHEMA_VERSION,
        "verdict": "MATCH" if matched_count == len(checks) else "MISMATCH",
        "summary": {"matched": matched_count, "total": len(checks)},
        "checks": checks,
    }


def run_case(case_dir: Path, case_root: Path) -> dict[str, Any]:
    resolved_root = case_root.resolve()
    resolved_case = case_dir.resolve()
    if not resolved_case.is_relative_to(resolved_root) or not resolved_case.is_dir():
        raise OracleDefinitionError("oracle case must be a directory inside task_cases")

    template_path = resolved_case / "template.yaml"
    manifest_path = resolved_case / "expected.yaml"
    prompt_path = resolved_case / "prompt.md"
    if not all(
        path.is_file() and not path.is_symlink()
        for path in (template_path, manifest_path, prompt_path)
    ):
        raise OracleDefinitionError(f"{case_dir.name}: template, expected, and prompt are required")

    template = template_path.read_text(encoding="utf-8")
    if len(template.encode("utf-8")) > MAX_CASE_BYTES:
        raise OracleDefinitionError(f"{case_dir.name}: template exceeds 512 KiB")
    manifest, manifest_sha256 = _load_manifest(manifest_path)
    _validate_manifest(manifest, case_dir.name)
    report = audit_text(
        template,
        source=f"task_cases/{case_dir.name}/template.yaml",
        base_dir=resolved_case,
    )
    return {
        "case_id": case_dir.name,
        "title": manifest["title"],
        "manifest_sha256": manifest_sha256,
        "context": manifest.get("context", {}),
        "report": report,
        "oracle": evaluate_report(report, manifest["expect"]),
    }


def _run_all(case_root: Path) -> list[dict[str, Any]]:
    if not case_root.is_dir():
        raise OracleDefinitionError("task_cases directory is unavailable")
    results = [
        run_case(case_dir, case_root)
        for case_dir in sorted(path for path in case_root.iterdir() if path.is_dir())
    ]
    if not results:
        raise OracleDefinitionError("no oracle cases were found")
    return results


def list_cases(case_root: Path = DEFAULT_CASE_ROOT) -> list[dict[str, Any]]:
    results = _run_all(case_root)
    return [
        {
            "case_id": result["case_id"],
            "title": result["title"],
            "manifest_sha256": result["manifest_sha256"],
        }
        for result in results
    ]


def run_suite(case_root: Path = DEFAULT_CASE_ROOT) -> dict[str, Any]:
    results = _run_all(case_root)
    matched_count = sum(result["oracle"]["verdict"] == "MATCH" for result in results)
    return {
        "schema_version": ORACLE_SCHEMA_VERSION,
        "verdict": "MATCH" if matched_count == len(results) else "MISMATCH",
        "case_count": len(results),
        "matched_count": matched_count,
        "cases": results,
        "evidence_boundary": {
            "oracle": "DETERMINISTIC_LOCAL",
            "localstack_iam": "UNVERIFIED",
            "real_aws": "NOT_RUN",
        },
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the deterministic audit regression oracle")
    parser.add_argument("--case-root", type=Path, default=DEFAULT_CASE_ROOT)
    parser.add_argument("--format", choices=("summary", "json"), default="summary")
    args = parser.parse_args(argv)
    try:
        suite = run_suite(args.case_root)
    except OracleDefinitionError as exc:
        print(f"ORACLE ERROR: {exc}")
        return 2
    if args.format == "json":
        print(json.dumps(suite, indent=2, sort_keys=True))
    else:
        print(
            f"ORACLE {suite['verdict']}: "
            f"{suite['matched_count']}/{suite['case_count']} cases matched expected evidence"
        )
        for result in suite["cases"]:
            print(f"- {result['case_id']}: {result['oracle']['verdict']} — {result['title']}")
    return 0 if suite["verdict"] == "MATCH" else 1


if __name__ == "__main__":
    raise SystemExit(main())
