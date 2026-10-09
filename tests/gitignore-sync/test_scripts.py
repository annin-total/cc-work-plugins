"""gitignore-sync の同梱スクリプトを一時リポジトリで実際に動かして確かめる。"""

import importlib.util
import os
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

SKILL_DIR = (
    Path(__file__).resolve().parents[2]
    / "plugins"
    / "gitignore-sync"
    / "skills"
    / "gitignore-sync"
)
SYNC = SKILL_DIR / "scripts" / "sync_gitignore_tracking.py"
PURGE = SKILL_DIR / "scripts" / "purge_secret_history.py"
SECRET = "秘密.env"
SECRET_BYTES = "TOKEN=値\r\n".encode("utf-8")
GIT_ENV = {
    **os.environ,
    "GIT_AUTHOR_NAME": "test",
    "GIT_AUTHOR_EMAIL": "test@example.com",
    "GIT_COMMITTER_NAME": "test",
    "GIT_COMMITTER_EMAIL": "test@example.com",
    "GIT_CONFIG_NOSYSTEM": "1",
}


def _git(cwd: Path, *args: str) -> None:
    subprocess.run(
        ["git", "-c", "init.defaultBranch=main", *args],
        cwd=cwd,
        env=GIT_ENV,
        check=True,
        capture_output=True,
    )


def _run(script: Path, cwd: Path, *args: str) -> tuple[int, str]:
    """スクリプトを起動し、出力を UTF-8 として読む（Windows で cp932 のまま出すと落ちる）。"""
    env = {k: v for k, v in GIT_ENV.items() if k != "PYTHONIOENCODING"}
    result = subprocess.run(
        [sys.executable, str(script), *args],
        cwd=cwd,
        env=env,
        capture_output=True,
    )
    out = (result.stdout + result.stderr).decode("utf-8")
    return result.returncode, out


def _load_purge():
    spec = importlib.util.spec_from_file_location("purge_secret_history", PURGE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class RepoTestCase(unittest.TestCase):
    """bare の origin に push 済みで、秘密ファイルを追跡したまま .gitignore に足したリポジトリ。"""

    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        base = Path(tmp.name)
        remote = base / "remote.git"
        self.repo = base / "repo"
        remote.mkdir()
        self.repo.mkdir()
        _git(remote, "init", "--bare", "-q")
        _git(self.repo, "init", "-q")
        (self.repo / SECRET).write_bytes(SECRET_BYTES)
        (self.repo / "README.md").write_text("x\n", encoding="utf-8")
        _git(self.repo, "add", "--", SECRET, "README.md")
        _git(self.repo, "commit", "-q", "-m", "init")
        (self.repo / ".gitignore").write_text("*.env\n", encoding="utf-8")
        _git(self.repo, "add", ".gitignore")
        _git(self.repo, "commit", "-q", "-m", "ignore")
        _git(self.repo, "remote", "add", "origin", str(remote))
        _git(self.repo, "push", "-q", "-u", "origin", "main")


class SyncTest(RepoTestCase):
    def test_check_reports_tracked_ignored_file(self) -> None:
        code, out = _run(SYNC, self.repo, "--check")
        self.assertEqual(code, 2, out)
        self.assertIn(SECRET, out)

    def test_untrack_keeps_local_bytes(self) -> None:
        code, out = _run(SYNC, self.repo, "--untrack")
        self.assertEqual(code, 0, out)
        self.assertIn("追跡解除しました: 1 件", out)
        self.assertEqual((self.repo / SECRET).read_bytes(), SECRET_BYTES)
        code, out = _run(SYNC, self.repo, "--check")
        self.assertEqual(code, 0, out)
        self.assertIn("index（追跡中かつ無視対象）: 0 件", out)

    def test_outside_git_fails(self) -> None:
        with tempfile.TemporaryDirectory() as other:
            code, out = _run(SYNC, Path(other), "--check")
        self.assertEqual(code, 1, out)


class PurgePlanTest(RepoTestCase):
    def test_plan_finds_pushed_secret(self) -> None:
        code, out = _run(PURGE, self.repo, "plan", "--path", SECRET)
        self.assertEqual(code, 0, out)
        self.assertIn(f"リモート履歴にあるパス: {SECRET}", out)
        self.assertEqual((self.repo / SECRET).read_bytes(), SECRET_BYTES)

    def test_plan_stops_when_not_in_remote(self) -> None:
        code, out = _run(PURGE, self.repo, "plan", "--path", "other.env")
        self.assertEqual(code, 2, out)

    def test_rewrite_requires_confirmation(self) -> None:
        code, out = _run(PURGE, self.repo, "rewrite", "--path", SECRET)
        self.assertEqual(code, 1, out)
        self.assertIn("--confirm-rewrite", out)


class ValidatePathTest(unittest.TestCase):
    def setUp(self) -> None:
        self.purge = _load_purge()

    def test_rejects_non_relative_paths(self) -> None:
        for path in ("/etc/x", "~/x", "C:/x", "../x", "a//b", ".git/config", "*.env", ""):
            with self.subTest(path=path):
                with self.assertRaises(self.purge.PurgeError):
                    self.purge.validate_path(path)

    def test_accepts_relative_path(self) -> None:
        self.assertEqual(self.purge.validate_path("config/.env"), "config/.env")

    def test_windows_backslashes_become_slashes(self) -> None:
        with mock.patch.object(self.purge.os, "name", "nt"):
            self.assertEqual(self.purge.validate_path("config\\.env"), "config/.env")
            with self.assertRaises(self.purge.PurgeError):
                self.purge.validate_path("C:\\x\\.env")


class SkillTest(unittest.TestCase):
    def setUp(self) -> None:
        self.text = (SKILL_DIR / "SKILL.md").read_text(encoding="utf-8")

    def test_frontmatter_name_matches_directory(self) -> None:
        m = re.match(r"---\nname: (\S+)\n", self.text)
        self.assertIsNotNone(m)
        self.assertEqual(m.group(1), SKILL_DIR.name)

    def test_script_references_exist_and_are_portable(self) -> None:
        refs = re.findall(r'"\$\{CLAUDE_SKILL_DIR\}/([^"]+)"', self.text)
        self.assertTrue(refs)
        for ref in refs:
            self.assertTrue((SKILL_DIR / ref).is_file(), ref)
        self.assertNotIn("$HOME", self.text)
        self.assertNotIn("~/.claude", self.text)


if __name__ == "__main__":
    unittest.main()
