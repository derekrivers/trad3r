import contextlib
from decimal import Decimal as D
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from zipfile import ZipFile

from trad3r.__main__ import main
from trad3r import experiments as e
from trad3r.data import decode
from test_preparation import sample, assumptions


class ExperimentTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.archive, self.assumptions, self.registration, self.output = (
            self.root/n for n in ("source.zip", "costs.json", "registration.json", "result.zip"))
        sample(self.archive)
        self.assumptions.write_text(json.dumps(assumptions()))

    def register(self):
        return e.register_experiment(self.archive, self.assumptions, self.registration,
                                     experiment_id="synthetic-aapl-v1", symbol="AAA", start="2026-09-08", end="2026-09-09")

    def run_experiment(self):
        return e.run_experiment(self.registration, self.archive, self.assumptions, self.output)

    def test_registration_is_read_only_for_outcomes_and_pins_all_inputs(self):
        with patch.object(e, "baseline_backtest") as simulate:
            report = self.register()
        simulate.assert_not_called()
        registered = decode(self.registration.read_bytes())
        self.assertEqual(registered["source_sha256"], e.digest(self.archive.read_bytes()))
        self.assertEqual(registered["assumptions_sha256"], e.digest(self.assumptions.read_bytes()))
        self.assertEqual(registered["code_sha256"], e.code_fingerprint())
        self.assertEqual(registered["policy"]["overall_loss"], "300")
        self.assertEqual(report["registration_sha256"], e.digest(self.registration.read_bytes()))
        self.assertFalse(self.output.exists())
        with self.assertRaisesRegex(ValueError, "already exists"):
            self.register()

    def test_result_bundle_replays_both_accounts_and_matches_inspection(self):
        self.register()
        report = self.run_experiment()
        verified = e.inspect_experiment(self.output)
        self.assertEqual(e.canonical({k: v for k, v in report.items() if k != "output"}), e.canonical(verified))
        self.assertEqual(verified["evaluation"]["closed_trades"], 2)
        self.assertEqual(D(verified["evaluation"]["net_account_pnl_gbp"]), D("-1.76"))
        self.assertEqual(verified["reconciliation"], "verified")
        self.assertFalse(verified["research_ready"])
        with ZipFile(self.output) as archive:
            self.assertEqual(set(archive.namelist()), e.PAYLOADS | {"run_manifest.json"})
            self.assertEqual(archive.read("registration.json"), self.registration.read_bytes())
            result = decode(archive.read("result.json"))
            self.assertEqual(result["cash_reference"]["evaluation"]["closed_trades"], 0)
            self.assertEqual(sum(event["type"] == "fund" for event in result["ledger_events"]), 1)

    def test_code_archive_costs_and_registered_policy_changes_fail_before_simulation(self):
        self.register()
        with patch.object(e, "code_fingerprint", return_value="0"*64), patch.object(e, "baseline_backtest") as simulate:
            with self.assertRaisesRegex(ValueError, "Code differs"):
                self.run_experiment()
            simulate.assert_not_called()
        original_costs = self.assumptions.read_bytes()
        self.assumptions.write_bytes(original_costs+b" ")
        with patch.object(e, "baseline_backtest") as simulate:
            with self.assertRaisesRegex(ValueError, "differ from registration"):
                self.run_experiment()
            simulate.assert_not_called()
        self.assumptions.write_bytes(original_costs)
        with ZipFile(self.archive, "a") as archive:
            archive.comment = b"New archive identity"
        with self.assertRaisesRegex(ValueError, "differ from registration"):
            self.run_experiment()
        registration = decode(self.registration.read_bytes())
        registration["policy"]["overall_loss"] = "500"
        self.registration.write_bytes(e.canonical(registration))
        with self.assertRaisesRegex(ValueError, "changed risk"):
            self.run_experiment()
        self.assertFalse(self.output.exists())

    def test_existing_result_is_preserved_without_running_again(self):
        self.register()
        self.run_experiment()
        before = self.output.read_bytes()
        with patch.object(e, "baseline_backtest") as simulate:
            with self.assertRaisesRegex(ValueError, "already exists"):
                self.run_experiment()
            simulate.assert_not_called()
        self.assertEqual(self.output.read_bytes(), before)

    def test_interrupted_simulation_does_not_publish_a_success_bundle(self):
        self.register()
        with patch.object(e, "baseline_backtest", side_effect=KeyboardInterrupt), self.assertRaises(KeyboardInterrupt):
            self.run_experiment()
        self.assertFalse(self.output.exists())

    def rewrite_bundle(self, change, rehash=False):
        with ZipFile(self.output) as archive:
            files = {n: archive.read(n) for n in archive.namelist()}
        change(files)
        if rehash:
            manifest = decode(files["run_manifest.json"])
            for entry in manifest["files"]:
                entry.update(bytes=len(files[entry["file"]]), sha256=e.digest(files[entry["file"]]))
            files["run_manifest.json"] = e.canonical(manifest)
        with ZipFile(self.output, "w") as archive:
            for name, raw in files.items():
                archive.writestr(name, raw)

    def test_checksum_changes_and_rehashed_false_metrics_are_rejected(self):
        self.register()
        self.run_experiment()
        original = self.output.read_bytes()
        self.rewrite_bundle(lambda files: files.update({"summary.json": b"{}"}))
        with self.assertRaisesRegex(ValueError, "checksum"):
            e.inspect_experiment(self.output)
        self.output.write_bytes(original)
        def change_metrics(files):
            result = decode(files["result.json"])
            result["evaluation"]["net_account_pnl_gbp"] = "999"
            files["result.json"] = e.canonical(result)
        self.rewrite_bundle(change_metrics, rehash=True)
        with self.assertRaisesRegex(ValueError, "metrics do not reconcile"):
            e.inspect_experiment(self.output)
        self.output.write_bytes(original)
        def change_ledger(files):
            result = decode(files["result.json"])
            result["final_ledger"]["equity_gbp"] = "9999"
            files["result.json"] = e.canonical(result)
        self.rewrite_bundle(change_ledger, rehash=True)
        with self.assertRaisesRegex(ValueError, "ledger does not reconcile"):
            e.inspect_experiment(self.output)

    def test_extra_bundle_member_and_backdated_completion_rejected(self):
        self.register()
        self.run_experiment()
        original = self.output.read_bytes()
        with ZipFile(self.output, "a") as archive:
            archive.writestr("unexpected.json", "{}")
        with self.assertRaisesRegex(ValueError, "inventory"):
            e.inspect_experiment(self.output)
        self.output.write_bytes(original)
        def change_time(files):
            result = decode(files["result.json"])
            result["completed_at"] = "2000-01-01T00:00:00Z"
            files["result.json"] = e.canonical(result)
        self.rewrite_bundle(change_time, rehash=True)
        with self.assertRaisesRegex(ValueError, "precedes registration"):
            e.inspect_experiment(self.output)

    def test_inconsistent_halt_history_rejected_even_after_payload_rehash(self):
        self.register()
        self.run_experiment()
        def lose_halt(files):
            result = decode(files["result.json"])
            result["sessions"][0]["halt_reasons"] = ["overall"]
            files["result.json"] = e.canonical(result)
        self.rewrite_bundle(lose_halt, rehash=True)
        with self.assertRaisesRegex(ValueError, "lost a halt"):
            e.inspect_experiment(self.output)

    def test_rehashed_cash_comparison_and_strategy_metadata_corruption_rejected(self):
        self.register()
        self.run_experiment()
        original = self.output.read_bytes()
        def wrong_comparison(files):
            result = decode(files["result.json"])
            result["comparison"]["net_account_pnl_difference_gbp"] = "999"
            files["result.json"] = e.canonical(result)
        self.rewrite_bundle(wrong_comparison, rehash=True)
        with self.assertRaisesRegex(ValueError, "cash comparison"):
            e.inspect_experiment(self.output)
        self.output.write_bytes(original)
        def wrong_strategy(files):
            result = decode(files["result.json"])
            result["strategy_id"] = "different-strategy"
            files["result.json"] = e.canonical(result)
        self.rewrite_bundle(wrong_strategy, rehash=True)
        with self.assertRaisesRegex(ValueError, "execution metadata"):
            e.inspect_experiment(self.output)

    def test_registration_run_inspection_cli(self):
        commands = [
            ["register-experiment", str(self.archive), str(self.assumptions), "--id", "cli-example", "--symbol", "AAA",
             "--start", "2026-09-08", "--end", "2026-09-09", "--output", str(self.registration)],
            ["run-experiment", str(self.registration), str(self.archive), str(self.assumptions), "--output", str(self.output)],
            ["inspect-experiment", str(self.output)],
        ]
        for command in commands:
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(main(command), 0)
        self.registration.write_text("{}")
        with contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(main(commands[1]), 2)
