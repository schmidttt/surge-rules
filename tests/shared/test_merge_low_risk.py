import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = PROJECT_ROOT / "scripts/shared/merge_low_risk.py"
SPEC = importlib.util.spec_from_file_location("merge_low_risk", SCRIPT_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


class AutoMergeTests(unittest.TestCase):
    def assessment_file(self, classification="low-risk", eligible=True, reasons=None):
        handle = tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", delete=False)
        json.dump(
            {
                "classification": classification,
                "auto_merge_eligible": eligible,
                "reasons": [] if reasons is None else reasons,
            },
            handle,
        )
        handle.close()
        self.addCleanup(Path(handle.name).unlink)
        return Path(handle.name)

    @staticmethod
    def metadata(head="abc123", branch="automation/google-rules-sync"):
        return {
            "headRefName": branch,
            "headRefOid": head,
            "baseRefName": "main",
            "state": "OPEN",
            "isDraft": False,
        }

    def call_merge(self, runner, sleeper=lambda _: None):
        return MODULE.validate_and_merge(
            "owner/repo",
            "https://github.com/owner/repo/pull/8",
            self.assessment_file(),
            "validate-repository.yml",
            ["rules/Google", "reports/google"],
            "automation/google-rules-sync",
            "abc123",
            runner,
            sleeper,
        )

    def test_non_low_risk_is_rejected_before_github_calls(self):
        calls = []
        with self.assertRaises(MODULE.AutoMergeError):
            MODULE.validate_and_merge(
                "owner/repo",
                "https://github.com/owner/repo/pull/8",
                self.assessment_file("medium-risk", False, ["threshold"]),
                "validate-repository.yml",
                ["rules/Google", "reports/google"],
                "automation/google-rules-sync",
                "abc123",
                lambda args: calls.append(list(args)) or "",
                lambda _: None,
            )
        self.assertEqual(calls, [])

    def test_action_required_pr_check_is_approved_watched_and_merged(self):
        calls = []

        def fake_runner(args):
            calls.append(list(args))
            if args[:2] == ["pr", "view"]:
                return json.dumps(self.metadata())
            if args[:3] == ["api", "--paginate", "repos/owner/repo/pulls/8/files"]:
                return "rules/Google/Google.list\nreports/google/change-assessment.json\n"
            if args[:2] == ["run", "list"]:
                return json.dumps(
                    [
                        {
                            "databaseId": 99,
                            "headSha": "abc123",
                            "status": "completed",
                            "conclusion": "action_required",
                        }
                    ]
                )
            return ""

        result = self.call_merge(fake_runner)
        self.assertEqual(result, "abc123")
        self.assertIn(
            [
                "api",
                "--method",
                "POST",
                "repos/owner/repo/actions/runs/99/approve",
            ],
            calls,
        )
        self.assertIn(
            ["run", "watch", "99", "--repo", "owner/repo", "--exit-status"],
            calls,
        )
        self.assertTrue(any(args[:2] == ["pr", "checks"] for args in calls))
        self.assertFalse(any(args[:2] == ["workflow", "run"] for args in calls))
        merge = next(args for args in calls if args[:2] == ["pr", "merge"])
        self.assertIn("--match-head-commit", merge)
        self.assertIn("abc123", merge)

    def test_already_successful_pr_check_is_not_approved_again(self):
        calls = []

        def fake_runner(args):
            calls.append(list(args))
            if args[:2] == ["pr", "view"]:
                return json.dumps(self.metadata())
            if args[:3] == ["api", "--paginate", "repos/owner/repo/pulls/8/files"]:
                return "rules/Google/Google.list\n"
            if args[:2] == ["run", "list"]:
                return json.dumps(
                    [
                        {
                            "databaseId": 99,
                            "headSha": "abc123",
                            "status": "completed",
                            "conclusion": "success",
                        }
                    ]
                )
            return ""

        self.call_merge(fake_runner)
        self.assertFalse(any("approve" in arg for call in calls for arg in call))
        self.assertTrue(any(args[:2] == ["pr", "merge"] for args in calls))

    def test_failed_pr_check_blocks_merge(self):
        calls = []

        def fake_runner(args):
            calls.append(list(args))
            if args[:2] == ["pr", "view"]:
                return json.dumps(self.metadata())
            if args[:3] == ["api", "--paginate", "repos/owner/repo/pulls/8/files"]:
                return "rules/Google/Google.list\n"
            if args[:2] == ["run", "list"]:
                return json.dumps(
                    [
                        {
                            "databaseId": 99,
                            "headSha": "abc123",
                            "status": "completed",
                            "conclusion": "failure",
                        }
                    ]
                )
            return ""

        with self.assertRaisesRegex(MODULE.AutoMergeError, "concluded with failure"):
            self.call_merge(fake_runner)
        self.assertFalse(any(args[:2] == ["pr", "merge"] for args in calls))

    def test_unexpected_changed_file_blocks_validation_and_merge(self):
        calls = []

        def fake_runner(args):
            calls.append(list(args))
            if args[:2] == ["pr", "view"]:
                return json.dumps(self.metadata())
            if args[:3] == ["api", "--paginate", "repos/owner/repo/pulls/8/files"]:
                return "rules/Google/Google.list\n.github/workflows/pwn.yml\n"
            return ""

        with self.assertRaisesRegex(MODULE.AutoMergeError, "outside the allowed paths"):
            self.call_merge(fake_runner)
        self.assertFalse(any(args[:2] == ["run", "list"] for args in calls))
        self.assertFalse(any(args[:2] == ["pr", "merge"] for args in calls))

    def test_unexpected_branch_or_generated_head_blocks_before_validation(self):
        for metadata, message in (
            (self.metadata(branch="automation/other"), "does not match"),
            (self.metadata(head="def456"), "generated commit"),
        ):
            calls = []

            def fake_runner(args, payload=metadata):
                calls.append(list(args))
                if args[:2] == ["pr", "view"]:
                    return json.dumps(payload)
                return ""

            with self.subTest(metadata=metadata):
                with self.assertRaisesRegex(MODULE.AutoMergeError, message):
                    self.call_merge(fake_runner)
                self.assertFalse(any(args[:2] == ["run", "list"] for args in calls))

    def test_head_change_after_validation_blocks_merge(self):
        calls = []
        metadata_calls = 0

        def fake_runner(args):
            nonlocal metadata_calls
            calls.append(list(args))
            if args[:2] == ["pr", "view"]:
                metadata_calls += 1
                return json.dumps(
                    self.metadata(head="abc123" if metadata_calls == 1 else "def456")
                )
            if args[:3] == ["api", "--paginate", "repos/owner/repo/pulls/8/files"]:
                return "rules/Google/Google.list\n"
            if args[:2] == ["run", "list"]:
                return json.dumps(
                    [
                        {
                            "databaseId": 99,
                            "headSha": "abc123",
                            "status": "completed",
                            "conclusion": "success",
                        }
                    ]
                )
            return ""

        with self.assertRaisesRegex(MODULE.AutoMergeError, "head changed"):
            self.call_merge(fake_runner)
        self.assertFalse(any(args[:2] == ["pr", "merge"] for args in calls))


if __name__ == "__main__":
    unittest.main()
