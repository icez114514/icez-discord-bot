import json
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path

from database import parse_import, DatabaseError
from legacy_merge import load_exact, merge_data, merge_files


class LegacyTests(unittest.TestCase):
    def test_merge_selection_and_independent_clamping(self):
        cash = {"1": {"crystals": 5, "Time": 10}, "2": {"crystals": -10},
                "3": {"crystals": 0}, "4": {"crystals": 7}}
        bank = {"1": {"savings": -100, "loanings": 99}, "2": {"savings": 20},
                "5": {"savings": 4}, "6": {"savings": 0}, "7": {"savings": -1}}
        rows, report = merge_data(cash, bank)
        self.assertEqual(rows, [
            {"user_id": "1", "balance": "5"}, {"user_id": "2", "balance": "20"},
            {"user_id": "3", "balance": "0"}, {"user_id": "4", "balance": "7"},
            {"user_id": "5", "balance": "4"},
        ])
        self.assertEqual((report["accounts"], report["skipped"], report["total"]), (5, 2, "36"))
        self.assertEqual(len(report["negative_corrections"]), 3)

    def test_exact_scientific_notation_and_no_decimal_context_rounding(self):
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder) / "source.json"
            source.write_text('{"1":{"crystals":1.6077469268776536e25}}', encoding="utf-8")
            data, digest = load_exact(source)
            self.assertEqual(len(digest), 64)
            rows, _ = merge_data(data, {"1": {"savings": 1}})
            self.assertEqual(rows[0]["balance"], "16077469268776536000000001")
            rows, _ = merge_data({"1": {"crystals": Decimal("1e100")}}, {"1": {"savings": 1}})
            self.assertEqual(int(rows[0]["balance"]), 10**100 + 1)

    def test_duplicate_keys_and_nonfinite_rejected(self):
        for raw in ('{"1":{},"1":{}}', '{"1":{"crystals":1,"crystals":2}}',
                    '{"1":{"crystals":NaN}}', '{"1":{"crystals":Infinity}}'):
            with self.subTest(raw=raw), tempfile.TemporaryDirectory() as folder:
                path = Path(folder) / "bad.json"
                path.write_text(raw, encoding="utf-8")
                with self.assertRaises(ValueError):
                    load_exact(path)

    def test_invalid_source_numbers_and_ids(self):
        for value in (Decimal("1.1"), Decimal("Infinity"), Decimal("NaN"), True, "123"):
            with self.assertRaises(ValueError):
                merge_data({"1": {"crystals": value}}, {})
        for data in ({"0": {"crystals": 1}}, {"1": {"crystals": 1}, "01": {"crystals": 2}},
                     {"1": {}}, {"bad": {"crystals": 1}}):
            with self.assertRaises(ValueError):
                merge_data(data, {})

    def test_file_roundtrip_hashes_and_originals_preserved(self):
        with tempfile.TemporaryDirectory() as folder:
            cash, bank, output = [Path(folder) / n for n in ("cash.json", "bank.json", "merged.json")]
            cash.write_text('{"1":{"crystals":1e100}}', encoding="utf-8")
            bank.write_text('{"1":{"savings":1}}', encoding="utf-8")
            before = (cash.read_bytes(), bank.read_bytes())
            report = merge_files(cash, bank, output)
            self.assertEqual(parse_import(output)[0].balance, 10**100 + 1)
            self.assertEqual((cash.read_bytes(), bank.read_bytes()), before)
            self.assertEqual(report["total"], str(10**100 + 1))
            self.assertTrue(output.with_name("merged.json.report.json").exists())
            with self.assertRaises(ValueError):
                merge_files(cash, bank, output)
            with self.assertRaises(ValueError):
                merge_files(cash, bank, cash)

    def test_generic_import_accepts_integer_strings_rejects_fractions(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "accounts.json"
            for amount in (10**100 + 1, str(10**100 + 1), 0, "0"):
                path.write_text(json.dumps([{"user_id": "1", "balance": amount}]), encoding="utf-8")
                self.assertEqual(parse_import(path)[0].balance, int(amount))
            for amount in (-1, "-1", "1e10", "1.0", 1.0, True, "NaN"):
                path.write_text(json.dumps([{"user_id": "1", "balance": amount}]), encoding="utf-8")
                with self.assertRaises(DatabaseError):
                    parse_import(path)
