#!/usr/bin/env python3
"""Normalize rule refresh assessments into low, medium, or high risk."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Mapping, Optional, Sequence


MEDIUM_RISK_REASONS = {
    "actual-change-ratio-above-auto-merge-limit",
    "addition-count-above-auto-merge-limit",
    "new-unresolved-candidates",
    "reference-manual-review-increased",
    "sukka-audit-unavailable",
    "sukka-uncovered-count-increased",
}
HIGH_RISK_REASONS = {
    "initial-baseline-requires-review",
    "reference-manual-review-set-changed",
    "rules-removed",
    "sukka-manual-review-set-changed",
    "sukka-unsupported-types-changed",
    "unsupported-rule-set-changed",
}
VALID_RISK_LEVELS = {"low-risk", "medium-risk", "high-risk"}


class RiskPolicyError(RuntimeError):
    """Raised when an assessment is malformed or internally inconsistent."""


def classify_reasons(reasons: object) -> str:
    if not isinstance(reasons, list) or any(not isinstance(item, str) for item in reasons):
        raise RiskPolicyError("assessment reasons must be a list of strings")
    if not reasons:
        return "low-risk"
    reason_set = set(reasons)
    unknown = reason_set - MEDIUM_RISK_REASONS - HIGH_RISK_REASONS
    if unknown or reason_set & HIGH_RISK_REASONS:
        return "high-risk"
    return "medium-risk"


def normalize_assessment(assessment: Mapping[str, object]) -> dict[str, object]:
    normalized = dict(assessment)
    level = classify_reasons(normalized.get("reasons"))
    eligible = normalized.get("auto_merge_eligible")
    if not isinstance(eligible, bool):
        raise RiskPolicyError("auto_merge_eligible must be a boolean")
    if eligible != (level == "low-risk"):
        raise RiskPolicyError(
            "auto_merge_eligible contradicts the computed risk level"
        )
    normalized["classification"] = level
    normalized["risk_level"] = level
    normalized["schema_version"] = max(int(normalized.get("schema_version", 1)), 2)
    return normalized


def normalize_file(path: Path) -> str:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        raise RiskPolicyError("could not read assessment: {}".format(path)) from exc
    if not isinstance(payload, dict):
        raise RiskPolicyError("assessment root must be an object")
    normalized = normalize_assessment(payload)
    path.write_text(
        json.dumps(normalized, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return str(normalized["risk_level"])


def create_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--assessment", type=Path, required=True)
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = create_parser().parse_args(argv)
    print("Risk classification: {}".format(normalize_file(args.assessment)))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except RiskPolicyError as exc:
        print("error: {}".format(exc))
        raise SystemExit(2)
