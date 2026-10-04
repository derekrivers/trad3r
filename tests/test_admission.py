from copy import deepcopy
from dataclasses import asdict
from decimal import Decimal as D
import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest

from trad3r.admission import check_entry
from trad3r.ledger import Ledger
from trad3r.risk import Mark, assess
from trad3r import risk_store
from trad3r.__main__ import main


AT = "2026-09-04T14:00:00Z"


def setup_book(fee="0"):
    book = Ledger()
    events = [dict(id="fund", type="fund", at=AT, amount="1000"),
              dict(id="fx", type="exchange", at=AT, from_currency="GBP", amount="800",
                   received="1000", fee_gbp=fee),
              dict(id="value", type="value", at=AT, usd_to_gbp="0.8", prices={})]
    for event in events:
        book.apply(event)
    return book, events


def risk_for(book):
    value = book.last_report
    mark = Mark(value["equity_gbp"], value["deposits_gbp"], value["withdrawals_gbp"])
    assessment = assess(mark, Mark("1000"), Mark("1000"))
    return dict(mode="offline_risk_observations_only", live_trading_enabled=False,
                mark=asdict(mark), as_of=value["as_of"], baseline_session="2026-09-04",
                blocked=bool(assessment.halt_reasons), blocked_reasons=list(assessment.halt_reasons),
                assessment=asdict(assessment))


def proposal(**changes):
    result = dict(symbol="SYNTH", quantity=2, entry="100", stop="99", entry_fee_usd="0.5",
                  exit_fee_usd="0.5", slippage_usd_per_share="0.05", usd_to_gbp="0.8",
                  quote_at=AT, fx_at=AT)
    result.update(changes)
    return result


class AdmissionTests(unittest.TestCase):
    def setUp(self):
        self.book, self.events = setup_book()
        self.risk = risk_for(self.book)

    def check(self, request=None, **kwargs):
        return check_entry(self.book, self.risk, request or proposal(), kwargs.get("at", AT), kwargs.get("attempts", 0))

    def test_valid_entry_has_explicit_all_in_costs_and_no_mutation(self):
        before = deepcopy(self.book)
        result = self.check()
        self.assertTrue(result["eligible"])
        self.assertEqual(result["planned_loss_gbp"], D("2.56"))
        self.assertEqual(result["cash_required_usd"], D("201.10"))
        self.assertEqual(self.book, before)
        self.assertFalse(result["live_trading_enabled"])

    def test_exact_and_over_trade_risk_boundary(self):
        exact = proposal(stop="98.625", slippage_usd_per_share="0")
        self.assertTrue(self.check(exact)["eligible"])
        self.assertEqual(self.check(exact)["planned_loss_gbp"], D("3"))
        exact["stop"] = "98.6249"
        self.assertIn("trade_loss_limit", self.check(exact)["reasons"])

    def test_exact_and_over_exposure_boundary(self):
        exact = proposal(quantity=1, entry="625", stop="624", entry_fee_usd="0",
                         exit_fee_usd="0", slippage_usd_per_share="0")
        self.assertTrue(self.check(exact)["eligible"])
        exact["entry"] = "625.01"
        self.assertIn("exposure_limit", self.check(exact)["reasons"])

    def test_settled_cash_includes_exit_fee_reserve(self):
        def withdraw(identity, amount):
            self.book.apply(dict(id=identity, type="withdraw", at=AT, currency="USD", amount=amount, usd_to_gbp="0.8"))
            self.book.apply(dict(id=identity+"-value", type="value", at=AT, usd_to_gbp="0.8", prices={}))
            self.risk = risk_for(self.book)
        withdraw("withdraw-1", "798.90")
        self.assertTrue(self.check()["eligible"])
        withdraw("withdraw-2", "0.01")
        self.assertIn("insufficient_settled_cash", self.check()["reasons"])

    def test_headroom_uses_account_loss_not_just_trade_limit(self):
        self.book, _ = setup_book("9")
        self.risk = risk_for(self.book)
        self.assertFalse(self.risk["blocked"])
        self.assertIn("daily_loss_headroom", self.check()["reasons"])

    def test_latched_stop_and_period_change_block(self):
        self.risk.update(blocked=True, blocked_reasons=["overall"])
        self.assertIn("risk_blocked", self.check()["reasons"])
        self.assertIn("period_review_required", self.check(at="2026-09-08T14:00:00Z")["reasons"])

    def test_attempt_limit_and_invalid_counts(self):
        for attempts in (0, 1, 2):
            self.assertTrue(self.check(attempts=attempts)["eligible"])
        self.assertIn("entry_attempt_limit", self.check(attempts=3)["reasons"])
        for attempts in (-1, True, 0.5):
            with self.assertRaises(ValueError):
                self.check(attempts=attempts)

    def test_existing_position_blocks_same_symbol_addition(self):
        self.book.apply(dict(id="buy", type="buy", at=AT, symbol="SYNTH", quantity=1,
                             price="100", fee_usd="0", usd_to_gbp="0.8"))
        self.book.apply(dict(id="value2", type="value", at=AT, prices={"SYNTH":"100"}, usd_to_gbp="0.8"))
        self.risk = risk_for(self.book)
        self.assertIn("position_already_open", self.check()["reasons"])

    def test_stale_future_and_mismatched_snapshots(self):
        self.assertTrue(self.check(at="2026-09-04T14:01:00Z")["eligible"])
        self.assertIn("valuation_stale_or_future", self.check(at="2026-09-04T14:01:01Z")["reasons"])
        self.assertIn("quote_stale_or_future", self.check(proposal(quote_at="2026-09-04T14:00:01Z"))["reasons"])
        self.assertIn("fx_stale_or_future", self.check(proposal(fx_at="2026-09-04T13:58:00Z"))["reasons"])
        with self.assertRaisesRegex(ValueError, "FX"):
            self.check(proposal(usd_to_gbp="0.9"))
        self.risk["mark"]["equity"] = "999"
        with self.assertRaisesRegex(ValueError, "observations"):
            self.check()

    def test_entry_window_is_exclusive_at_1130_new_york(self):
        self.assertIn("outside_entry_window", self.check(at="2026-09-04T15:30:00Z")["reasons"])
        self.assertIn("outside_entry_window", self.check(at="2026-09-04T13:59:59Z")["reasons"])

    def test_bad_numeric_inputs_and_missing_costs_rejected(self):
        for changes in (dict(quantity=0.5), dict(quantity=True), dict(entry="NaN"),
                        dict(stop="100"), dict(entry_fee_usd="-1"), dict(usd_to_gbp="Infinity")):
            with self.assertRaises(ValueError):
                self.check(proposal(**changes))
        request = proposal()
        del request["exit_fee_usd"]
        with self.assertRaises(ValueError):
            self.check(request)

    def test_cli_reads_database_without_reserving_or_writing(self):
        with tempfile.TemporaryDirectory() as root:
            root = Path(root)
            db, events, request = root/"risk.sqlite", root/"events.json", root/"request.json"
            risk_store.initialize(db, "2026-09-04T13:59:00Z")
            risk_store.record(db, risk_store.from_ledger("one", self.book.last_report), 0)
            events.write_text(json.dumps(self.events))
            request.write_text(json.dumps(proposal()))
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                self.assertEqual(main(["entry-check", str(db), str(events), str(request),
                                       "--at", AT, "--attempts", "0"]), 0)
            self.assertTrue(json.loads(out.getvalue())["eligible"])
            self.assertEqual(risk_store.status(db)["version"], 1)
