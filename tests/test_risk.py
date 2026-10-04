import unittest
from decimal import Decimal as D

from trad3r.risk import Mark, Policy, assess, planned_long_loss


class RiskTests(unittest.TestCase):
    def test_agreed_nine_cumulative_examples(self):
        examples = [
            ("1000", "0", "0", "0", False),
            ("700.01", "0", "0", "-299.99", False),
            ("700", "0", "0", "-300", True),
            ("695", "0", "0", "-305", True),
            ("900", "0", "0", "-100", False),
            ("900", "200", "0", "-300", True),
            ("700", "0", "100", "-200", False),
            ("600", "0", "100", "-300", True),
            ("1100", "200", "100", "0", False),
        ]
        for equity, deposits, withdrawals, pnl, halted in examples:
            with self.subTest(equity=equity, deposits=deposits, withdrawals=withdrawals):
                result = assess(Mark(equity, deposits, withdrawals), Mark("1000"), Mark("1000"))
                self.assertEqual(result.cumulative_pnl, D(pnl))
                self.assertEqual("overall" in result.halt_reasons, halted)

    def test_exact_daily_and_weekly_thresholds(self):
        result = assess(Mark("975"), Mark("985"), Mark("1000"))
        self.assertEqual(result.halt_reasons, ("daily", "weekly"))
        self.assertEqual(result.daily_pnl, D("-10"))
        self.assertEqual(result.weekly_pnl, D("-25"))

    def test_just_above_period_thresholds(self):
        result = assess(Mark("975.01"), Mark("985"), Mark("1000"))
        self.assertEqual(result.halt_reasons, ())

    def test_flows_are_adjusted_relative_to_each_period(self):
        # £100 deposit and £20 withdrawal after baseline: actual loss is £10.
        result = assess(Mark("1270", "300", "20"), Mark("1200", "200"), Mark("1200", "200"))
        self.assertEqual(result.daily_pnl, D("-10"))
        self.assertEqual(result.cumulative_pnl, D("-10"))

    def test_recovery_cannot_clear_latched_stop(self):
        result = assess(Mark("1200"), Mark("1200"), Mark("1200"), ("overall", "daily"))
        self.assertEqual(result.halt_reasons, ("daily", "overall"))

    def test_bad_numeric_inputs_are_rejected(self):
        for value in (float("nan"), 1.5, True, "NaN", "Infinity"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                Mark(value)
        with self.assertRaises(ValueError):
            Mark("1000", "-1")
        with self.assertRaises(ValueError):
            Policy(trade_loss="0")
        with self.assertRaises(ValueError):
            assess(Mark("1000"), Mark("1000", "1"), Mark("1000"))

    def test_planned_loss_includes_costs(self):
        loss = planned_long_loss(2, D("100"), D("99"), D("0.8"), D("1.4"))
        self.assertEqual(loss, Policy().trade_loss)
        self.assertGreater(planned_long_loss(3, D("100"), D("99"), D("0.8"), D("1.4")), Policy().trade_loss)

    def test_whole_shares_and_long_stop_required(self):
        for quantity in (0, -1, True, D("0.5")):
            with self.assertRaises(ValueError):
                planned_long_loss(quantity, D("100"), D("99"), D("0.8"), D("1"))
        with self.assertRaises(ValueError):
            planned_long_loss(1, D("100"), D("101"), D("0.8"), D("1"))


if __name__ == "__main__":
    unittest.main()
