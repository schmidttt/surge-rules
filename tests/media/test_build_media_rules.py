import importlib.util
import json
import sys
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
FIXTURE_ROOT = Path(__file__).resolve().parent / "fixtures"
SCRIPT_PATH = PROJECT_ROOT / "scripts" / "media" / "build_media_rules.py"
SPEC = importlib.util.spec_from_file_location("build_media_rules", SCRIPT_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


class ParserTests(unittest.TestCase):
    def setUp(self):
        self.tree = MODULE.load_local_tree(FIXTURE_ROOT / "v2fly-data")

    def test_v2fly_attributes_and_full_rules_are_preserved(self):
        config = replace(MODULE.PRODUCTS["youtube"], minimum_rules=1)
        rules, counts, omitted = MODULE.build_product_rules(
            self.tree, config, [], []
        )
        identities = {rule.identity for rule in rules}
        self.assertIn(("domain", "youtube.com"), identities)
        self.assertIn(("full", "yt3.googleusercontent.com"), identities)
        self.assertEqual(counts["ads_tagged_in_source"], 1)
        self.assertEqual(omitted, [])

    def test_patch_include_and_exclude_are_exact(self):
        config = replace(MODULE.PRODUCTS["tiktok"], minimum_rules=1)
        include = [MODULE.Rule("full", "manual.tiktok.example")]
        exclude = [MODULE.Rule("domain", "musical.ly")]
        rules, _, _ = MODULE.build_product_rules(
            self.tree, config, include, exclude
        )
        identities = {rule.identity for rule in rules}
        self.assertIn(("full", "manual.tiktok.example"), identities)
        self.assertNotIn(("domain", "musical.ly"), identities)

    def test_project_tiktok_patch_preserves_byteoversea(self):
        config = replace(MODULE.PRODUCTS["tiktok"], minimum_rules=1)
        include = MODULE.parse_patch(
            PROJECT_ROOT / "patches" / "tiktok" / "include.txt"
        )
        rules, _, _ = MODULE.build_product_rules(
            self.tree, config, include, []
        )
        identities = {rule.identity for rule in rules}
        self.assertIn(("domain", "byteoversea.com"), identities)

    def test_bilibili_expands_cdn_and_game_lists(self):
        config = replace(MODULE.PRODUCTS["bilibili"], minimum_rules=1)
        rules, _, _ = MODULE.build_product_rules(self.tree, config, [], [])
        identities = {rule.identity for rule in rules}
        self.assertIn(("domain", "bilibili.com"), identities)
        self.assertIn(("domain", "bilivideo.com"), identities)
        self.assertIn(("domain", "biligame.com"), identities)
        self.assertIn(("full", "upos-hz-mirrorakam.akamaized.net"), identities)

    def test_sukka_parser_ignores_comments_and_counts_other_types(self):
        text = (FIXTURE_ROOT / "Sukka-stream.ts").read_text(encoding="utf-8")
        rules, unsupported = MODULE.parse_sukka_service(text, "TIKTOK")
        identities = {rule.identity for rule in rules}
        self.assertIn(("domain", "tiktok.com"), identities)
        self.assertNotIn(("domain", "commented-out.example"), identities)
        self.assertEqual(unsupported["DOMAIN-KEYWORD"], 1)
        self.assertEqual(unsupported["USER-AGENT"], 1)

    def test_blackmatrix_is_aggregate_comparison_only(self):
        config = replace(MODULE.PRODUCTS["youtube"], minimum_rules=1)
        rules, _, _ = MODULE.build_product_rules(self.tree, config, [], [])
        text = (FIXTURE_ROOT / "BlackMatrix-YouTube.list").read_text(
            encoding="utf-8"
        )
        report = MODULE.compare_reference(rules, text)
        identities = {rule.identity for rule in rules}
        self.assertNotIn(("domain", "blackmatrix-video.example"), identities)
        self.assertEqual(report["non_domain_types"]["DOMAIN-KEYWORD"], 1)
        self.assertFalse(report["entries_persisted"])


class SafetyTests(unittest.TestCase):
    def test_render_uses_beijing_time_and_no_trailing_newline(self):
        config = MODULE.PRODUCTS["youtube"]
        metadata = MODULE.SourceMetadata(
            "example/repo", "main", "abc", "2026-07-21T08:54:40Z"
        )
        rendered = MODULE.render_rules(
            config, metadata, [MODULE.Rule("domain", "youtube.com")]
        )
        self.assertTrue(rendered.startswith("# NAME: schmidttt's YouTube Ruleset\n"))
        self.assertIn("# UPDATED: 2026.07.21 16:54:40", rendered)
        self.assertIn("# TOTAL: 1", rendered)
        self.assertTrue(rendered.endswith("DOMAIN-SUFFIX,youtube.com"))
        self.assertFalse(rendered.endswith("\n"))

    def test_deletion_always_requires_review(self):
        config = replace(
            MODULE.PRODUCTS["youtube"],
            auto_merge_max_change_ratio=1.0,
        )
        rules = [
            MODULE.Rule("domain", "youtube.com"),
            MODULE.Rule("domain", "googlevideo.com"),
            MODULE.Rule("domain", "ytimg.com"),
        ]
        existing = {rule.identity for rule in rules}
        existing.add(("domain", "old.example"))
        report = {"unsupported_omitted": []}
        assessment = MODULE.assess_change(
            config, rules, existing, [], report, 0,
            {"sources": {"sukka": {"not_covered_by_generated_count": 0}}},
        )
        self.assertFalse(assessment["auto_merge_eligible"])
        self.assertIn("rules-removed", assessment["reasons"])

    def test_small_addition_can_be_low_risk_after_baseline(self):
        config = replace(
            MODULE.PRODUCTS["youtube"],
            auto_merge_max_change_ratio=0.5,
        )
        existing = {
            ("domain", "youtube.com"),
            ("domain", "googlevideo.com"),
            ("domain", "ytimg.com"),
        }
        rules = [MODULE.Rule(*identity) for identity in existing]
        rules.append(MODULE.Rule("domain", "new.example"))
        assessment = MODULE.assess_change(
            config,
            rules,
            existing,
            [],
            {"unsupported_omitted": []},
            1,
            {"sources": {"sukka": {"not_covered_by_generated_count": 1}}},
        )
        self.assertTrue(assessment["auto_merge_eligible"])

    def test_increased_manual_review_count_requires_review(self):
        config = replace(
            MODULE.PRODUCTS["tiktok"],
            auto_merge_max_change_ratio=1.0,
        )
        existing = {
            ("domain", "tiktok.com"),
            ("domain", "tiktokv.com"),
            ("domain", "tiktokcdn.com"),
        }
        rules = [MODULE.Rule(*identity) for identity in existing]
        assessment = MODULE.assess_change(
            config,
            rules,
            existing,
            [],
            {"unsupported_omitted": []},
            2,
            {"sources": {"sukka": {"not_covered_by_generated_count": 1}}},
        )
        self.assertFalse(assessment["auto_merge_eligible"])
        self.assertIn(
            "reference-manual-review-increased",
            assessment["reasons"],
        )

    def test_changed_manual_review_set_requires_review(self):
        config = replace(
            MODULE.PRODUCTS["tiktok"],
            auto_merge_max_change_ratio=1.0,
        )
        existing = {
            ("domain", "tiktok.com"),
            ("domain", "tiktokv.com"),
            ("domain", "tiktokcdn.com"),
        }
        rules = [MODULE.Rule(*identity) for identity in existing]
        assessment = MODULE.assess_change(
            config,
            rules,
            existing,
            [],
            {"unsupported_omitted": []},
            1,
            {
                "verification": {
                    "manual_review_count": 1,
                    "manual_review_fingerprint": "a" * 64,
                }
            },
            "b" * 64,
        )
        self.assertIn(
            "reference-manual-review-set-changed",
            assessment["reasons"],
        )

    def test_core_suffix_disappearance_fails(self):
        config = replace(MODULE.PRODUCTS["tiktok"], minimum_rules=1)
        with self.assertRaises(MODULE.BuildError):
            MODULE.validate_output(
                config,
                [MODULE.Rule("domain", "tiktok.com")],
                set(),
                False,
            )


class IntegrationTests(unittest.TestCase):
    def test_local_build_writes_all_products(self):
        originals = dict(MODULE.PRODUCTS)
        try:
            MODULE.PRODUCTS["youtube"] = replace(
                MODULE.PRODUCTS["youtube"], minimum_rules=1
            )
            MODULE.PRODUCTS["tiktok"] = replace(
                MODULE.PRODUCTS["tiktok"], minimum_rules=1
            )
            MODULE.PRODUCTS["bilibili"] = replace(
                MODULE.PRODUCTS["bilibili"], minimum_rules=1
            )
            with tempfile.TemporaryDirectory() as temp_dir:
                root = Path(temp_dir)
                for product in ("youtube", "tiktok", "bilibili"):
                    patch_dir = root / "patches" / product
                    patch_dir.mkdir(parents=True)
                    (patch_dir / "include.txt").write_text("", encoding="utf-8")
                    (patch_dir / "exclude.txt").write_text("", encoding="utf-8")
                    blackmatrix = (
                        FIXTURE_ROOT
                        / ("BlackMatrix-{}.list".format(MODULE.PRODUCTS[product].display_name))
                    )
                    exit_code = MODULE.main(
                        [
                            "--product", product,
                            "--source-dir", str(FIXTURE_ROOT / "v2fly-data"),
                            "--blackmatrix-file", str(blackmatrix),
                            "--sukka-stream-file", str(FIXTURE_ROOT / "Sukka-stream.ts"),
                            "--project-root", str(root),
                        ]
                    )
                    self.assertEqual(exit_code, 0)

                self.assertTrue((root / "rules/YouTube/YouTube.list").is_file())
                self.assertTrue((root / "rules/TikTok/TikTok.list").is_file())
                self.assertTrue((root / "rules/BiliBili/BiliBili.list").is_file())
                audit = json.loads(
                    (root / "reports/tiktok/reference-audit.json").read_text(
                        encoding="utf-8"
                    )
                )
                self.assertFalse(
                    audit["policy"]["third_party_reference_entries_persisted"]
                )
                self.assertIn("verification", audit)
                self.assertIn("manual_review_count", audit["verification"])
        finally:
            MODULE.PRODUCTS.clear()
            MODULE.PRODUCTS.update(originals)


if __name__ == "__main__":
    unittest.main()
