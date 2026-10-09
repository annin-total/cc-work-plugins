"""retitle の hook のキャッシュの権限と、残った依頼文の写しの掃除の単体テスト。"""

import io
import json
import os
import stat
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

from test_retitle import HOOK, _load

POSIX_ONLY = unittest.skipIf(os.name == "nt", "POSIX の権限ビットの検査")


class CacheDirTest(unittest.TestCase):
    def setUp(self) -> None:
        self.hook = _load("retitle_cache_dir", HOOK)
        self.tmp = tempfile.TemporaryDirectory()
        self.cache = Path(self.tmp.name) / "parent" / "cache"
        patch = mock.patch.object(self.hook, "CACHE_DIR", self.cache)
        patch.start()
        self.addCleanup(patch.stop)
        old_umask = os.umask(0o022)
        self.addCleanup(os.umask, old_umask)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _mode(self, path: Path) -> int:
        return stat.S_IMODE(os.lstat(path).st_mode)

    def test_creates_dir_without_error_on_any_os(self) -> None:
        self.hook._ensure_cache_dir()
        self.hook._ensure_cache_dir()  # 既にあっても例外にしない
        self.assertTrue(self.cache.is_dir())

    @POSIX_ONLY
    def test_new_dir_is_owner_only(self) -> None:
        self.hook._ensure_cache_dir()
        self.assertEqual(self._mode(self.cache), 0o700)

    @POSIX_ONLY
    def test_existing_loose_dir_is_tightened(self) -> None:
        self.cache.mkdir(parents=True)
        self.cache.chmod(0o755)
        self.hook._ensure_cache_dir()
        self.assertEqual(self._mode(self.cache), 0o700)

    @POSIX_ONLY
    def test_symlink_target_is_left_alone(self) -> None:
        target = Path(self.tmp.name) / "target"
        target.mkdir()
        target.chmod(0o755)
        self.cache.parent.mkdir()
        self.cache.symlink_to(target)
        self.hook._ensure_cache_dir()
        self.assertEqual(self._mode(target), 0o755)

    def test_sweep_removes_only_stale_requests(self) -> None:
        self.hook._ensure_cache_dir()
        stale, fresh = self.cache / "old.req", self.cache / "new.req"
        state = self.cache / "old.json"
        for path in (stale, fresh, state):
            path.write_text("{}", encoding="utf-8")
        past = time.time() - self.hook.LOCK_STALE_SEC - 10
        os.utime(stale, (past, past))
        os.utime(state, (past, past))
        self.hook._sweep_stale_requests()
        self.assertEqual(
            (stale.exists(), fresh.exists(), state.exists()), (False, True, True)
        )

    def test_hook_tightens_dir_and_sweeps_before_judging(self) -> None:
        self.hook._ensure_cache_dir()
        stale = self.cache / "other.req"
        stale.write_text("{}", encoding="utf-8")
        past = time.time() - self.hook.LOCK_STALE_SEC - 10
        os.utime(stale, (past, past))
        if os.name != "nt":
            self.cache.chmod(0o755)
        payload = {
            "session_id": "s1",
            "prompt": "認証まわりの不具合を調べてほしい",
            "cwd": self.tmp.name,
        }
        stdin = io.TextIOWrapper(io.BytesIO(json.dumps(payload).encode("utf-8")))
        with (
            mock.patch.object(self.hook.sys, "stdin", stdin),
            mock.patch.object(self.hook, "_git", return_value=None),
            mock.patch.object(self.hook, "_spawn_judge") as spawn,
        ):
            self.hook._hook()
        spawn.assert_called_once_with("s1")
        self.assertFalse(stale.exists())
        self.assertTrue((self.cache / "s1.req").exists())
        if os.name != "nt":
            self.assertEqual(self._mode(self.cache), 0o700)


if __name__ == "__main__":
    unittest.main()
