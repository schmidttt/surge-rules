#!/usr/bin/env python3
"""Validate an exact low-risk PR head through Actions, then merge it."""

from __future__ import annotations

import argparse
import json
import subprocess
import time
from pathlib import Path
from typing import Callable, Mapping, Optional, Sequence
from urllib.parse import urlparse


GhRunner = Callable[[Sequence[str]], str]
Sleeper = Callable[[float], None]


class AutoMergeError(RuntimeError):
    """Raised when a PR cannot be proven safe to merge."""


def run_gh(arguments: Sequence[str]) -> str:
    completed = subprocess.run(
        ["gh", *arguments], text=True, capture_output=True, check=False
    )
    if completed.returncode != 0:
        raise AutoMergeError(
            "GitHub command failed: {}".format(
                completed.stderr.strip() or completed.stdout.strip()
            )
        )
    return completed.stdout


def load_assessment(path: Path) -> Mapping[str, object]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        raise AutoMergeError("could not read assessment: {}".format(path)) from exc
    if not isinstance(payload, dict):
        raise AutoMergeError("assessment root must be an object")
    if payload.get("classification") != "low-risk":
        raise AutoMergeError("only low-risk assessments may be auto-merged")
    if payload.get("auto_merge_eligible") is not True:
        raise AutoMergeError("assessment is not eligible for auto-merge")
    if payload.get("reasons") != []:
        raise AutoMergeError("low-risk assessment must not contain review reasons")
    return payload


def parse_pr_url(pr_url: str, repository: str) -> int:
    parsed = urlparse(pr_url)
    parts = [part for part in parsed.path.split("/") if part]
    if (
        parsed.scheme != "https"
        or parsed.netloc.lower() != "github.com"
        or len(parts) != 4
        or parts[2] != "pull"
        or "{}/{}".format(parts[0], parts[1]).lower() != repository.lower()
    ):
        raise AutoMergeError("invalid pull request URL: {}".format(pr_url))
    try:
        return int(parts[3])
    except ValueError as exc:
        raise AutoMergeError("invalid pull request number") from exc


def pr_metadata(repository: str, pr_url: str, gh_runner: GhRunner) -> Mapping[str, object]:
    output = gh_runner(
        [
            "pr",
            "view",
            pr_url,
            "--repo",
            repository,
            "--json",
            "headRefName,headRefOid,baseRefName,state,isDraft",
        ]
    )
    try:
        payload = json.loads(output)
    except (ValueError, json.JSONDecodeError) as exc:
        raise AutoMergeError("could not parse pull request metadata") from exc
    if not isinstance(payload, dict):
        raise AutoMergeError("pull request metadata must be an object")
    if payload.get("state") != "OPEN" or payload.get("isDraft") is not False:
        raise AutoMergeError("pull request must be open and ready for review")
    if payload.get("baseRefName") != "main":
        raise AutoMergeError("automatic refresh pull requests must target main")
    for key in ("headRefName", "headRefOid"):
        if not isinstance(payload.get(key), str) or not payload[key]:
            raise AutoMergeError("pull request metadata is missing {}".format(key))
    return payload


def find_validation_run(
    repository: str,
    workflow: str,
    branch: str,
    head_sha: str,
    gh_runner: GhRunner,
    sleeper: Sleeper,
    attempts: int = 30,
) -> Mapping[str, object]:
    for _ in range(attempts):
        output = gh_runner(
            [
                "run",
                "list",
                "--repo",
                repository,
                "--workflow",
                workflow,
                "--branch",
                branch,
                "--event",
                "workflow_dispatch",
                "--limit",
                "20",
                "--json",
                "databaseId,headSha,status,conclusion,url",
            ]
        )
        try:
            runs = json.loads(output)
        except (ValueError, json.JSONDecodeError) as exc:
            raise AutoMergeError("could not parse validation runs") from exc
        if not isinstance(runs, list):
            raise AutoMergeError("validation runs response must be a list")
        for run in runs:
            if isinstance(run, dict) and run.get("headSha") == head_sha:
                return run
        sleeper(2)
    raise AutoMergeError("validation workflow did not start for {}".format(head_sha))


def validate_and_merge(
    repository: str,
    pr_url: str,
    assessment_path: Path,
    workflow: str,
    gh_runner: GhRunner = run_gh,
    sleeper: Sleeper = time.sleep,
) -> str:
    load_assessment(assessment_path)
    parse_pr_url(pr_url, repository)
    metadata = pr_metadata(repository, pr_url, gh_runner)
    branch = str(metadata["headRefName"])
    head_sha = str(metadata["headRefOid"])
    gh_runner(
        ["workflow", "run", workflow, "--repo", repository, "--ref", branch]
    )
    run = find_validation_run(
        repository, workflow, branch, head_sha, gh_runner, sleeper
    )
    run_id = str(run.get("databaseId", ""))
    if not run_id:
        raise AutoMergeError("validation run is missing its database ID")
    gh_runner(["run", "watch", run_id, "--repo", repository, "--exit-status"])

    current = pr_metadata(repository, pr_url, gh_runner)
    if current.get("headRefOid") != head_sha:
        raise AutoMergeError("pull request head changed during validation")
    gh_runner(
        [
            "pr",
            "merge",
            pr_url,
            "--repo",
            repository,
            "--squash",
            "--delete-branch",
            "--match-head-commit",
            head_sha,
        ]
    )
    return head_sha


def create_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository", required=True)
    parser.add_argument("--pr-url", required=True)
    parser.add_argument("--assessment", type=Path, required=True)
    parser.add_argument("--workflow", default="validate-repository.yml")
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = create_parser().parse_args(argv)
    head_sha = validate_and_merge(
        args.repository, args.pr_url, args.assessment, args.workflow
    )
    print("Merged validated low-risk commit: {}".format(head_sha))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except AutoMergeError as exc:
        print("error: {}".format(exc))
        raise SystemExit(2)
