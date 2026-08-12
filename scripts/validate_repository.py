#!/usr/bin/env python3
"""Validate generated lists, repository casing, and published raw paths."""

from __future__ import annotations

import argparse
import hashlib
import ipaddress
import json
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

from shared.reference_verifier import (
    ReferenceVerificationError,
    load_resolution_catalog,
)


EXPECTED_LISTS = {
    "rules/Google/Google.list": 500,
    "rules/GoogleCN/GoogleCN.list": 20,
    "rules/GoogleAI/GoogleAI.list": 30,
    "rules/AI/AI.list": 100,
    "rules/YouTube/YouTube.list": 100,
    "rules/TikTok/TikTok.list": 20,
    "rules/BiliBili/BiliBili.list": 30,
    "rules/Game/Game.list": 150,
    "rules/GameCN/GameCN.list": 20,
    "rules/Emby/Emby.list": 10,
}
EXPECTED_VERIFICATION_REPORTS = (
    "reports/google/google-report.json",
    "reports/google/reference-audit.json",
    "reports/googlecn/googlecn-report.json",
    "reports/ai/ai-report.json",
    "reports/game/game-report.json",
    "reports/youtube/youtube-report.json",
    "reports/youtube/reference-audit.json",
    "reports/tiktok/tiktok-report.json",
    "reports/tiktok/reference-audit.json",
    "reports/bilibili/bilibili-report.json",
    "reports/bilibili/reference-audit.json",
)
TEXT_SUFFIXES = {
    ".md",
    ".py",
    ".yml",
    ".yaml",
    ".list",
    ".txt",
    ".json",
}
RAW_PREFIX = "https://raw.githubusercontent.com/schmidttt/surge-rules/"
LEGACY_REPO_NAME = "Surge" + "-Rules"


class ValidationError(RuntimeError):
    pass


def validate_list(path: Path, minimum: int) -> Tuple[int, List[str]]:
    data = path.read_bytes()
    if data.endswith((b"\n", b"\r")):
        raise ValidationError("{} has a trailing newline".format(path))
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValidationError("{} is not UTF-8".format(path)) from exc
    lines = text.splitlines()
    rules = [line for line in lines if line and not line.startswith("#")]
    if len(rules) < minimum:
        raise ValidationError(
            "{} contains {} rules, below {}".format(path, len(rules), minimum)
        )
    total_lines = [line for line in lines if line.startswith("# TOTAL: ")]
    if total_lines != ["# TOTAL: {}".format(len(rules))]:
        raise ValidationError("{} has an invalid TOTAL header".format(path))
    if len(rules) != len(set(rules)):
        raise ValidationError("{} contains duplicate rules".format(path))
    for line in rules:
        parts = line.split(",")
        rule_type = parts[0]
        if rule_type in {"DOMAIN", "DOMAIN-SUFFIX"}:
            if len(parts) != 2 or not parts[1] or parts[1] != parts[1].lower():
                raise ValidationError("{} has invalid domain rule {!r}".format(path, line))
            continue
        if rule_type == "IP-CIDR":
            if not path.as_posix().endswith("/rules/Emby/Emby.list"):
                raise ValidationError(
                    "{} must not contain IP-CIDR rules".format(path)
                )
            if len(parts) != 2:
                raise ValidationError("{} has invalid IP rule {!r}".format(path, line))
            try:
                network = ipaddress.ip_network(parts[1], strict=True)
            except ValueError as exc:
                raise ValidationError(
                    "{} has invalid IP network {!r}".format(path, line)
                ) from exc
            if network.version != 4:
                raise ValidationError("{} has non-IPv4 IP-CIDR {!r}".format(path, line))
            continue
        raise ValidationError("{} has invalid rule {!r}".format(path, line))
    return len(rules), rules


def validate_lowercase_repository_name(project_root: Path) -> None:
    findings: List[str] = []
    for path in sorted(project_root.rglob("*")):
        if (
            not path.is_file()
            or ".git" in path.parts
            or path.suffix not in TEXT_SUFFIXES
        ):
            continue
        text = path.read_text(encoding="utf-8")
        if LEGACY_REPO_NAME in text:
            findings.append(str(path.relative_to(project_root)))
    if findings:
        raise ValidationError(
            "Legacy repository casing remains in: {}".format(findings)
        )


