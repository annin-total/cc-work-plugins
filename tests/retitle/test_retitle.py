"""setup-retitle の導入スクリプトと hook の単体テスト。python -m unittest で動く（pytest でも可）。"""

import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

SCRIPTS = Path(__file__).resolve().parents[2] / "plugins" / "retitle" / "skills" / "setup-retitle" / "scripts"
INSTALL = SCRIPTS / "install.py"
HOOK = SCRIPTS / "retitle.py"
OTHER_HOOK = {"type": "command", "command": "echo other"}


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _run_install(cfg: Path, *flags: str) -> subprocess.CompletedProcess:
    env = {k: v for k, v in os.environ.items() if k != "CLAUDE_CONFIG_DIR"}
    env["CC_RETITLE_CACHE_DIR"] = str(cfg / "cache")
    return subprocess.run(
        [sys.executable, str(INSTALL), "--config-dir", str(cfg), *flags],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        env=env,
    )


def _ours(settings: dict) -> list:
    groups = settings.get("hooks", {}).get("UserPromptSubmit", [])
    return [h for g in groups for h in g["hooks"] if "retitle.py" in json.dumps(h)]


class InstallTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.cfg = Path(self.tmp.name) / "cfg"
        self.cfg.mkdir()
        self.settings = self.cfg / "settings.json"

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _read(self) -> dict:
        return json.loads(self.settings.read_text(encoding="utf-8"))

    def test_fresh_install_registers_exec_form(self) -> None:
        out = _run_install(self.cfg)
        self.assertEqual(out.returncode, 0, out.stderr)
        (hook,) = _ours(self._read())
        self.assertEqual(Path(hook["command"]), Path(sys.executable).resolve())
        self.assertEqual(
            hook["args"], [str(self.cfg.resolve() / "hooks" / "retitle.py")]
        )
        skill = (self.cfg / "skills" / "retitle" / "SKILL.md").read_text(
            encoding="utf-8"
        )
        self.assertNotIn("{{", skill)
        self.assertIn((self.cfg.resolve() / "hooks" / "retitle.py").as_posix(), skill)

    def test_reinstall_replaces_old_entry_and_keeps_others(self) -> None:
        old = {
            "type": "command",
            "command": "/usr/bin/python3 /Users/x/.claude/hooks/retitle.py",
        }
        self.settings.write_text(
            json.dumps(
                {
                    "model": "opus",
                    "hooks": {
                        "UserPromptSubmit": [{"hooks": [old, OTHER_HOOK]}],
                        "Stop": [{"hooks": [OTHER_HOOK]}],
                    },
                }
            )
        )
        for _ in range(2):
            self.assertEqual(_run_install(self.cfg).returncode, 0)
        data = self._read()
        self.assertEqual(len(_ours(data)), 1)
        self.assertEqual(data["model"], "opus")
        self.assertIn(OTHER_HOOK, data["hooks"]["UserPromptSubmit"][0]["hooks"])
        self.assertEqual(data["hooks"]["Stop"], [{"hooks": [OTHER_HOOK]}])
        self.assertTrue(list(self.cfg.glob("settings.json.bak-retitle-*")))

    def test_broken_settings_are_left_untouched(self) -> None:
        self.settings.write_text('{"hooks": ', encoding="utf-8")
        out = _run_install(self.cfg)
        self.assertNotEqual(out.returncode, 0)
        self.assertEqual(self.settings.read_text(encoding="utf-8"), '{"hooks": ')
        self.assertFalse((self.cfg / "hooks" / "retitle.py").exists())

    def test_symlinked_settings_stay_a_symlink(self) -> None:
        real = Path(self.tmp.name) / "dotfiles-settings.json"
        real.write_text("{}", encoding="utf-8")
        self.settings.symlink_to(real)
        self.assertEqual(_run_install(self.cfg).returncode, 0)
        self.assertTrue(self.settings.is_symlink())
        self.assertEqual(len(_ours(json.loads(real.read_text(encoding="utf-8")))), 1)

    def test_check_before_and_after_install(self) -> None:
        self.assertNotEqual(_run_install(self.cfg, "--check").returncode, 0)
        _run_install(self.cfg)
        out = _run_install(self.cfg, "--check")
        self.assertEqual(out.returncode, 0, out.stdout)
        self.assertNotIn("NG", out.stdout)

    def test_uninstall_removes_only_ours(self) -> None:
        self.settings.write_text(
            json.dumps({"hooks": {"UserPromptSubmit": [{"hooks": [OTHER_HOOK]}]}})
        )
        _run_install(self.cfg)
        self.assertEqual(_run_install(self.cfg, "--uninstall").returncode, 0)
        self.assertEqual(
            self._read(), {"hooks": {"UserPromptSubmit": [{"hooks": [OTHER_HOOK]}]}}
        )
        self.assertFalse((self.cfg / "hooks" / "retitle.py").exists())
        self.assertFalse((self.cfg / "skills" / "retitle").exists())


