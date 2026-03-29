#!/usr/bin/env python3

import unittest
from unittest.mock import patch
from io import StringIO
import sys
import os
import json
import tempfile

sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "util"))

import genRuleFile


def make_base_metrics():
    """Return a minimal but complete metrics dict for testing."""
    return {
        "constraints__clocks__count": 1,
        "constraints__clocks__details": ["core_clock: 2.0"],
        "synth__design__instance__area__stdcell": 500.0,
        "detailedplace__design__violations": 0,
        "placeopt__design__instance__count__stdcell": 400,
        "placeopt__design__instance__area": 600,
        "cts__design__instance__count__setup_buffer": 20,
        "cts__design__instance__count__hold_buffer": 15,
        "cts__timing__setup__ws": -0.05,
        "cts__timing__setup__tns": -0.3,
        "cts__timing__hold__ws": 0.0,
        "cts__timing__hold__tns": 0.0,
        "globalroute__antenna_diodes_count": 5,
        "globalroute__route__net": 500,
        "globalroute__timing__setup__ws": -0.06,
        "globalroute__timing__setup__tns": -0.5,
        "globalroute__timing__hold__ws": 0.0,
        "globalroute__timing__hold__tns": 0.0,
        "detailedroute__route__wirelength": 3000,
        "detailedroute__route__drc_errors": 0,
        "detailedroute__antenna__violating__nets": 2,
        "detailedroute__antenna_diodes_count": 3,
        "detailedroute__route__net": 500,
        "finish__timing__setup__ws": -0.1,
        "finish__timing__setup__tns": -2.0,
        "finish__timing__hold__ws": 0.05,
        "finish__timing__hold__tns": 0.0,
        "finish__design__instance__area": 800,
    }


class TestCommaList(unittest.TestCase):
    def test_all_returns_empty(self):
        self.assertEqual(genRuleFile.comma_separated_list("all"), [])

    def test_none_returns_empty(self):
        self.assertEqual(genRuleFile.comma_separated_list(None), [])

    def test_csv(self):
        self.assertEqual(genRuleFile.comma_separated_list("a,b,c"), ["a", "b", "c"])

    def test_whitespace_trimming(self):
        self.assertEqual(genRuleFile.comma_separated_list("a , b , c"), ["a", "b", "c"])


