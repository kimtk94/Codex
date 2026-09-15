from __future__ import annotations

import errno
import os
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from engine.pipeline_entry import _install_drive_copy2_compat


class DriveCopy2CompatTests(unittest.TestCase):
    def test_drive_path_falls_back_to_copyfile_on_eio(self) -> None:
        original_copy2 = shutil.copy2
        original_copyfile = shutil.copyfile
        try:
            with tempfile.TemporaryDirectory() as td:
                root = Path(td)
                src = root / "src.bin"
                dst = root / "dst.bin"
                src.write_bytes(b"kalman")

                def fake_copy2(src_arg, dst_arg, *, follow_symlinks=True):
                    original_copyfile(src_arg, dst_arg, follow_symlinks=follow_symlinks)
                    raise OSError(errno.EIO, "simulated xattr EIO")

                with patch("shutil.copy2", side_effect=fake_copy2):
                    # Install while shutil.copy2 is patched so the wrapper captures
                    # the simulated copy2 implementation as the original.
                    _install_drive_copy2_compat()
                    with patch("os.path.abspath", return_value="/mnt/gdrive/test/src.bin"):
                        result = shutil.copy2(src, dst)

                self.assertEqual(Path(result), dst)
                self.assertEqual(dst.read_bytes(), b"kalman")
        finally:
            shutil.copy2 = original_copy2

    def test_non_drive_eio_is_not_suppressed(self) -> None:
        original_copy2 = shutil.copy2
        try:
            def fake_copy2(*args, **kwargs):
                raise OSError(errno.EIO, "simulated local EIO")

            with patch("shutil.copy2", side_effect=fake_copy2):
                _install_drive_copy2_compat()
                with patch("os.path.abspath", return_value="/tmp/local-file"):
                    with self.assertRaises(OSError):
                        shutil.copy2("/tmp/a", "/tmp/b")
        finally:
            shutil.copy2 = original_copy2


if __name__ == "__main__":
    unittest.main()
