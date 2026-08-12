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

    def test_non_low_risk_is_rejected_before_github_calls(self):
        calls = []
        with self.assertRaises(MODULE.AutoMergeError):
            MODULE.validate_and_merge(
                "owner/repo",
                "https://github.com/owner/repo/pull/8",
                self.assessment_file("medium-risk", False, ["threshold"]),
                "validate-repository.yml",
                lambda args: calls.append(list(args)) or "",
                lambda _: None,
            )
        self.assertEqual(calls, [])

    def test_exact_head_is_dispatched_validated_and_merged(self):
        calls = []
        metadata = {
            "headRefName": "automation/google-rules-sync",
            "headRefOid": "abc123",
            "baseRefName": "main",
            "state": "OPEN",
            "isDraft": False,
        }

        def fake_runner(args):
            calls.append(list(args))
            if args[:2] == ["pr", "view"]:
                return json.dumps(metadata)
            if args[:2] == ["run", "list"]:
                return json.dumps(
                    [{"databaseId": 99, "headSha": "abc123", "status": "queued"}]
                )
            return ""

        result = MODULE.validate_and_merge(
            "owner/repo",
            "https://github.com/owner/repo/pull/8",
            self.assessment_file(),
            "validate-repository.yml",
            fake_runner,
            lambda _: None,
        )
        self.assertEqual(result, "abc123")
        self.assertIn(
            [
                "workflow", "run", "validate-repository.yml", "--repo", "owner/repo",
                "--ref", "automation/google-rules-sync",
            ],
            calls,
        )
        merge = next(args for args in calls if args[:2] == ["pr", "merge"])
        self.assertIn("--match-head-commit", merge)
        self.assertIn("abc123", merge)

    def test_head_change_after_validation_blocks_merge(self):
        calls = []
        metadata_calls = 0

        def fake_runner(args):
            nonlocal metadata_calls
            calls.append(list(args))
            if args[:2] == ["pr", "view"]:
                metadata_calls += 1
                return json.dumps(
                    {
                        "headRefName": "automation/google-rules-sync",
                        "headRefOid": "abc123" if metadata_calls == 1 else "def456",
                        "baseRefName": "main",
                        "state": "OPEN",
                        "isDraft": False,
                    }
                )
            if args[:2] == ["run", "list"]:
                return json.dumps([{"databaseId": 99, "headSha": "abc123"}])
            return ""

        with self.assertRaises(MODULE.AutoMergeError):
            MODULE.validate_and_merge(
                "owner/repo",
                "https://github.com/owner/repo/pull/8",
                self.assessment_file(),
                "validate-repository.yml",
                fake_runner,
                lambda _: None,
            )
        self.assertFalse(any(args[:2] == ["pr", "merge"] for args in calls))


if __name__ == "__main__":
    unittest.main()
