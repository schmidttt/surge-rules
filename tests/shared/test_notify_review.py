import importlib.util
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = PROJECT_ROOT / "scripts/shared/notify_review.py"
SPEC = importlib.util.spec_from_file_location("notify_review", SCRIPT_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


class NotificationTests(unittest.TestCase):
    def assessment(self):
        return {
            "classification": "high-risk",
            "added_count": 2,
            "removed_count": 1,
            "reasons": ["rules-removed"],
            "new_unresolved_candidate_count": 1,
        }

    def test_parse_pr_url_rejects_other_repository(self):
        with self.assertRaises(MODULE.NotificationError):
            MODULE.parse_pr_url(
                "https://github.com/other/repo/pull/8",
                "owner/repo",
            )

    def test_low_risk_assessment_never_calls_github(self):
        calls = []

        def fake_runner(arguments, payload):
            calls.append((list(arguments), payload))
            return ""

        result = MODULE.notify(
            "owner/repo",
            8,
            "owner",
            "Google",
            {"classification": "low-risk"},
            [],
            "docs/rules/google/REVIEW_CHECKLIST.md",
            fake_runner,
        )
        self.assertEqual(result, "skipped-low-risk")
        self.assertEqual(calls, [])

    def test_fingerprint_changes_with_review_evidence(self):
        first = MODULE.notification_fingerprint(
            "Google",
            self.assessment(),
            [{"verification": {"manual_review": [{"identity": "domain:a.test"}]}}],
        )
        second = MODULE.notification_fingerprint(
            "Google",
            self.assessment(),
            [{"verification": {"manual_review": [{"identity": "domain:b.test"}]}}],
        )
        self.assertNotEqual(first, second)

    def test_medium_risk_is_reported(self):
        assessment = self.assessment()
        assessment["classification"] = "medium-risk"
        calls = []

        def fake_runner(arguments, payload):
            calls.append((list(arguments), payload))
            return ""

        result = MODULE.notify(
            "owner/repo",
            8,
            "owner",
            "Google",
            assessment,
            [],
            "docs/rules/google/REVIEW_CHECKLIST.md",
            fake_runner,
        )
        self.assertEqual(result, "review-requested")
        comment = calls[-1][1]["body"]
        self.assertIn("`medium-risk`", comment)

    def test_new_notification_requests_review_then_comments(self):
        calls = []

        def fake_runner(arguments, payload):
            calls.append((list(arguments), payload))
            endpoint = arguments[1] if len(arguments) > 1 else ""
            if endpoint.endswith("/comments") and "--method" not in arguments:
                return ""
            if endpoint.endswith("/requested_reviewers") and "--method" not in arguments:
                return ""
            return ""

        result = MODULE.notify(
            "owner/repo",
            8,
            "owner",
            "Google",
            self.assessment(),
            [],
            "docs/rules/google/REVIEW_CHECKLIST.md",
            fake_runner,
        )
        self.assertEqual(result, "review-requested")
        post_payloads = [
            payload for arguments, payload in calls if "--method" in arguments
        ]
        self.assertEqual(post_payloads[0], {"reviewers": ["owner"]})
        self.assertNotIn("@owner", post_payloads[1]["body"])

    def test_existing_review_request_uses_one_mention(self):
        calls = []

        def fake_runner(arguments, payload):
            calls.append((list(arguments), payload))
            endpoint = arguments[1] if len(arguments) > 1 else ""
            if endpoint.endswith("/comments") and "--method" not in arguments:
                return ""
            if endpoint.endswith("/requested_reviewers") and "--method" not in arguments:
                return "owner\n"
            return ""

        result = MODULE.notify(
            "owner/repo",
            8,
            "owner",
            "AI",
            self.assessment(),
            [],
            "docs/rules/ai/REVIEW_CHECKLIST.md",
            fake_runner,
        )
        self.assertEqual(result, "commented-and-mentioned")
        posts = [
            payload for arguments, payload in calls if "--method" in arguments
        ]
        self.assertEqual(len(posts), 1)
        self.assertIn("@owner", posts[0]["body"])

    def test_duplicate_marker_sends_nothing(self):
        assessment = self.assessment()
        fingerprint = MODULE.notification_fingerprint(
            "Game", assessment, []
        )
        marker = "<!-- surge-rules-review:Game:{} -->".format(fingerprint)
        calls = []

        def fake_runner(arguments, payload):
            calls.append((list(arguments), payload))
            return marker

        result = MODULE.notify(
            "owner/repo",
            8,
            "owner",
            "Game",
            assessment,
            [],
            "docs/rules/game/REVIEW_CHECKLIST.md",
            fake_runner,
        )
        self.assertEqual(result, "skipped-duplicate")
        self.assertEqual(len(calls), 1)


if __name__ == "__main__":
    unittest.main()
