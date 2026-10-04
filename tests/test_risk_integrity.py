import contextlib
import io
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest

from trad3r import risk_store as store
from trad3r.__main__ import main


class RiskIntegrityTests(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.TemporaryDirectory()
        self.addCleanup(self.root.cleanup)
        self.path = Path(self.root.name)/"risk.sqlite"
        store.initialize(self.path, "2026-09-04T13:30:00Z")

    def seed(self, loss=True):
        for version, equity in enumerate(("700" if loss else "1000", "1200" if loss else "1000")):
            store.record(self.path, dict(id=f"obs-{version}", at=f"2026-09-04T13:3{version+1}:00Z",
                                        mark=dict(equity=equity, deposits="0", withdrawals="0")), version)

    def mutate_entry(self, version, change):
        with sqlite3.connect(self.path) as connection:
            entry = json.loads(connection.execute("SELECT payload FROM observations WHERE version=?", (version,)).fetchone()[0])
            change(entry)
            connection.execute("UPDATE observations SET payload=? WHERE version=?", (json.dumps(entry), version))
        connection.close()

    def test_earlier_mark_damage_detected_with_unchanged_latest_snapshot(self):
        self.seed()
        self.mutate_entry(1, lambda entry: entry["mark"].update(equity="1000"))
        with self.assertRaisesRegex(ValueError, "reconstructed result"):
            store.status(self.path)

    def test_earlier_result_damage_detected_by_status_and_history(self):
        self.seed()
        self.mutate_entry(1, lambda entry: entry["result"]["assessment"].update(daily_pnl="0"))
        for read in (store.status, store.history):
            with self.assertRaises(ValueError):
                read(self.path)

    def test_matching_latest_state_and_report_cannot_hide_earlier_halt(self):
        self.seed()
        with sqlite3.connect(self.path) as connection:
            state = json.loads(connection.execute("SELECT payload FROM state").fetchone()[0])
            state["halt_reasons"] = []
            connection.execute("UPDATE state SET payload=?", (store.pack(state),))
            entry = json.loads(connection.execute("SELECT payload FROM observations WHERE version=2").fetchone()[0])
            entry["result"] = store.report(state)
            connection.execute("UPDATE observations SET payload=? WHERE version=2", (store.pack(entry),))
        connection.close()
        with self.assertRaisesRegex(ValueError, "reconstructed result"):
            store.status(self.path)

    def test_sequence_hole_detected_even_when_row_count_and_latest_match(self):
        self.seed()
        with sqlite3.connect(self.path) as connection:
            connection.execute("UPDATE observations SET version=0 WHERE version=1")
        connection.close()
        with self.assertRaisesRegex(ValueError, "version sequence"):
            store.status(self.path)

    def test_sql_identity_must_match_payload_identity(self):
        self.seed()
        self.mutate_entry(1, lambda entry: entry.update(id="different"))
        with self.assertRaisesRegex(ValueError, "identity"):
            store.status(self.path)

    def test_old_observation_cannot_predate_funding_session(self):
        self.seed()
        self.mutate_entry(1, lambda entry: entry.update(at="2026-09-03T13:31:00Z"))
        with self.assertRaisesRegex(ValueError, "timestamps"):
            store.status(self.path)

    def test_full_replay_checks_external_flows_between_observations(self):
        self.seed(loss=False)
        def change(entry):
            entry["mark"].update(equity="1100", deposits="100")
            entry["result"]["mark"] = entry["mark"]
        self.mutate_entry(1, change)
        with self.assertRaisesRegex(ValueError, "flows went backwards"):
            store.status(self.path)

    def test_unobserved_initial_equity_change_fails_closed(self):
        with sqlite3.connect(self.path) as connection:
            state = json.loads(connection.execute("SELECT payload FROM state").fetchone()[0])
            state["latest"]["equity"] = "1200"
            connection.execute("UPDATE state SET payload=?", (store.pack(state),))
        connection.close()
        with self.assertRaisesRegex(ValueError, "reconstructed contents"):
            store.status(self.path)

    def test_bad_earlier_entry_blocks_append_without_partial_write_or_cli_success(self):
        self.seed()
        self.mutate_entry(1, lambda entry: entry.update(unexpected=True))
        before = self.path.read_bytes()
        observation = dict(id="third", at="2026-09-04T13:33:00Z",
                           mark=dict(equity="1200", deposits="0", withdrawals="0"))
        with self.assertRaises(ValueError):
            store.record(self.path, observation, 2)
        self.assertEqual(self.path.read_bytes(), before)
        out = io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(main(["risk-status", str(self.path)]), 2)
        self.assertEqual(out.getvalue(), "")

    def test_valid_v1_history_remains_compatible_without_migration(self):
        self.seed()
        before = self.path.read_bytes()
        self.assertEqual(store.status(self.path)["blocked_reasons"], ["daily", "overall", "weekly"])
        history = store.history(self.path)
        self.assertEqual(len(history), 2)
        self.assertEqual(history[-1]["result"], json.loads(store.pack(store.status(self.path))))
        self.assertEqual(self.path.read_bytes(), before)
