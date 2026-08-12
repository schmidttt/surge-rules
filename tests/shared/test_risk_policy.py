import importlib.util
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = PROJECT_ROOT / "scripts/shared/risk_policy.py"
SPEC = importlib.util.spec_from_file_location("risk_policy", SCRIPT_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


class RiskPolicyTests(unittest.TestCase):
    def assessment(self, reasons, eligible):
        return {
            "schema_version": 1,
            "classification": "low-risk" if eligible else "review-required",
            "auto_merge_eligible": eligible,
            "reasons": reasons,
        }

    def test_no_reasons_is_low_risk(self):
        result = MODULE.normalize_assessment(self.assessment([], True))
        self.assertEqual(result["classification"], "low-risk")
        self.assertEqual(result["risk_level"], "low-risk")

    def test_threshold_excess_is_medium_risk(self):
        result = MODULE.normalize_assessment(
            self.assessment(["addition-count-above-auto-merge-limit"], False)
        )
        self.assertEqual(result["classification"], "medium-risk")

    def test_removal_is_high_risk(self):
        result = MODULE.normalize_assessment(
            self.assessment(["rules-removed"], False)
        )
        self.assertEqual(result["classification"], "high-risk")

    def test_unknown_reason_fails_closed_as_high_risk(self):
        result = MODULE.normalize_assessment(
            self.assessment(["future-safety-signal"], False)
        )
        self.assertEqual(result["classification"], "high-risk")

    def test_inconsistent_auto_merge_flag_is_rejected(self):
        with self.assertRaises(MODULE.RiskPolicyError):
            MODULE.normalize_assessment(self.assessment(["rules-removed"], True))


if __name__ == "__main__":
    unittest.main()