def validate_raw_links(project_root: Path) -> None:
    readme = (project_root / "README.md").read_text(encoding="utf-8")
    paths = set(
        re.findall(
            re.escape(RAW_PREFIX) + r"main/(rules/[A-Za-z0-9/_-]+\.list)",
            readme,
        )
    )
    expected = set(EXPECTED_LISTS)
    missing_links = sorted(expected.difference(paths))
    invalid_paths = sorted(path for path in paths if not (project_root / path).is_file())
    if missing_links:
        raise ValidationError(
            "README is missing raw links for: {}".format(missing_links)
        )
    if invalid_paths:
        raise ValidationError(
            "README raw links do not map to local files: {}".format(invalid_paths)
        )


def validate_cross_outputs(all_rules: Dict[str, List[str]]) -> None:
    game = set(all_rules["rules/Game/Game.list"])
    game_cn = set(all_rules["rules/GameCN/GameCN.list"])
    duplicates = sorted(game.intersection(game_cn))
    if duplicates:
        raise ValidationError(
            "Game and GameCN contain exact duplicates: {}".format(duplicates)
        )
    google_cn = all_rules["rules/GoogleCN/GoogleCN.list"]
    forbidden = [
        rule
        for rule in google_cn
        if any(
            marker in rule
            for marker in (
                "analytics",
                "doubleclick",
                "mtalk",
                "tagmanager",
                "tagservices",
            )
        )
    ]
    if forbidden:
        raise ValidationError(
            "GoogleCN contains a hard-excluded service: {}".format(forbidden)
        )

    def parsed(rule: str) -> Tuple[str, str]:
        rule_type, domain = rule.split(",", 1)
        return rule_type, domain

    def covers(left: str, right: str) -> bool:
        left_type, left_domain = parsed(left)
        right_type, right_domain = parsed(right)
        if left_type == "DOMAIN":
            return right_type == "DOMAIN" and left_domain == right_domain
        return (
            right_domain == left_domain
            or right_domain.endswith("." + left_domain)
        )

    def overlap(left: str, right: str) -> bool:
        return covers(left, right) or covers(right, left)

    google_ai = all_rules["rules/GoogleAI/GoogleAI.list"]
    ai = all_rules["rules/AI/AI.list"]
    ai_cross = sorted(
        "{} <> {}".format(left, right)
        for left in google_ai
        for right in ai
        if overlap(left, right)
    )
    if ai_cross:
        raise ValidationError(
            "GoogleAI and AI overlap: {}".format(ai_cross[:10])
        )

    google = all_rules["rules/Google/Google.list"]
    google_leaks = sorted(
        rule
        for rule in ai
        if any(overlap(rule, google_rule) for google_rule in google)
    )
    if google_leaks:
        raise ValidationError(
            "AI contains Google-owned coverage: {}".format(google_leaks[:10])
        )

    required = {
        "rules/GoogleAI/GoogleAI.list": {
            "DOMAIN-SUFFIX,gemini.google.com",
            "DOMAIN-SUFFIX,deepmind.com",
            "DOMAIN-SUFFIX,generativelanguage.googleapis.com",
        },
        "rules/AI/AI.list": {
            "DOMAIN-SUFFIX,openai.com",
            "DOMAIN-SUFFIX,chatgpt.com",
            "DOMAIN-SUFFIX,anthropic.com",
            "DOMAIN-SUFFIX,claude.ai",
            "DOMAIN-SUFFIX,perplexity.ai",
        },
    }
    for path, core_rules in required.items():
        missing = sorted(core_rules.difference(all_rules[path]))
        if missing:
            raise ValidationError(
                "{} is missing core rules: {}".format(path, missing)
            )


