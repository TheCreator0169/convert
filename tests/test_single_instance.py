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
        """Explorer starts one process per selected file at the same moment. Needs a real desktop session.
        Which launch wins the claim is a race: the loser must exit 0 on its own, the winner must stay alive."""
        d = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)  # the killed app may still hold its log
        self.addCleanup(d.cleanup)
        (Path(d.name) / "Convert").mkdir()
        (Path(d.name) / "Convert" / "settings.json").write_text('{"update_check": false}', "utf-8")  # no network call
        env = {**os.environ, "APPDATA": d.name, "LOCALAPPDATA": d.name}
        env.pop("QT_QPA_PLATFORM", None)
        args = [sys.executable, str(ROOT / "convert.pyw")]
        procs = []
        self.addCleanup(_stop, procs)  # by Popen handle: each process is stopped by its own PID
        for f in (str(ROOT / "README.md"), str(ROOT / "LICENSE")):
            procs.append(subprocess.Popen(args + [f], env=env, stdin=subprocess.DEVNULL))
        loser = _wait_for_exit(procs, timeout=60)
        self.assertIsNotNone(loser, "neither launch exited: the second launch must hand its files over and exit")
        self.assertEqual(loser.returncode, 0, "the second launch must exit 0 after the hand-over")
        (winner,) = [p for p in procs if p is not loser]
        self.assertIsNone(winner.poll(), "the first launch must still be running with the window")


def _wait_for_exit(procs, timeout):
    """The first of `procs` to exit, or None after `timeout` seconds. Checks the process state every 0.1 s, no fixed sleep."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        done = [p for p in procs if p.poll() is not None]
        if done:
            return done[0]
        time.sleep(0.1)
    return None


def _stop(procs):
    for p in procs:
        if p.poll() is None:
            p.terminate()
    for p in procs:
        try:
            p.wait(10)
        except subprocess.TimeoutExpired:
            p.kill()
            p.wait(10)


if __name__ == "__main__":
    unittest.main()
