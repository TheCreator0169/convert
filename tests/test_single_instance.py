import os
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

from convert_win import ui

ROOT = Path(__file__).resolve().parent.parent


class SingleInstance(unittest.TestCase):
    def test_only_one_claims_first(self):
        name = f"Convert-test-{os.getpid()}"
        self.assertTrue(ui.claim_first(name))
        self.assertFalse(ui.claim_first(name))  # same process, second handle: already exists

    def test_two_simultaneous_real_launches_make_one_window(self):
        """Explorer starts one process per selected file at the same moment. Needs a real desktop session."""
        d = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)  # the killed app may still hold its log
        env = {**os.environ, "APPDATA": d.name, "LOCALAPPDATA": d.name}
        env.pop("QT_QPA_PLATFORM", None)
        args = [sys.executable, str(ROOT / "convert.pyw")]
        procs = [subprocess.Popen(args + [f], env=env, stdin=subprocess.DEVNULL)
                 for f in (str(ROOT / "README.md"), str(ROOT / "LICENSE"))]
        try:
            time.sleep(6)
            alive = [p for p in procs if p.poll() is None]
            self.assertEqual(len(alive), 1, "the second launch must hand its files over and exit")
        finally:
            for p in procs:
                if p.poll() is None:
                    p.terminate()
            for p in procs:
                p.wait(10)
            d.cleanup()


if __name__ == "__main__":
    unittest.main()
