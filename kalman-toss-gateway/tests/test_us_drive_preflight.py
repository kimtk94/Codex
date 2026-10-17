import errno
import io
import unittest
from contextlib import redirect_stdout, redirect_stderr
from pathlib import Path
from types import SimpleNamespace
from scripts.us_drive_preflight import check


class DrivePreflightTests(unittest.TestCase):
    def run_case(self, sequence):
        items = iter(sequence)
        calls = []
        def fake_stat():
            outcome = next(items)
            if isinstance(outcome, Exception):
                raise outcome
            return SimpleNamespace(st_mode=outcome)
        with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            return check(Path("/not/used"), retries=3, sleep=lambda secs: calls.append(secs), stat=fake_stat), calls

    def test_success(self):
        self.assertEqual(self.run_case([1]), (0, []))

    def test_eio_retry_then_success(self):
        self.assertEqual(self.run_case([OSError(errno.EIO, "io"), 1]), (0, [1]))

    def test_eio_exhausted(self):
        self.assertEqual(self.run_case([OSError(errno.EIO, "io")] * 3), (20, [1, 2]))

    def test_permission_no_retry(self):
        self.assertEqual(self.run_case([PermissionError(errno.EACCES, "denied")]), (21, []))

    def test_missing_no_retry(self):
        self.assertEqual(self.run_case([FileNotFoundError(errno.ENOENT, "missing")]), (22, []))


if __name__ == "__main__":
    unittest.main()