def validate_verification_reports(project_root: Path) -> None:
    def validate_block(path: str, block: object, label: str) -> None:
        if not isinstance(block, dict):
            raise ValidationError("{} is missing {}".format(path, label))
        try:
            schema = block["schema_version"]
            automatic = int(block["auto_resolved_count"])
            manual_count = int(block["manual_review_count"])
            fingerprint = block["manual_review_fingerprint"]
            manual = block["manual_review"]
        except (KeyError, TypeError, ValueError) as exc:
            raise ValidationError(
                "{} has an invalid {} block".format(path, label)
            ) from exc
        if schema != 1 or automatic < 0 or manual_count < 0:
            raise ValidationError(
                "{} has invalid {} counts".format(path, label)
            )
        if not isinstance(manual, list) or len(manual) != manual_count:
            raise ValidationError(
                "{} has mismatched {} manual entries".format(path, label)
            )
        try:
            manual_identities = [str(item["identity"]) for item in manual]
        except (KeyError, TypeError) as exc:
            raise ValidationError(
                "{} has invalid {} manual entries".format(path, label)
            ) from exc
        if len(set(manual_identities)) != len(manual_identities):
            raise ValidationError(
                "{} has duplicate {} manual entries".format(path, label)
            )
        expected_fingerprint = hashlib.sha256(
            "\n".join(sorted(manual_identities)).encode("utf-8")
        ).hexdigest()
        if not isinstance(fingerprint, str) or not re.fullmatch(
            r"[0-9a-f]{64}",
            fingerprint,
        ):
            raise ValidationError(
                "{} has invalid {} fingerprint".format(path, label)
            )
        if fingerprint != expected_fingerprint:
            raise ValidationError(
                "{} has stale {} fingerprint".format(path, label)
            )
        automatic_counts = block.get("automatic_decision_counts")
        if isinstance(automatic_counts, dict):
            try:
                decision_total = sum(
                    int(value) for value in automatic_counts.values()
                )
            except (TypeError, ValueError) as exc:
                raise ValidationError(
                    "{} has invalid {} automatic counts".format(path, label)
                ) from exc
            if decision_total != automatic:
                raise ValidationError(
                    "{} has mismatched {} automatic counts".format(path, label)
                )
        reference_total = block.get("reference_rule_count")
        if isinstance(reference_total, int) and (
            automatic + manual_count != reference_total
        ):
            raise ValidationError(
                "{} has mismatched {} reference total".format(path, label)
            )

    for relative in EXPECTED_VERIFICATION_REPORTS:
        path = project_root / relative
        if not path.is_file():
            raise ValidationError(
                "Missing verification report: {}".format(relative)
            )
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            raise ValidationError(
                "Invalid verification report JSON: {}".format(relative)
            ) from exc
        validate_block(relative, payload.get("verification"), "verification")
        if relative == "reports/ai/ai-report.json":
            sukka = payload.get("sukka_audit")
            if not isinstance(sukka, dict):
                raise ValidationError("{} is missing Sukka audit".format(relative))
            validate_block(
                relative,
                sukka.get("verification"),
                "Sukka verification",
            )
    try:
        load_resolution_catalog(
            project_root / "references/verification/reference-decisions.json",
            "google",
        )
    except ReferenceVerificationError as exc:
        raise ValidationError(str(exc)) from exc


def check_remote_ref(project_root: Path, ref: str) -> None:
    for relative in EXPECTED_LISTS:
        url = "{}{}/{}".format(RAW_PREFIX, ref, relative)
        request = urllib.request.Request(
            url, headers={"User-Agent": "schmidttt-surge-rules-validator/0.2"}
        )
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                remote = response.read()
        except (urllib.error.URLError, TimeoutError) as exc:
            raise ValidationError("Could not fetch {}: {}".format(url, exc)) from exc
        local = (project_root / relative).read_bytes()
        if remote != local:
            raise ValidationError("Remote raw content differs: {}".format(relative))


def create_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--project-root",
        type=Path,
        default=Path(__file__).resolve().parents[1],
    )
    parser.add_argument(
        "--check-remote-ref",
        help="Fetch every raw list at this branch or commit and compare bytes",
    )
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = create_parser().parse_args(argv)
    project_root = args.project_root.resolve()
    all_rules: Dict[str, List[str]] = {}
    counts: Dict[str, int] = {}
    for relative, minimum in EXPECTED_LISTS.items():
        path = project_root / relative
        if not path.is_file():
            raise ValidationError("Missing generated list: {}".format(relative))
        count, rules = validate_list(path, minimum)
        counts[relative] = count
        all_rules[relative] = rules
    validate_lowercase_repository_name(project_root)
    validate_raw_links(project_root)
    validate_cross_outputs(all_rules)
    validate_verification_reports(project_root)
    if args.check_remote_ref:
        check_remote_ref(project_root, args.check_remote_ref)
    print(
        "Repository validation passed: {}".format(
            ", ".join(
                "{}={}".format(Path(path).name, count)
                for path, count in counts.items()
            )
        )
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except ValidationError as exc:
        print("error: {}".format(exc), file=sys.stderr)
        raise SystemExit(2)
