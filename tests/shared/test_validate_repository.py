import sys
import tempfile
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

from validate_repository import ValidationError, validate_list  # noqa: E402


class RepositoryListValidationTests(unittest.TestCase):
    def write_list(self, root: Path, relative: str, rules: list[str]) -> Path:
        path = root / relative
        path.parent.mkdir(parents=True)
        lines = ["# TOTAL: {}".format(len(rules)), *rules]
        path.write_bytes("\n".join(lines).encode("utf-8"))
        return path

    def test_emby_accepts_exact_ipv4_cidr(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = self.write_list(
                Path(temporary),
                "rules/Emby/Emby.list",
                [
                    "DOMAIN-SUFFIX,example.com",
                    "IP-CIDR,110.42.42.172/32",
                ],
            )
            count, rules = validate_list(path, 2)
            self.assertEqual(count, 2)
            self.assertIn("IP-CIDR,110.42.42.172/32", rules)

    def test_emby_rejects_noncanonical_ipv4_network(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = self.write_list(
                Path(temporary),
                "rules/Emby/Emby.list",
                ["IP-CIDR,110.42.42.172/24"],
            )
            with self.assertRaises(ValidationError):
                validate_list(path, 1)

    def test_other_lists_reject_ip_cidr(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = self.write_list(
                Path(temporary),
                "rules/Google/Google.list",
                ["IP-CIDR,110.42.42.172/32"],
            )
            with self.assertRaises(ValidationError):
                validate_list(path, 1)


if __name__ == "__main__":
    unittest.main()
