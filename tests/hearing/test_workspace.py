"""init（実行ごとの作業フォルダの作成）のテスト。"""

import json
import os
import tempfile
import unittest
from datetime import datetime
from pathlib import Path

from helpers import run
from _workspace import init_workspace


class InitCommandTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def init(self):
        return run(["init", "--root", str(self.root)])

    def test_first_run_creates_layout(self) -> None:
        rc, so, _ = self.init()
        self.assertEqual(rc, 0)
        self.assertEqual(len(so.strip().splitlines()), 1)
        out = json.loads(so)
        self.assertEqual(set(out), {"run_dir", "work_dir", "created_gitignore"})
        self.assertTrue(out["created_gitignore"])
        run_dir, work_dir = Path(out["run_dir"]), Path(out["work_dir"])
        self.assertTrue(run_dir.is_absolute())
        self.assertEqual(work_dir, run_dir / "work")
        self.assertTrue(work_dir.is_dir())
        self.assertEqual(run_dir.parent, self.root / "hearing-cost")
        self.assertEqual((self.root / "hearing-cost" / ".gitignore").read_text(), "*\n")

    def test_second_run_keeps_gitignore(self) -> None:
        self.init()
        gi = self.root / "hearing-cost" / ".gitignore"
        gi.write_text("custom\n")
        rc, so, _ = self.init()
        self.assertEqual(rc, 0)
        self.assertFalse(json.loads(so)["created_gitignore"])
        self.assertEqual(gi.read_text(), "custom\n")

    def test_same_minute_gets_suffix(self) -> None:
        fixed = lambda: datetime(2026, 10, 2, 9, 5)  # noqa: E731
        names = [Path(str(init_workspace(str(self.root), fixed)["run_dir"])).name for _ in range(3)]
        self.assertEqual(names, ["20261002-0905", "20261002-0905-2", "20261002-0905-3"])

    def test_symlink_base_is_refused(self) -> None:
        target = self.root / "elsewhere"
        target.mkdir()
        os.symlink(str(target), str(self.root / "hearing-cost"))
        rc, so, se = self.init()
        self.assertEqual(rc, 2)
        self.assertEqual(so, "")
        self.assertEqual(list(target.iterdir()), [])

    def test_file_base_is_refused(self) -> None:
        (self.root / "hearing-cost").write_text("x")
        rc, so, _ = self.init()
        self.assertEqual(rc, 2)
        self.assertEqual(so, "")
        self.assertEqual((self.root / "hearing-cost").read_text(), "x")

    def test_missing_root(self) -> None:
        rc, so, _ = run(["init", "--root", str(self.root / "nope")])
        self.assertEqual(rc, 2)
        self.assertEqual(so, "")
        self.assertFalse((self.root / "nope").exists())


if __name__ == "__main__":
    unittest.main()
