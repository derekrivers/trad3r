from copy import deepcopy
from decimal import Decimal as D
import unittest

from trad3r.evaluation import summarize_run
from trad3r.ledger import replay_ledger
from test_backtest import config, run


class EvaluationTests(unittest.TestCase):
    def test_whole_account_metrics_and_cash_reference_reconcile(self):
        result = run([config(), config("2026-09-09", False)])
        report = result["evaluation"]
        self.assertEqual(report["net_account_pnl_gbp"], D("-1.76"))
        self.assertEqual(report["net_account_return"], D("-0.00176"))
        self.assertEqual(report["max_observed_drawdown_gbp"], D("1.76"))
        self.assertEqual(report["max_observed_loss_from_initial_gbp"], D("1.76"))
        self.assertEqual(report["explicit_commissions_gbp"], D("1.60"))
        self.assertEqual(report["explicit_conversion_fees_gbp"], 0)
        self.assertEqual(report["entries"], 2)
        self.assertEqual(report["closed_trades"], 2)
        self.assertEqual(report["losing_trades"], 2)
        self.assertEqual(report["trade_win_fraction"], 0)
        self.assertEqual(report["simulated_position_seconds"], 2*118*60)
        self.assertEqual(report["equity_curve"][-1]["equity_gbp"], result["final_ledger"]["equity_gbp"])
        reference = result["cash_reference"]
        self.assertEqual(replay_ledger(reference["ledger_events"]), reference["final_ledger"])
        self.assertEqual(reference["evaluation"]["net_account_pnl_gbp"], 0)
        self.assertEqual(result["comparison"]["net_account_pnl_difference_gbp"], D("-1.76"))

    def test_no_trades_uses_null_win_fraction_and_keeps_flat_sessions(self):
        result = run([config(crossing=False), config("2026-09-09", False, crossing=False)])
        report = result["evaluation"]
        self.assertEqual(report["sessions"], 2)
        self.assertEqual(report["no_candidate_sessions"], 2)
        self.assertEqual(report["closed_trades"], 0)
        self.assertIsNone(report["trade_win_fraction"])
        self.assertEqual(report["gross_turnover_gbp"], 0)
        self.assertEqual(result["comparison"]["net_account_pnl_difference_gbp"], 0)

    def test_rejected_candidates_are_not_reported_as_no_candidate_days(self):
        configs = [config(), config("2026-09-09", False)]
        for c in configs:
            c["costs"]["entry_fee_usd"] = "3"
        report = run(configs)["evaluation"]
        self.assertEqual(report["candidates"], 2)
        self.assertEqual(report["rejected_candidates"], 2)
        self.assertEqual(report["rejection_reason_counts"]["trade_loss_limit"], 2)
        self.assertEqual(report["no_candidate_sessions"], 0)
        self.assertEqual(report["explicit_commissions_gbp"], 0)

    def test_cash_reference_includes_same_fx_movement_and_conversion_fee(self):
        first = config(crossing=False)
        first["funding"]["fee_gbp"] = "1"
        result = run([first, config("2026-09-09", False, fx="0.79", crossing=False)])
        self.assertEqual(result["evaluation"]["net_account_pnl_gbp"], D(-6))
        self.assertEqual(result["cash_reference"]["evaluation"]["net_account_pnl_gbp"], D(-6))
        self.assertEqual(result["evaluation"]["explicit_conversion_fees_gbp"], D(1))
        self.assertEqual(result["comparison"]["net_account_pnl_difference_gbp"], 0)

    def test_account_fx_gain_is_not_misreported_as_a_winning_trade(self):
        report = run([config(), config("2026-09-09", False, fx="0.81")])["evaluation"]
        self.assertGreater(report["net_account_pnl_gbp"], 0)
        self.assertLess(report["realised_trade_pnl_gbp"], 0)
        self.assertEqual(report["winning_trades"], 0)
        self.assertEqual(report["losing_trades"], 2)

    def test_winning_trade_uses_net_fills_and_fees(self):
        first = config()
        first["bars"][33].update(h=107, c=106)
        report = run([first], end="2026-09-08")["evaluation"]
        self.assertEqual(report["winning_trades"], 1)
        self.assertEqual(report["trade_win_fraction"], 1)
        self.assertEqual(report["trades"][0]["realised_trade_pnl_gbp"], D("2.32"))
        self.assertEqual(report["exit_reason_counts"], {"target": 1})

    def test_drawdown_retains_temporary_loss_after_account_recovery(self):
        result = run([config(crossing=False), config("2026-09-09", False, fx="0.1", crossing=False),
                      config("2026-09-10", False, crossing=False)], end="2026-09-10")
        report = result["evaluation"]
        self.assertEqual(report["net_account_pnl_gbp"], 0)
        self.assertEqual(report["max_observed_drawdown_gbp"], D(350))
        self.assertEqual(report["max_observed_loss_from_initial_gbp"], D(350))
        self.assertEqual(report["sessions_blocked_at_end"], 2)

    def test_inconsistent_final_snapshot_is_rejected_not_summarized(self):
        result = run([config(), config("2026-09-09", False)])
        bad = deepcopy(result)
        bad["final_ledger"]["equity_gbp"] += 1
        with self.assertRaisesRegex(ValueError, "reconciled"):
            summarize_run(bad)
