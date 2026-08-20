import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
WORKFLOW_ROOT = PROJECT_ROOT / ".github/workflows"
PINNED_ACTIONS = {
    "actions/checkout": (
        "3d3c42e5aac5ba805825da76410c181273ba90b1",
        "v7.0.1",
    ),
    "actions/setup-python": (
        "5fda3b95a4ea91299a34e894583c3862153e4b97",
        "v7.0.0",
    ),
}

SYNC_CONTRACTS = {
    "sync-ai-rules.yml": {
        "branch": "automation/ai-rules-sync",
        "paths": ("rules/GoogleAI", "rules/AI", "reports/ai"),
        "schedule": ("30 4 * * *", "30 4 * * 2,4,6"),
    },
    "sync-bilibili-rules.yml": {
        "branch": "automation/bilibili-rules-sync",
        "paths": ("rules/BiliBili", "reports/bilibili"),
        "schedule": ("10 4 * * *", "10 4 * * 2,4,6"),
    },
    "sync-game-rules.yml": {
        "branch": "automation/game-rules-sync",
        "paths": ("rules/Game", "rules/GameCN", "reports/game"),
        "schedule": ("5 4 * * *", "5 4 * * 2,4,6"),
    },
    "sync-google-rules.yml": {
        "branch": "automation/google-rules-sync",
        "paths": ("rules/Google", "reports/google"),
        "schedule": ("0 4 * * *", "0 4 * * 2,4,6"),
    },
    "sync-googlecn-rules.yml": {
        "branch": "automation/googlecn-rules-sync",
        "paths": ("rules/GoogleCN", "reports/googlecn"),
        "schedule": ("25 4 * * *", "25 4 * * 2,4,6"),
    },
    "sync-tiktok-rules.yml": {
        "branch": "automation/tiktok-rules-sync",
        "paths": ("rules/TikTok", "reports/tiktok"),
        "schedule": ("20 4 * * *", "20 4 * * 2,4,6"),
    },
    "sync-youtube-rules.yml": {
        "branch": "automation/youtube-rules-sync",
        "paths": ("rules/YouTube", "reports/youtube"),
        "schedule": ("15 4 * * *", "15 4 * * 2,4,6"),
    },
}


class WorkflowContractTests(unittest.TestCase):
    def test_exact_sync_workflow_set_is_covered(self):
        actual = {path.name for path in WORKFLOW_ROOT.glob("sync-*-rules.yml")}
        self.assertEqual(actual, set(SYNC_CONTRACTS))

    def test_sync_workflows_use_only_trusted_triggers_and_explicit_permissions(self):
        for name in SYNC_CONTRACTS:
            text = (WORKFLOW_ROOT / name).read_text(encoding="utf-8")
            trigger = text.split("concurrency:", 1)[0]
            with self.subTest(workflow=name):
                self.assertIn("workflow_dispatch:", trigger)
                self.assertIn("schedule:", trigger)
                self.assertNotIn("pull_request", trigger)
                self.assertNotIn("workflow_run", trigger)
                self.assertNotIn("repository_dispatch", trigger)
                self.assertNotIn("pull_request_target", text)
                self.assertNotIn("secrets.", text)
                self.assertIn("cancel-in-progress: false", text)
                for permission in (
                    "actions: write",
                    "contents: write",
                    "issues: write",
                    "pull-requests: write",
                ):
                    self.assertIn(permission, text)

    def test_sync_workflows_find_only_open_prs(self):
        for name in SYNC_CONTRACTS:
            text = (WORKFLOW_ROOT / name).read_text(encoding="utf-8")
            with self.subTest(workflow=name):
                self.assertIn("gh pr list", text)
                self.assertIn("--state open", text)
                self.assertNotIn('gh pr view "$REVIEW_BRANCH"', text)

    def test_schedules_are_staggered_and_conditions_match(self):
        daily_schedules = set()
        for name, contract in SYNC_CONTRACTS.items():
            text = (WORKFLOW_ROOT / name).read_text(encoding="utf-8")
            daily, stable = contract["schedule"]
            with self.subTest(workflow=name):
                self.assertIn('- cron: "{}"'.format(daily), text)
                self.assertIn('- cron: "{}"'.format(stable), text)
                self.assertIn("github.event.schedule == '{}'".format(daily), text)
                self.assertIn("github.event.schedule == '{}'".format(stable), text)
            daily_schedules.add(daily)
        self.assertEqual(len(daily_schedules), len(SYNC_CONTRACTS))

    def test_sync_workflows_bind_branch_head_and_changed_paths(self):
        for name, contract in SYNC_CONTRACTS.items():
            text = (WORKFLOW_ROOT / name).read_text(encoding="utf-8")
            with self.subTest(workflow=name):
                self.assertIn('echo "head_sha=$(git rev-parse HEAD)"', text)
                self.assertIn('echo "base_sha=$(git rev-parse HEAD^)"', text)
                self.assertIn(
                    "--expected-branch {}".format(contract["branch"]), text
                )
                self.assertIn(
                    '--expected-head-sha "${{ steps.review_pr.outputs.head_sha }}"',
                    text,
                )
                self.assertIn(
                    '--expected-base-sha "${{ steps.review_pr.outputs.base_sha }}"',
                    text,
                )
                for path in contract["paths"]:
                    self.assertIn("--allowed-path {}".format(path), text)

    def test_all_actions_are_pinned_to_full_commit_shas(self):
        for path in WORKFLOW_ROOT.glob("*.yml"):
            uses = [line.strip() for line in path.read_text(encoding="utf-8").splitlines() if "uses:" in line]
            with self.subTest(workflow=path.name):
                self.assertTrue(uses)
                expected = {
                    "uses: {}@{} # {}".format(action, sha, version)
                    for action, (sha, version) in PINNED_ACTIONS.items()
                }
                self.assertTrue(all(line in expected for line in uses), uses)

    def test_pull_request_validation_is_read_only_and_secret_free(self):
        text = (WORKFLOW_ROOT / "validate-repository.yml").read_text(encoding="utf-8")
        self.assertIn("pull_request:", text)
        self.assertIn("contents: read", text)
        self.assertNotIn("contents: write", text)
        self.assertNotIn("pull_request_target", text)
        self.assertNotIn("secrets.", text)


if __name__ == "__main__":
    unittest.main()
