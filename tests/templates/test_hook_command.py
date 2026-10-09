"""templates/plugin の hooks.json の command を、Claude Code と同じシェルで実行して確かめる。"""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

PLUGIN = Path(__file__).resolve().parents[2] / "templates" / "plugin"


def _shell() -> str:
    """macOS・Linux は sh、Windows は Git Bash（Claude Code の既定に合わせる）。"""
    if os.name != "nt":
        return shutil.which("sh") or "/bin/sh"
    git = shutil.which("git")
    for parent in Path(git).resolve().parents if git else []:
        if (parent / "bin" / "bash.exe").is_file():
            return str(parent / "bin" / "bash.exe")
    raise AssertionError(f"Git Bash が見つからない（git: {git}）")


def _command() -> str:
    hooks = json.loads((PLUGIN / "hooks" / "hooks.json").read_text(encoding="utf-8"))
    return hooks["hooks"]["UserPromptSubmit"][0]["hooks"][0]["command"]


def _run(stdin: str, path: str) -> subprocess.CompletedProcess:
    env = dict(os.environ, CLAUDE_PLUGIN_ROOT=str(PLUGIN), PATH=path)
    return subprocess.run(
        [_shell(), "-c", _command()], input=stdin, capture_output=True,
        encoding="utf-8", errors="replace", env=env, timeout=60,
    )


class HookCommandTest(unittest.TestCase):
    def test_runs_hook_with_found_python(self) -> None:
        r = _run(json.dumps({"prompt": "こんにちは"}, ensure_ascii=False), os.environ["PATH"])
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_script_failure_is_not_retried_with_another_python(self) -> None:
        r = _run("not json", os.environ["PATH"])
        self.assertNotEqual(r.returncode, 0)
        self.assertEqual(r.stderr.count("Traceback"), 1, r.stderr)

    def test_reports_when_no_python(self) -> None:
        with tempfile.TemporaryDirectory() as empty:
            r = _run("{}", empty)
        self.assertEqual(r.returncode, 1)
        self.assertIn("Python が見つからない", r.stderr)


if __name__ == "__main__":
    unittest.main()
