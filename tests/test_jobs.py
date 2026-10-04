import contextlib
import io
import json
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

from trad3r import experiments as e, jobs
from trad3r.__main__ import main
from test_preparation import sample, assumptions


class JobTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fixture = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.fixture.cleanup)
        root = Path(cls.fixture.name)
        sample(root/"source.zip")
        (root/"assumptions.json").write_text(json.dumps(assumptions()))
        e.register_experiment(root/"source.zip", root/"assumptions.json", root/"registration.json",
                              experiment_id="synthetic-job-v1", symbol="AAA", start="2026-09-08", end="2026-09-09")
        e.run_experiment(root/"registration.json", root/"source.zip", root/"assumptions.json", root/"result.zip")

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        for name in ("registration.json", "assumptions.json", "source.zip"):
            shutil.copyfile(Path(self.fixture.name)/name, self.root/name)

    def publish(self, *args):
        shutil.copyfile(Path(self.fixture.name)/"result.zip", self.root/"result.zip")
        return e.inspect_experiment(self.root/"result.zip")

    def test_real_job_executes_once_and_cli_repeat_only_verifies(self):
        self.assertEqual(jobs.run_job(self.root)["outcome"], "completed")
        original = (self.root/"result.zip").read_bytes()
        with patch.object(e, "run_experiment") as run:
            self.assertEqual(jobs.run_job(self.root)["outcome"], "already_complete")
            with contextlib.redirect_stdout(io.StringIO()) as output:
                self.assertEqual(main(["run-job", str(self.root)]), 0)
            self.assertEqual(json.loads(output.getvalue())["outcome"], "already_complete")
            run.assert_not_called()
        self.assertEqual(original, (self.root/"result.zip").read_bytes())

    def test_failure_before_publication_keeps_identity_and_can_retry(self):
        with patch.object(e, "run_experiment", side_effect=KeyboardInterrupt), self.assertRaises(KeyboardInterrupt):
            jobs.run_job(self.root)
        with sqlite3.connect(self.root/"job.sqlite") as connection:
            self.assertEqual(connection.execute("SELECT registration_sha, bundle_sha FROM job").fetchone(),
                             (e.digest((self.root/"registration.json").read_bytes()), None))
        with patch.object(e, "run_experiment", side_effect=self.publish):
            self.assertEqual(jobs.run_job(self.root)["outcome"], "completed")

    def test_process_exit_after_publication_recovers_without_execution(self):
        code = ("import os,sys; from pathlib import Path; from unittest.mock import patch; "
                "from trad3r import jobs; "
                "patcher=patch.object(jobs, '_durable_result', side_effect=lambda p: os._exit(9)); "
                "patcher.start(); jobs.run_job(Path(sys.argv[1]))")
        result = subprocess.run([sys.executable, "-c", code, str(self.root)], capture_output=True, timeout=30)
        self.assertEqual(result.returncode, 9, result.stderr)
        self.assertTrue((self.root/"result.zip").exists())
        with patch.object(e, "run_experiment") as run:
            self.assertEqual(jobs.run_job(self.root)["outcome"], "recovered_published_result")
            run.assert_not_called()

    def test_killed_worker_releases_lock_and_retains_pending_identity(self):
        code = ("import sys,time; from pathlib import Path; from unittest.mock import patch; "
                "from trad3r import jobs, experiments; root=Path(sys.argv[1]); "
                "patcher=patch.object(experiments,'baseline_backtest', "
                "side_effect=lambda *a,**k: ((root/'started').write_text('yes'), time.sleep(60))); "
                "patcher.start(); jobs.run_job(root)")
        process = subprocess.Popen([sys.executable, "-c", code, str(self.root)], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        try:
            deadline = time.monotonic()+15
            while not (self.root/"started").exists() and process.poll() is None and time.monotonic() < deadline:
                time.sleep(.02)
            self.assertTrue((self.root/"started").exists(), "Worker did not reach computation")
            with self.assertRaises(sqlite3.OperationalError):
                jobs.run_job(self.root)
        finally:
            if process.poll() is None:
                process.terminate()
            process.communicate(timeout=10)
        self.assertFalse((self.root/"result.zip").exists())
        with patch.object(e, "run_experiment", side_effect=self.publish):
            self.assertEqual(jobs.run_job(self.root)["outcome"], "completed")

    def test_completed_missing_or_modified_result_never_reruns(self):
        with patch.object(e, "run_experiment", side_effect=self.publish):
            jobs.run_job(self.root)
        original = (self.root/"result.zip").read_bytes()
        (self.root/"result.zip").unlink()
        with patch.object(e, "run_experiment") as run:
            with self.assertRaisesRegex(ValueError, "missing"):
                jobs.run_job(self.root)
            # A valid ZIP with a changed comment still has a different identity.
            from zipfile import ZipFile
            (self.root/"result.zip").write_bytes(original)
            with ZipFile(self.root/"result.zip", "a") as archive:
                archive.comment = b"changed"
            with self.assertRaisesRegex(ValueError, "differs from the pinned"):
                jobs.run_job(self.root)
            run.assert_not_called()

    def test_changed_registration_or_inputs_rejected(self):
        with patch.object(e, "run_experiment", side_effect=ValueError("interrupted")), self.assertRaises(ValueError):
            jobs.run_job(self.root)
        original = (self.root/"registration.json").read_bytes()
        (self.root/"registration.json").write_bytes(original+b" ")
        with self.assertRaisesRegex(ValueError, "identity changed"):
            jobs.run_job(self.root)
        (self.root/"registration.json").write_bytes(original)
        with (self.root/"source.zip").open("ab") as stream:
            stream.write(b"changed")
        with self.assertRaisesRegex(ValueError, "input differs"):
            jobs.run_job(self.root)

    def test_unknown_database_and_corrupt_state_are_preserved(self):
        path = self.root/"job.sqlite"
        with sqlite3.connect(path) as connection:
            connection.execute("CREATE TABLE unrelated (value TEXT)")
        before = path.read_bytes()
        with self.assertRaisesRegex(ValueError, "Unknown job database"):
            jobs.run_job(self.root)
        self.assertEqual(path.read_bytes(), before)
        path.unlink()
        with patch.object(e, "run_experiment", side_effect=self.publish):
            jobs.run_job(self.root)
        with sqlite3.connect(path) as connection:
            connection.execute("DELETE FROM job")
        with self.assertRaisesRegex(ValueError, "inconsistent"):
            jobs.run_job(self.root)

    def test_symlink_inputs_and_wrong_result_identity_fail_closed(self):
        self.publish()
        registration = e.decode((self.root/"registration.json").read_bytes())
        registration["experiment_id"] = "different-job"
        (self.root/"registration.json").write_bytes(e.canonical(registration))
        with self.assertRaisesRegex(ValueError, "differs from the pinned"):
            jobs.run_job(self.root)
        link = self.root/"source.zip"
        link.unlink()
        try:
            link.symlink_to(Path(self.fixture.name)/"source.zip")
        except OSError:
            self.skipTest("Platform does not permit creating symbolic links")
        with self.assertRaisesRegex(ValueError, "symbolic links"):
            jobs.run_job(self.root)
