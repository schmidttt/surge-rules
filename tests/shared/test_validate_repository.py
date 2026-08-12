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

    def test_115_emby_accepts_domain_rules(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = self.write_list(
                Path(temporary),
                "rules/Emby/115Emby.list",
                [
                    "DOMAIN-SUFFIX,115.com",
                    "DOMAIN-SUFFIX,115cdn.net",
                    "DOMAIN,cdn.wenjian.de",
                    "DOMAIN,1.cdn.wenjian.de",
                    "DOMAIN,2.cdn.wenjian.de",
                    "DOMAIN,3.cdn.wenjian.de",
                ],
            )
            count, rules = validate_list(path, 6)
            self.assertEqual(count, 6)
            self.assertIn("DOMAIN-SUFFIX,115cdn.net", rules)
            self.assertEqual(
                rules[-4:],
                [
                    "DOMAIN,cdn.wenjian.de",
                    "DOMAIN,1.cdn.wenjian.de",
                    "DOMAIN,2.cdn.wenjian.de",
                    "DOMAIN,3.cdn.wenjian.de",
                ],
            )

    def test_115_emby_rejects_ip_cidr(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = self.write_list(
                Path(temporary),
                "rules/Emby/115Emby.list",
                ["IP-CIDR,192.0.2.1/32"],
            )
            with self.assertRaises(ValidationError):
                validate_list(path, 1)

    def test_other_lists_reject_ip_cidr(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = self.write_list(
                Path(temporary),
                "rules/Google/Google.list",
                ["IP-CIDR,192.0.2.1/32"],
            )
            with self.assertRaises(ValidationError):
                validate_list(path, 1)


if __name__ == "__main__":
    unittest.main()