class TestGenRuleFile(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.metrics_file = os.path.join(self.tmp_dir.name, "metrics.json")
        self.rules_file = os.path.join(self.tmp_dir.name, "rules.json")
        self.new_rules_file = os.path.join(self.tmp_dir.name, "new_rules.json")

    def _run(self, metrics, old_rules=None, **kwargs):
        with open(self.metrics_file, "w") as f:
            json.dump(metrics, f)
        if old_rules is not None:
            with open(self.rules_file, "w") as f:
                json.dump(old_rules, f)
        defaults = dict(
            rules_file=self.rules_file,
            new_rules_file=self.new_rules_file,
            update=False,
            tighten=False,
            failing=False,
            variant="base",
            metrics_file=self.metrics_file,
            metrics_to_consider=[],
        )
        defaults.update(kwargs)
        genRuleFile.gen_rule_file(**defaults)
        with open(self.new_rules_file, "r") as f:
            return json.load(f)

    def test_direct_mode(self):
        metrics = make_base_metrics()
        rules = self._run(metrics, update=True)
        # detailedplace__design__violations uses direct mode
        self.assertEqual(rules["detailedplace__design__violations"]["value"], 0)
        self.assertEqual(rules["detailedplace__design__violations"]["compare"], "==")

    def test_direct_mode_drc_errors(self):
        metrics = make_base_metrics()
        metrics["detailedroute__route__drc_errors"] = 3
        rules = self._run(metrics, update=True)
        self.assertEqual(rules["detailedroute__route__drc_errors"]["value"], 3)

    def test_padding_mode_area(self):
        metrics = make_base_metrics()
        rules = self._run(metrics, update=True)
        # synth__design__instance__area__stdcell: padding=15, round_value=False
        # 500.0 * 1.15 = 575.0 -> 3 sig figs -> 575.0
        expected = float(f"{500.0 * 1.15:.3g}")
        self.assertEqual(
            rules["synth__design__instance__area__stdcell"]["value"], expected
        )

    def test_padding_mode_rounded(self):
        metrics = make_base_metrics()
        rules = self._run(metrics, update=True)
        # placeopt__design__instance__area: padding=15, round_value=True
        # 600 * 1.15 = 690.0 -> round -> 690
        self.assertEqual(rules["placeopt__design__instance__area"]["value"], 690)
        self.assertIsInstance(rules["placeopt__design__instance__area"]["value"], int)

    def test_padding_mode_wirelength(self):
        metrics = make_base_metrics()
        rules = self._run(metrics, update=True)
        # detailedroute__route__wirelength: padding=15, round_value=True
        # 3000 * 1.15 = 3450
        self.assertEqual(rules["detailedroute__route__wirelength"]["value"], 3450)

    def test_period_padding_negative_slack(self):
        metrics = make_base_metrics()
        # finish__timing__setup__ws = -0.1, period = 2.0, padding = 5
        # negative_slack = min(-0.1, 0) = -0.1
        # rule = -0.1 - max(-0.1 * 5/100, 2.0 * 5/100)
        #      = -0.1 - max(0.005, 0.1) = -0.1 - 0.1 = -0.2
        rules = self._run(metrics, update=True)
        self.assertAlmostEqual(
            rules["finish__timing__setup__ws"]["value"], -0.2, places=3
        )
        self.assertEqual(rules["finish__timing__setup__ws"]["compare"], ">=")

    def test_period_padding_zero_slack(self):
        metrics = make_base_metrics()
        # finish__timing__hold__ws = 0.05 (positive)
        # negative_slack = min(0.05, 0) = 0
        # rule = 0 - max(0 * 5/100, 2.0 * 5/100) = 0 - 0.1 = -0.1
        rules = self._run(metrics, update=True)
        self.assertAlmostEqual(
            rules["finish__timing__hold__ws"]["value"], -0.1, places=3
        )

    def test_period_padding_tns(self):
        metrics = make_base_metrics()
        # finish__timing__setup__tns = -2.0, period = 2.0, padding = 20
        # negative_slack = min(-2.0, 0) = -2.0
        # rule = -2.0 - max(-2.0 * 20/100, 2.0 * 20/100)
        #      = -2.0 - max(0.4, 0.4) = -2.0 - 0.4 = -2.4
        rules = self._run(metrics, update=True)
        self.assertAlmostEqual(
            rules["finish__timing__setup__tns"]["value"], -2.4, places=3
        )

    def test_metric_mode_antenna_diodes(self):
        metrics = make_base_metrics()
        rules = self._run(metrics, update=True)
        # globalroute__antenna_diodes_count: mode=metric, padding=0.1,
        #   metric=globalroute__route__net (500), min_max=max, min_max_direct=100
        # rule = 500 * 0.1 / 100 = 0.5 -> max(0.5, 100) = 100
        self.assertEqual(rules["globalroute__antenna_diodes_count"]["value"], 100)

    def test_cts_buffer_min_threshold(self):
        metrics = make_base_metrics()
        rules = self._run(metrics, update=True)
        # cts__design__instance__count__setup_buffer: mode=metric, padding=10,
        #   metric=placeopt__design__instance__count__stdcell (400)
        # rule_value = 400 * 10 / 100 = 40
        # special: max(40, 20 * 1.1) = max(40, 22) = 40
        self.assertEqual(
            rules["cts__design__instance__count__setup_buffer"]["value"], 40
        )

    def test_cts_buffer_uses_metric_times_1_1(self):
        metrics = make_base_metrics()
        # Set placeopt stdcell count low so metric mode gives small value
        metrics["placeopt__design__instance__count__stdcell"] = 10
        metrics["cts__design__instance__count__setup_buffer"] = 50
        rules = self._run(metrics, update=True)
        # rule_value = 10 * 10 / 100 = 1
        # special: max(1, 50 * 1.1) = max(1, 55) = 55
        self.assertEqual(
            rules["cts__design__instance__count__setup_buffer"]["value"], 55
        )

    def test_round_value_true_produces_int(self):
        metrics = make_base_metrics()
        rules = self._run(metrics, update=True)
        self.assertIsInstance(
            rules["placeopt__design__instance__count__stdcell"]["value"], int
        )

    def test_round_value_false_produces_float(self):
        metrics = make_base_metrics()
        rules = self._run(metrics, update=True)
        self.assertIsInstance(
            rules["synth__design__instance__area__stdcell"]["value"], float
        )

    def test_wildcard_warnings_match(self):
        metrics = make_base_metrics()
        # The wildcard pattern "*flow__warnings__count:*" matches keys with
        # colons. The code then replaces ":" with "__" for the output key but
        # looks up the replaced name in metrics, so we provide both forms.
        metrics["1_synth__flow__warnings__count:default"] = 5
        metrics["1_synth__flow__warnings__count__default"] = 5
        rules = self._run(metrics, update=True)
        key = "1_synth__flow__warnings__count__default"
        self.assertIn(key, rules)
        self.assertEqual(rules[key]["value"], 5)
        self.assertEqual(rules[key]["compare"], "<=")
        self.assertEqual(rules[key].get("level"), "warning")

    @patch("sys.stdout", new_callable=StringIO)
    def test_no_old_rules_file_warns(self, mock_stdout):
        metrics = make_base_metrics()
        self._run(metrics, update=True)
        self.assertIn("[WARNING] No old rules file found", mock_stdout.getvalue())

    def test_tighten_updates_when_tighter(self):
        metrics = make_base_metrics()
        old_rules = {
            "detailedroute__route__wirelength": {"value": 5000, "compare": "<="},
        }
        rules = self._run(metrics, old_rules=old_rules, tighten=True)
        # New value 3450 is tighter than old 5000 for <=
        self.assertEqual(rules["detailedroute__route__wirelength"]["value"], 3450)

    def test_tighten_keeps_old_when_not_tighter(self):
        metrics = make_base_metrics()
        old_rules = {
            "detailedroute__route__wirelength": {"value": 3000, "compare": "<="},
        }
        rules = self._run(metrics, old_rules=old_rules, tighten=True)
        # New value 3450 is NOT tighter than old 3000 for <=, keep old
        self.assertEqual(rules["detailedroute__route__wirelength"]["value"], 3000)

    def test_failing_updates_when_metric_fails(self):
        metrics = make_base_metrics()
        metrics["detailedroute__route__wirelength"] = 6000
        old_rules = {
            "detailedroute__route__wirelength": {"value": 5000, "compare": "<="},
        }
        rules = self._run(metrics, old_rules=old_rules, failing=True)
        # metric 6000 fails old rule (6000 <= 5000 is false), so update
        # new value = 6000 * 1.15 = 6900
        self.assertEqual(rules["detailedroute__route__wirelength"]["value"], 6900)

    def test_failing_keeps_old_when_passing(self):
        metrics = make_base_metrics()
        metrics["detailedroute__route__wirelength"] = 4000
        old_rules = {
            "detailedroute__route__wirelength": {"value": 5000, "compare": "<="},
        }
        rules = self._run(metrics, old_rules=old_rules, failing=True)
        # metric 4000 passes old rule (4000 <= 5000), keep old
        self.assertEqual(rules["detailedroute__route__wirelength"]["value"], 5000)

    def test_update_always_changes(self):
        metrics = make_base_metrics()
        old_rules = {
            "detailedroute__route__wirelength": {"value": 9999, "compare": "<="},
        }
        rules = self._run(metrics, old_rules=old_rules, update=True)
        self.assertEqual(rules["detailedroute__route__wirelength"]["value"], 3450)

    @patch("sys.stdout", new_callable=StringIO)
    def test_string_metric_skipped(self, mock_stdout):
        metrics = make_base_metrics()
        metrics["detailedplace__design__violations"] = "N/A"
        rules = self._run(metrics, update=True)
        self.assertIn("[WARNING] Skipping string field", mock_stdout.getvalue())
        self.assertNotIn("detailedplace__design__violations", rules)

    @patch("sys.stdout", new_callable=StringIO)
    def test_missing_clocks_details_warns(self, mock_stdout):
        metrics = make_base_metrics()
        # metrics.get() returns None when key is absent; the code checks
        # truthiness so both None and [] trigger the warning.
        metrics["constraints__clocks__details"] = []
        rules = self._run(metrics, update=True)
        self.assertIn(
            "'constraints__clocks__details' not found", mock_stdout.getvalue()
        )

    @patch("sys.stdout", new_callable=StringIO)
    def test_multiple_clocks_warns(self, mock_stdout):
        metrics = make_base_metrics()
        metrics["constraints__clocks__details"] = [
            "clk1: 2.0",
            "clk2: 5.0",
        ]
        self._run(metrics, update=True)
        self.assertIn("Multiple clocks not supported", mock_stdout.getvalue())

    def test_metrics_to_consider_preserves_others(self):
        metrics = make_base_metrics()
        old_rules = {
            "detailedroute__route__wirelength": {"value": 9999, "compare": "<="},
            "finish__design__instance__area": {"value": 7777, "compare": "<="},
        }
        rules = self._run(
            metrics,
            old_rules=old_rules,
            update=True,
            metrics_to_consider=["detailedroute__route__wirelength"],
        )
        # wirelength is in the consider list, so it should be updated
        self.assertEqual(rules["detailedroute__route__wirelength"]["value"], 3450)
        # finish area is NOT in the consider list, so old value preserved
        self.assertEqual(rules["finish__design__instance__area"]["value"], 7777)

    def test_clocks_count_direct(self):
        metrics = make_base_metrics()
        rules = self._run(metrics, update=True)
        self.assertEqual(rules["constraints__clocks__count"]["value"], 1)
        self.assertEqual(rules["constraints__clocks__count"]["compare"], "==")

    def test_compare_operators(self):
        metrics = make_base_metrics()
        rules = self._run(metrics, update=True)
        self.assertEqual(
            rules["synth__design__instance__area__stdcell"]["compare"], "<="
        )
        self.assertEqual(rules["finish__timing__setup__ws"]["compare"], ">=")

    def tearDown(self):
        self.tmp_dir.cleanup()


if __name__ == "__main__":
    unittest.main()
