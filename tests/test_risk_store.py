from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
import contextlib
import io
import json
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import unittest

from trad3r import risk_store as store
from trad3r.__main__ import main
from trad3r.ledger import replay_ledger
from trad3r.data import decode


class RiskStoreTests(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.TemporaryDirectory()
        self.addCleanup(self.root.cleanup)
        self.path = Path(self.root.name) / 'risk.sqlite'
        store.initialize(self.path, '2026-09-04T13:30:00Z')

    def observation(self, identity='one', equity='990', at='2026-09-04T13:31:00Z', deposits='0', withdrawals='0'):
        return dict(id=identity, at=at, mark=dict(equity=equity, deposits=deposits, withdrawals=withdrawals))

    def test_halts_survive_fresh_process_and_recovery(self):
        result = store.record(self.path, self.observation(equity='700'), 0)
        self.assertEqual(result['blocked_reasons'], ['daily', 'overall', 'weekly'])
        raw = subprocess.check_output([sys.executable, '-m', 'trad3r', 'risk-status', str(self.path)], text=True)
        self.assertEqual(json.loads(raw)['blocked_reasons'], result['blocked_reasons'])
        after = store.record(self.path, self.observation('two', '1200', '2026-09-04T13:32:00Z'), 1)
        self.assertEqual(after['blocked_reasons'], result['blocked_reasons'])
        self.assertFalse(after['live_trading_enabled'])
        self.assertEqual(len(store.history(self.path)), 2)

    def test_new_period_never_renews_budget(self):
        store.record(self.path, self.observation(equity='995'), 0)
        next_day = store.record(self.path, self.observation('two', '989', '2026-09-08T13:31:00Z'), 1)
        self.assertEqual(next_day['blocked_reasons'], ['daily', 'period_review_required'])
        self.assertEqual(str(next_day['assessment']['daily_pnl']), '-11')
        self.assertEqual(next_day['baseline_session'], '2026-09-04')
        self.assertEqual(next_day['baseline_week'], '2026-08-31')

    def test_healthy_new_period_still_requires_review(self):
        result = store.record(self.path, self.observation(equity='1001', at='2026-09-08T13:31:00Z'), 0)
        self.assertEqual(result['blocked_reasons'], ['period_review_required'])

    def test_deposits_cannot_erase_loss(self):
        result = store.record(self.path, self.observation(equity='900', deposits='200'), 0)
        self.assertIn('overall', result['blocked_reasons'])
        self.assertEqual(str(result['assessment']['cumulative_pnl']), '-300')

    def test_flow_counters_checked_against_latest_not_just_initial_baseline(self):
        store.record(self.path, self.observation(equity='1200', deposits='200'), 0)
        before = store.status(self.path)
        with self.assertRaisesRegex(ValueError, 'backwards'):
            store.record(self.path, self.observation('two', '1100', '2026-09-04T13:32:00Z', '100'), 1)
        self.assertEqual(store.status(self.path), before)
        self.assertEqual(len(store.history(self.path)), 1)

    def test_missing_file_is_not_reinitialised(self):
        path = Path(self.root.name) / 'typo.sqlite'
        with self.assertRaises(sqlite3.Error):
            store.status(path)
        with self.assertRaises(sqlite3.Error):
            store.record(path, self.observation(), 0)
        self.assertFalse(path.exists())

    def test_existing_database_cannot_be_reinitialised(self):
        store.record(self.path, self.observation(), 0)
        with self.assertRaises(FileExistsError):
            store.initialize(self.path, '2026-09-08T13:30:00Z')
        self.assertTrue(store.status(self.path)['blocked'])

    def test_stale_duplicate_and_changed_version_rejected_without_writes(self):
        store.record(self.path, self.observation(), 0)
        before = store.status(self.path)
        cases = [(self.observation('two', at='2026-09-04T13:30:00Z'), 1),
                 (self.observation('one', at='2026-09-04T13:32:00Z'), 1),
                 (self.observation('two', at='2026-09-04T13:32:00Z'), 0)]
        for observation, version in cases:
            with self.assertRaises(ValueError):
                store.record(self.path, observation, version)
            self.assertEqual(store.status(self.path), before)
            self.assertEqual(len(store.history(self.path)), 1)

    def test_failed_state_update_rolls_back_audit_insert(self):
        connection = sqlite3.connect(self.path)
        connection.execute("CREATE TRIGGER fail_update BEFORE UPDATE ON state BEGIN SELECT RAISE(ABORT, 'injected write failure'); END")
        connection.commit()
        connection.close()
        with self.assertRaises(sqlite3.Error):
            store.record(self.path, self.observation(), 0)
        self.assertEqual(store.status(self.path)['version'], 0)
        self.assertEqual(store.history(self.path), [])

    def test_concurrent_writers_cannot_overwrite_each_other(self):
        def write(identity):
            try:
                store.record(self.path, self.observation(identity), 0)
                return 'committed'
            except ValueError as error:
                self.assertIn('version changed', str(error))
                return 'rejected'
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(write, ['one', 'two']))
        self.assertCountEqual(results, ['committed', 'rejected'])
        self.assertEqual(store.status(self.path)['version'], 1)
        self.assertEqual(len(store.history(self.path)), 1)

    def test_unknown_policy_or_database_schema_fails_closed(self):
        connection = sqlite3.connect(self.path)
        payload = json.loads(connection.execute('SELECT payload FROM state').fetchone()[0])
        payload['policy']['overall_loss'] = '500'
        connection.execute('UPDATE state SET payload=?', (json.dumps(payload),))
        connection.commit()
        connection.close()
        with self.assertRaisesRegex(ValueError, 'policy differs'):
            store.status(self.path)
        self.path.write_bytes(b'corrupted database')
        with self.assertRaises(sqlite3.Error):
            store.status(self.path)

    def test_cli_reports_bad_observation_without_success_output(self):
        p = Path(self.root.name) / 'observation.json'
        bad = self.observation()
        del bad['mark']['deposits']
        p.write_text(json.dumps(bad))
        out = io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(main(['risk-record', str(self.path), str(p), '--expected-version', '0']), 2)
        self.assertEqual(out.getvalue(), '')
        self.assertEqual(store.status(self.path)['version'], 0)

    def test_ledger_import_uses_total_equity_including_conversion_fees(self):
        events = decode(Path('examples/ledger.json').read_bytes())
        events[1]['fee_gbp'] = '10'
        events[3]['price'] = '90'
        valuation = replay_ledger(events)
        self.assertEqual(str(valuation['realised_trade_pnl_gbp']), '-17.6')
        self.assertEqual(str(valuation['account_pnl_gbp']), '-27.6')
        p = Path(self.root.name) / 'valuation.json'
        p.write_text(json.dumps(valuation, default=str))
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.assertEqual(main(['risk-record', str(self.path), str(p),
                                   '--expected-version', '0', '--ledger-report', '--event-id', 'ledger1']), 0)
        result = json.loads(out.getvalue())
        self.assertEqual(result['assessment']['cumulative_pnl'], '-27.6')
        self.assertEqual(result['blocked_reasons'], ['daily', 'weekly'])

    def test_audit_state_disagreement_is_not_silently_repaired(self):
        store.record(self.path, self.observation(), 0)
        with sqlite3.connect(self.path) as connection:
            connection.execute('DELETE FROM observations')
        connection.close()
        with self.assertRaisesRegex(ValueError, 'audit/state'):
            store.status(self.path)

    def test_recovered_equity_cannot_hide_a_changed_latch(self):
        store.record(self.path, self.observation(), 0)
        store.record(self.path, self.observation('two', '1000', '2026-09-04T13:32:00Z'), 1)
        with sqlite3.connect(self.path) as connection:
            payload = json.loads(connection.execute('SELECT payload FROM state').fetchone()[0])
            payload['halt_reasons'] = []
            connection.execute('UPDATE state SET payload=?', (json.dumps(payload),))
        connection.close()
        with self.assertRaisesRegex(ValueError, 'audit/state'):
            store.status(self.path)
