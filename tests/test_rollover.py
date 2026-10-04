from copy import deepcopy
from decimal import Decimal as D
import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest

from trad3r.__main__ import main
from trad3r import risk_store
from trad3r.data import decode, parse_bar
from trad3r.ledger import replay_ledger
from trad3r.simulation import ROLLOVER_POLICY, simulate_research_series
from test_series import session, run as ordinary_run


def run(configs, start=None, end=None, strategy_id="synthetic-scenarios-v1"):
    configs = decode(json.dumps(configs))
    pairs = [([parse_bar(row, config["symbol"]) for row in config["bars"]], config) for config in configs]
    return simulate_research_series(pairs, start or configs[0]["session"], end or configs[-1]["session"], strategy_id=strategy_id)


class RolloverTests(unittest.TestCase):
    def test_same_week_renews_only_daily_baseline_and_retains_one_account(self):
        configs = [session("2026-09-08", True), session("2026-09-09")]
        before = deepcopy(configs)
        result = run(configs)
        self.assertEqual(configs, before)
        first, second = result["sessions"]
        self.assertEqual(second["session_start"]["equity"], first["final_ledger"]["equity_gbp"])
        self.assertEqual(second["week_start"]["equity"], D(1000))
        self.assertEqual(second["assessment"]["daily_pnl"], D("-0.96"))
        self.assertEqual(second["assessment"]["weekly_pnl"], D("-1.92"))
        self.assertEqual(second["assessment"]["cumulative_pnl"], D("-1.92"))
        self.assertEqual(result["transitions"][0]["decision"], "applied")
        self.assertEqual(sum(e["type"] == "fund" for e in result["ledger_events"]), 1)
        self.assertEqual(sum(e["type"] == "exchange" for e in result["ledger_events"]), 1)
        self.assertEqual(replay_ledger(result["ledger_events"]), result["final_ledger"])
        self.assertEqual(result["rollover_policy"], ROLLOVER_POLICY)
        self.assertFalse(result["live_trading_enabled"])

    def test_new_week_renews_period_marks_but_never_cumulative_loss_basis(self):
        result = run([session("2026-09-04", True), session("2026-09-08")])
        first, second = result["sessions"]
        self.assertEqual(second["session_start"], second["week_start"])
        self.assertEqual(second["session_start"]["equity"], first["final_ledger"]["equity_gbp"])
        self.assertEqual(second["assessment"]["weekly_pnl"], D("-0.96"))
        self.assertEqual(second["assessment"]["cumulative_pnl"], D("-1.92"))
        self.assertEqual(second["baseline_week"], "2026-09-07")

    def test_unsettled_proceeds_cannot_be_spent_again_after_rollover(self):
        configs = [session("2026-09-08", True), session("2026-09-09"), session("2026-09-10")]
        configs[0]["funding"].update(amount="200", received="250")
        result = run(configs)
        first, second, third = result["sessions"]
        self.assertEqual(first["final_ledger"]["unsettled_usd"], second["final_ledger"]["unsettled_usd"])
        check = next(e for e in second["trace"] if e["type"] == "entry_check")
        self.assertIn("insufficient_settled_cash", check["reasons"])
        self.assertFalse(any(e["type"] == "entry" for e in second["trace"]))
        self.assertTrue(any(e["type"] == "entry" for e in third["trace"]))

    def test_fresh_overnight_fx_loss_is_assessed_before_any_rollover(self):
        result = run([session("2026-09-04", True), session("2026-09-08", fx="0.1"), session("2026-09-09")])
        self.assertEqual(result["halt_reasons"], ["daily", "overall", "weekly"])
        self.assertTrue(all(t["decision"] == "blocked" and t["before"] == t["after"] for t in result["transitions"]))
        self.assertEqual(result["baseline_session"], "2026-09-04")
        self.assertEqual(result["final_ledger"]["account_pnl_gbp"], D("-0.96"))
        self.assertFalse(any(e["type"] == "entry" for s in result["sessions"][1:] for e in s["trace"]))

    def test_daily_halt_survives_week_change_and_recovered_equity(self):
        first = session("2026-09-04", True)
        first["bars"][3].update(o=90, h=91, l=89, c=90)
        result = run([first, session("2026-09-08", fx="0.84")])
        self.assertEqual(result["halt_reasons"], ["daily"])
        self.assertGreater(result["final_ledger"]["equity_gbp"], 1000)
        self.assertEqual(result["transitions"][0]["decision"], "blocked")
        self.assertEqual(result["transitions"][0]["before"], result["transitions"][0]["after"])

    def test_weekly_loss_accumulates_across_daily_rollovers_and_survives_next_week(self):
        configs = []
        for i, (day, fx) in enumerate(zip(("2026-09-14", "2026-09-15", "2026-09-16", "2026-09-17", "2026-09-18", "2026-09-21"),
                                         ("0.8", "0.786", "0.772", "0.758", "0.744", "0.8"))):
            config = session(day, i == 0, fx)
            config["signals"] = []
            configs.append(config)
        result = run(configs)
        self.assertEqual(result["halt_reasons"], ["weekly"])
        self.assertEqual(result["sessions"][4]["assessment"]["weekly_pnl"], D(-28))
        self.assertEqual(result["sessions"][4]["assessment"]["daily_pnl"], D(-7))
        self.assertEqual(result["baseline_session"], "2026-09-17")
        self.assertEqual(result["baseline_week"], "2026-09-14")
        self.assertEqual(result["transitions"][-1]["decision"], "blocked")
        self.assertEqual(result["final_ledger"]["equity_gbp"], D(1000))

    def test_durable_halted_account_is_never_read_or_modified_by_research_run(self):
        with tempfile.TemporaryDirectory() as root:
            path = Path(root)/"risk.sqlite"
            risk_store.initialize(path, "2026-09-04T13:30:00Z")
            risk_store.record(path, dict(id="loss", at="2026-09-04T13:31:00Z",
                                        mark=dict(equity="700", deposits="0", withdrawals="0")), 0)
            before = path.read_bytes()
            result = run([session("2026-09-08", True), session("2026-09-09")])
            self.assertEqual(result["halt_reasons"], [])
            self.assertEqual(path.read_bytes(), before)
            self.assertIn("overall", risk_store.status(path)["blocked_reasons"])

    def test_transition_record_references_the_pre_rollover_valuation(self):
        result = run([session("2026-09-08", True), session("2026-09-09")])
        transition = result["transitions"][0]
        event = next(e for e in result["ledger_events"] if e["id"] == transition["valuation_event_id"])
        self.assertEqual(event["type"], "value")
        self.assertEqual(event["at"], transition["at"])
        self.assertEqual(transition["assessed_before"]["daily_pnl"], D("-0.96"))
        self.assertEqual(transition["policy"], ROLLOVER_POLICY)

    def test_missing_sessions_are_reported_without_invented_observations(self):
        result = run([session("2026-09-08", True), session("2026-09-10")], "2026-09-04", "2026-09-11")
        self.assertEqual(result["missing_sessions"], ["2026-09-04", "2026-09-09", "2026-09-11"])
        self.assertEqual(len(result["sessions"]), 2)

    def test_explicit_window_and_all_inputs_are_bound_to_identity(self):
        configs = [session("2026-09-08", True), session("2026-09-09")]
        first = run(configs)
        self.assertEqual(first, run(configs))
        self.assertNotEqual(first["inputs_sha256"], run(configs, strategy_id="synthetic-scenarios-v2")["inputs_sha256"])
        self.assertNotEqual(first["inputs_sha256"], run(configs, end="2026-09-10")["inputs_sha256"])
        configs[1]["costs"]["exit_fee_usd"] = "0.6"
        self.assertNotEqual(first["inputs_sha256"], run(configs)["inputs_sha256"])

    def test_original_series_contract_keeps_its_period_block(self):
        result = ordinary_run([session("2026-09-08", True), session("2026-09-09")])
        self.assertEqual(result["blocked_reasons"], ["period_review_required"])
        self.assertNotIn("rollover_policy", result)

    def test_unsupported_outside_window_and_duplicate_sessions_rejected(self):
        config = session("2026-09-08", True)
        for configs, start, end in (([config], "2026-09-09", "2026-09-10"),
                                    ([config], "2026-09-08", "2027-01-01"),
                                    ([config, config], "2026-09-08", "2026-09-08")):
            with self.assertRaises(ValueError):
                run(configs, start, end)

    def test_cli_requires_window_and_rejects_bad_later_input_without_success(self):
        with tempfile.TemporaryDirectory() as root:
            path = Path(root)/"research.json"
            payload = dict(window=dict(start="2026-09-08", end="2026-09-09"), strategy_id="synthetic-scenarios-v1",
                           sessions=[session("2026-09-08", True), session("2026-09-09")])
            path.write_text(json.dumps(payload))
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                self.assertEqual(main(["simulate-research-series", str(path)]), 0)
            self.assertEqual(json.loads(out.getvalue())["rollover_policy"], ROLLOVER_POLICY)
            for kind in ("fx", "funding", "window", "strategy_id"):
                bad = deepcopy(payload)
                if kind == "fx":
                    bad["sessions"][1]["fx"] = []
                elif kind == "funding":
                    bad["sessions"][1]["funding"] = bad["sessions"][0]["funding"]
                else:
                    del bad[kind]
                path.write_text(json.dumps(bad))
                out = io.StringIO()
                with contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
                    self.assertEqual(main(["simulate-research-series", str(path)]), 2)
                self.assertEqual(out.getvalue(), "")
