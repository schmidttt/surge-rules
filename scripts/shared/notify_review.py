#!/usr/bin/env python3
"""Send one deduplicated GitHub review notification for a risky rules refresh."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path
from typing import Callable, Dict, List, Mapping, Optional, Sequence, Tuple
from urllib.parse import urlparse


RISK_EVIDENCE_KEYS = {
    "manual_review",
    "new_unresolved_candidates",
    "review",
    "unsupported_omitted",
}
REASON_LABELS = {
    "actual-change-ratio-above-auto-merge-limit": "实际变动率超过自动合并阈值",
    "addition-count-above-auto-merge-limit": "新增规则数量超过自动合并阈值",
    "initial-baseline-requires-review": "首次发布基线需要人工确认",
    "new-unresolved-candidates": "出现新的未决候选",
    "reference-manual-review-increased": "参考源待审核数量增加",
    "reference-manual-review-set-changed": "参考源待审核集合发生变化",
    "rules-removed": "正式规则发生删除",
    "sukka-audit-unavailable": "Sukka 参考审计不可用",
    "sukka-manual-review-set-changed": "Sukka 待审核集合发生变化",
    "sukka-uncovered-count-increased": "Sukka 未覆盖数量增加",
    "sukka-unsupported-types-changed": "Sukka 不支持语法类型发生变化",
    "unsupported-rule-set-changed": "不支持语法集合发生变化",
}
GhRunner = Callable[[Sequence[str], Optional[Mapping[str, object]]], str]


class NotificationError(RuntimeError):
    """Raised when notification inputs or GitHub operations are invalid."""


def parse_pr_url(pr_url: str, expected_repository: str) -> Tuple[str, int]:
    parsed = urlparse(pr_url)
    parts = [part for part in parsed.path.split("/") if part]
    if (
        parsed.scheme != "https"
        or parsed.netloc.lower() != "github.com"
        or len(parts) != 4
        or parts[2] != "pull"
    ):
        raise NotificationError("Invalid GitHub pull request URL: {}".format(pr_url))
    repository = "{}/{}".format(parts[0], parts[1])
    if repository.lower() != expected_repository.lower():
        raise NotificationError(
            "Pull request repository {} does not match {}".format(
                repository, expected_repository
            )
        )
    try:
        number = int(parts[3])
    except ValueError as exc:
        raise NotificationError("Invalid pull request number: {}".format(pr_url)) from exc
    return repository, number


def collect_risk_evidence(
    payload: object,
    prefix: str = "",
) -> Dict[str, object]:
    collected: Dict[str, object] = {}
    if not isinstance(payload, dict):
        return collected
    for key, value in sorted(payload.items()):
        path = "{}.{}".format(prefix, key) if prefix else key
        if key in RISK_EVIDENCE_KEYS:
            collected[path] = value
        else:
            collected.update(collect_risk_evidence(value, path))
    return collected


def notification_fingerprint(
    product: str,
    assessment: Mapping[str, object],
    evidence: Sequence[Mapping[str, object]],
) -> str:
    material = {
        "product": product,
        "assessment": dict(assessment),
        "evidence": [
            collect_risk_evidence(payload) for payload in evidence
        ],
    }
    canonical = json.dumps(
        material,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def manual_review_count(assessment: Mapping[str, object]) -> Optional[int]:
    for key in (
        "new_unresolved_candidate_count",
        "reference_manual_review_count",
        "sukka_uncovered",
        "unresolved_candidate_count",
    ):
        value = assessment.get(key)
        if isinstance(value, int):
            return value
    values = assessment.get("reference_manual_review")
    if isinstance(values, dict):
        counts = [value for value in values.values() if isinstance(value, int)]
        if counts:
            return sum(counts)
    return None


def render_comment(
    product: str,
    reviewer: str,
    assessment: Mapping[str, object],
    fingerprint: str,
    repository: str,
    review_guide: str,
    mention: bool,
) -> str:
    risk_level = str(assessment.get("classification", "high-risk"))
    reasons = assessment.get("reasons")
    reason_values = reasons if isinstance(reasons, list) else []
    reason_lines = [
        "- {}".format(REASON_LABELS.get(str(reason), str(reason)))
        for reason in reason_values
    ]
    if not reason_lines:
        reason_lines = ["- 未提供具体原因，请查看变更报告。"]
    manual_count = manual_review_count(assessment)
    lines = [
        "<!-- surge-rules-review:{}:{} -->".format(product, fingerprint),
        "## Surge 规则需要人工审核",
        "",
    ]
    if mention:
        lines.extend(
            [
                "@{} 待审核内容已经发生变化，请重新查看。".format(reviewer),
                "",
            ]
        )
    lines.extend(
        [
            "- 规则组：`{}`".format(product),
            "- 分类：`{}`".format(risk_level),
            "- 新增：{} 条".format(assessment.get("added_count", "unknown")),
            "- 删除：{} 条".format(assessment.get("removed_count", "unknown")),
        ]
    )
    if manual_count is not None:
        lines.append("- 待审核候选：{} 条".format(manual_count))
    lines.extend(
        [
            "",
            "触发原因：",
            "",
            *reason_lines,
            "",
            "审核指南：[{}](https://github.com/{}/blob/main/{})".format(
                review_guide,
                repository,
                review_guide,
            ),
            "",
            "通知指纹：`{}`".format(fingerprint),
        ]
    )
    return "\n".join(lines)


def run_gh(
    arguments: Sequence[str],
    input_payload: Optional[Mapping[str, object]] = None,
) -> str:
    completed = subprocess.run(
        ["gh", *arguments],
        input=(
            json.dumps(input_payload, ensure_ascii=False)
            if input_payload is not None
            else None
        ),
        text=True,
        capture_output=True,
        check=False,
    )
    if completed.returncode != 0:
        raise NotificationError(
            "GitHub notification command failed: {}".format(
                completed.stderr.strip() or completed.stdout.strip()
            )
        )
    return completed.stdout


def notify(
    repository: str,
    pr_number: int,
    reviewer: str,
    product: str,
    assessment: Mapping[str, object],
    evidence: Sequence[Mapping[str, object]],
    review_guide: str,
    gh_runner: GhRunner = run_gh,
) -> str:
    if assessment.get("classification") not in {"medium-risk", "high-risk"}:
        return "skipped-low-risk"
    fingerprint = notification_fingerprint(product, assessment, evidence)
    marker = "<!-- surge-rules-review:{}:{} -->".format(product, fingerprint)
    comments = gh_runner(
        [
            "api",
            "repos/{}/issues/{}/comments".format(repository, pr_number),
            "--paginate",
            "--jq",
            ".[].body",
        ],
        None,
    )
    if marker in comments:
        return "skipped-duplicate"

    requested_reviewers = {
        line.strip().lower()
        for line in gh_runner(
            [
                "api",
                "repos/{}/pulls/{}/requested_reviewers".format(
                    repository, pr_number
                ),
                "--jq",
                ".users[].login",
            ],
            None,
        ).splitlines()
        if line.strip()
    }
    already_requested = reviewer.lower() in requested_reviewers
    if not already_requested:
        gh_runner(
            [
                "api",
                "--method",
                "POST",
                "repos/{}/pulls/{}/requested_reviewers".format(
                    repository, pr_number
                ),
                "--input",
                "-",
            ],
            {"reviewers": [reviewer]},
        )

    comment = render_comment(
        product,
        reviewer,
        assessment,
        fingerprint,
        repository,
        review_guide,
        mention=already_requested,
    )
    gh_runner(
        [
            "api",
            "--method",
            "POST",
            "repos/{}/issues/{}/comments".format(repository, pr_number),
            "--input",
            "-",
        ],
        {"body": comment},
    )
    return "commented-and-mentioned" if already_requested else "review-requested"


def load_json(path: Path) -> Mapping[str, object]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        raise NotificationError("Could not read JSON file: {}".format(path)) from exc
    if not isinstance(payload, dict):
        raise NotificationError("JSON root must be an object: {}".format(path))
    return payload


def create_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository", required=True)
    parser.add_argument("--pr-url", required=True)
    parser.add_argument("--reviewer", required=True)
    parser.add_argument("--product", required=True)
    parser.add_argument("--assessment", type=Path, required=True)
    parser.add_argument("--evidence", type=Path, action="append", default=[])
    parser.add_argument("--review-guide", required=True)
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = create_parser().parse_args(argv)
    repository, pr_number = parse_pr_url(args.pr_url, args.repository)
    assessment = load_json(args.assessment)
    evidence = [load_json(path) for path in args.evidence]
    result = notify(
        repository,
        pr_number,
        args.reviewer,
        args.product,
        assessment,
        evidence,
        args.review_guide,
    )
    print("Review notification: {}".format(result))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except NotificationError as exc:
        print("error: {}".format(exc), file=sys.stderr)
        raise SystemExit(2)
