import sys
import threading
import unittest

from convert_win import process


class Process(unittest.TestCase):
    def test_run_captures_output(self):
        rc, out, _ = process.run([sys.executable, "-c", "print('héllo')"])
        self.assertEqual((rc, out.strip()), (0, "héllo"))

    def test_nonzero_exit_and_stderr(self):
        rc, _, err = process.run([sys.executable, "-c", "import sys;sys.stderr.write('boom');sys.exit(3)"])
        self.assertEqual((rc, err), (3, "boom"))

    def test_cancel_stops_a_long_process(self):
        ev = threading.Event()
        threading.Timer(0.5, ev.set).start()
        with self.assertRaises(process.Cancelled):
            process.run([sys.executable, "-c", "import time;time.sleep(30)"], ev)

    def test_no_window_flag(self):
        self.assertEqual(process.NO_WINDOW, 0x08000000)


if __name__ == "__main__":
    unittest.main()