class HookFlowTest(unittest.TestCase):
    """偽の claude を PATH に置き、判定から次の送信での反映までを通す。"""

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.cache = root / "cache"
        bin_dir = root / "bin"
        bin_dir.mkdir()
        fake = bin_dir / "claude"
        fake.write_text(
            f"#!{sys.executable}\nimport sys\nsys.stdin.read()\nprint('偽の判定タイトル')\n",
            encoding="utf-8",
        )
        fake.chmod(0o755)
        self.env = {
            **os.environ,
            "CC_RETITLE_CACHE_DIR": str(self.cache),
            "PATH": f"{bin_dir}{os.pathsep}{os.environ['PATH']}",
        }
        self.env.pop("CC_RETITLE_CHILD", None)
        self.cwd = str(root)  # git リポジトリの外なのでブランチは付かない

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _send(self, prompt: str) -> subprocess.CompletedProcess:
        payload = {"session_id": "s1", "prompt": prompt, "cwd": self.cwd}
        return subprocess.run(
            [sys.executable, str(HOOK)],
            input=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            check=False,
            capture_output=True,
            env=self.env,
        )

    def test_title_applies_on_next_prompt(self) -> None:
        first = self._send("認証まわりの不具合を調べてほしい。ログインが失敗する")
        self.assertEqual((first.returncode, first.stdout, first.stderr), (0, b"", b""))
        state = self.cache / "s1.json"
        deadline = time.time() + 30
        while not state.exists() and time.time() < deadline:
            time.sleep(0.2)
        self.assertTrue(
            state.exists(),
            (self.cache / "error.log").read_text()
            if (self.cache / "error.log").exists()
            else "",
        )
        second = self._send("ok")
        self.assertEqual(second.returncode, 0)
        out = json.loads(second.stdout)
        self.assertEqual(out["hookSpecificOutput"]["sessionTitle"], "偽の判定タイトル")
        self.assertTrue(
            second.stdout.isascii()
        )  # Windows のコンソールの文字コードに左右されない

    def test_short_and_slash_prompts_are_not_judged(self) -> None:
        for prompt in ("短い", "/retitle 認証まわりの不具合の調査をする"):
            self.assertEqual(self._send(prompt).returncode, 0)
        time.sleep(1)
        self.assertFalse((self.cache / "s1.json").exists())


class WindowsSpawnTest(unittest.TestCase):
    def setUp(self) -> None:
        self.hook = _load("retitle_under_test", HOOK)

    def test_windows_detach_falls_back_when_breakaway_is_denied(self) -> None:
        calls = []

        def fake_popen(args, **kwargs):
            calls.append(kwargs)
            if len(calls) == 1:
                raise PermissionError("access denied")
            return mock.Mock()

        with (
            mock.patch.object(self.hook, "IS_WINDOWS", True),
            mock.patch.object(self.hook, "_DETACH_FLAGS", 0x08000200),
            mock.patch.object(self.hook, "_BREAKAWAY", 0x01000000),
            mock.patch.object(self.hook.subprocess, "Popen", side_effect=fake_popen),
        ):
            self.hook._spawn_judge("s1")
        self.assertEqual([c["creationflags"] for c in calls], [0x09000200, 0x08000200])
        self.assertTrue(all("start_new_session" not in c for c in calls))

    def test_windows_only_flags_are_zero_elsewhere(self) -> None:
        if os.name != "nt":
            self.assertEqual(
                (self.hook._NO_WINDOW, self.hook._DETACH_FLAGS, self.hook._BREAKAWAY),
                (0, 0, 0),
            )


if __name__ == "__main__":
    unittest.main()
