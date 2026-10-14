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
        path.parent.mkdir(parents=True, exist_ok=True)
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

    def test_115_emby_accepts_exact_ipv4_hosts_with_domains(self):
        with tempfile.TemporaryDirectory() as temporary:
            expected = [
                "DOMAIN-SUFFIX,115.com",
                "IP-CIDR,192.0.2.1/32,no-resolve",
                "IP-CIDR,198.51.100.2/32,no-resolve",
                "IP-CIDR,203.0.113.3/32,no-resolve",
            ]
            path = self.write_list(
                Path(temporary),
                "rules/Emby/115Emby.list",
                expected,
            )
            self.assertEqual(validate_list(path, 4), (4, expected))

    def test_115_emby_rejects_invalid_or_broad_ip_rules(self):
        invalid_rules = [
            "IP-CIDR,192.0.2.1/32",
            "IP-CIDR,192.0.2.0/24,no-resolve",
            "IP-CIDR,192.0.2.1,no-resolve",
            "IP-CIDR,192.0.2.1/255.255.255.255,no-resolve",
            "IP-CIDR,999.0.2.1/32,no-resolve",
            "IP-CIDR,192.0.2.1:11566/32,no-resolve",
            "IP-CIDR,192.0.2.1/32,DIRECT",
            "IP-CIDR,192.0.2.1/32,no-resolve,DIRECT",
            "IP-CIDR,2001:db8::1/32,no-resolve",
            "IP-CIDR6,2001:db8::1/128,no-resolve",
        ]
        with tempfile.TemporaryDirectory() as temporary:
            for rule in invalid_rules:
                with self.subTest(rule=rule):
                    path = self.write_list(
                        Path(temporary), "rules/Emby/115Emby.list", [rule]
                    )
                    with self.assertRaises(ValidationError):
                        validate_list(path, 1)

    def test_other_lists_reject_ip_cidr(self):
        with tempfile.TemporaryDirectory() as temporary:
            for relative in (
                "rules/Google/Google.list",
                "rules/Emby/Emby.list",
                "rules/Other/115Emby.list",
                "115Emby.list",
            ):
                with self.subTest(path=relative):
                    path = self.write_list(
                        Path(temporary), relative,
                        ["IP-CIDR,192.0.2.1/32,no-resolve"],
                    )
                    with self.assertRaises(ValidationError):
                        validate_list(path, 1)

    def test_proxy_emby_accepts_exact_host_and_port(self):
        with tempfile.TemporaryDirectory() as temporary:
            expected = [
                "AND,((DOMAIN,er8mm.mobaiemby.site),(DEST-PORT,80))",
                "DOMAIN,emby101.origamiart.uk",
            ]
            path = self.write_list(
                Path(temporary), "rules/Emby/Emby.list", expected
            )
            self.assertEqual(validate_list(path, 2), (2, expected))

    def test_115_emby_accepts_exact_domain_and_port(self):
        with tempfile.TemporaryDirectory() as temporary:
            expected = [
                "DOMAIN-SUFFIX,115.com",
                "AND,((DOMAIN,er8mm.mobaiemby.site),(DEST-PORT,443))",
                "AND,((DOMAIN,er8mm.mobaiemby.site),(DEST-PORT,1))",
                "AND,((DOMAIN,er8mm.mobaiemby.site),(DEST-PORT,65535))",
                "IP-CIDR,192.0.2.1/32,no-resolve",
            ]
            path = self.write_list(
                Path(temporary), "rules/Emby/115Emby.list", expected
            )
            self.assertEqual(validate_list(path, 5), (5, expected))

    def test_115_emby_rejects_invalid_domain_and_port(self):
        invalid_rules = [
            "AND,((DOMAIN,er8mm.mobaiemby.site),(DEST-PORT,0))",
            "AND,((DOMAIN,er8mm.mobaiemby.site),(DEST-PORT,65536))",
            "AND,((DOMAIN,er8mm.mobaiemby.site),(DEST-PORT,0443))",
            "AND,((DOMAIN,er8mm.mobaiemby.site),(DEST-PORT,80-443))",
            "AND,((DOMAIN,er8mm.mobaiemby.site),(DEST-PORT,>80))",
            "AND,((DOMAIN,er8mm.mobaiemby.site),(DEST-PORT,443)),DIRECT",
            "AND,((DOMAIN,er8mm.mobaiemby.site))",
            "AND,((DOMAIN,er8mm.mobaiemby.site),(DEST-PORT,443)",
            "AND,((DOMAIN,er8mm.mobaiemby.site),(DEST-PORT,443),(PROTOCOL,TCP))",
            "OR,((DOMAIN,er8mm.mobaiemby.site),(DEST-PORT,443))",
            "AND,((DOMAIN-SUFFIX,mobaiemby.site),(DEST-PORT,443))",
            "AND,((DOMAIN,https://er8mm.mobaiemby.site),(DEST-PORT,443))",
            "AND,((DOMAIN,er8mm.mobaiemby.site:443),(DEST-PORT,443))",
            "AND,((DOMAIN,ER8MM.mobaiemby.site),(DEST-PORT,443))",
            "AND,((DOMAIN,er8mm..mobaiemby.site),(DEST-PORT,443))",
            "AND,((DOMAIN,-er8mm.mobaiemby.site),(DEST-PORT,443))",
            "AND,((DOMAIN,*.mobaiemby.site),(DEST-PORT,443))",
        ]
        with tempfile.TemporaryDirectory() as temporary:
            for rule in invalid_rules:
                with self.subTest(rule=rule):
                    path = self.write_list(
                        Path(temporary), "rules/Emby/115Emby.list", [rule]
                    )
                    with self.assertRaises(ValidationError):
                        validate_list(path, 1)

    def test_other_lists_reject_domain_and_port(self):
        with tempfile.TemporaryDirectory() as temporary:
            for relative in (
                "rules/Google/Google.list",
                "rules/Other/115Emby.list",
                "115Emby.list",
            ):
                with self.subTest(path=relative):
                    path = self.write_list(
                        Path(temporary), relative,
                        ["AND,((DOMAIN,er8mm.mobaiemby.site),(DEST-PORT,443))"],
                    )
                    with self.assertRaises(ValidationError):
                        validate_list(path, 1)

    def test_115_emby_rejects_unrestricted_domain_coverage(self):
        with tempfile.TemporaryDirectory() as temporary:
            for broad_rule in (
                "DOMAIN,er8mm.mobaiemby.site",
                "DOMAIN-SUFFIX,er8mm.mobaiemby.site",
                "DOMAIN-SUFFIX,mobaiemby.site",
            ):
                for reverse in (False, True):
                    with self.subTest(rule=broad_rule, reverse=reverse):
                        rules = [
                            "AND,((DOMAIN,er8mm.mobaiemby.site),(DEST-PORT,443))",
                            broad_rule,
                        ]
                        path = self.write_list(
                            Path(temporary), "rules/Emby/115Emby.list",
                            list(reversed(rules)) if reverse else rules,
                        )
                        with self.assertRaises(ValidationError):
                            validate_list(path, 2)


if __name__ == "__main__":
    unittest.main()
