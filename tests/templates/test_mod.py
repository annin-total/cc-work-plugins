"""templates/plugin の mod を、配布物の外に置いたテストと合わせて `claude plugin test` で確かめる。"""

import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

PLUGIN = Path(__file__).resolve().parents[2] / "templates" / "plugin"
MOD_TESTS = Path(__file__).resolve().parent / "mod"
CLAUDE = shutil.which("claude")


class ModTest(unittest.TestCase):
    def test_mod_tests_pass(self) -> None:
        if CLAUDE is None:
            if os.environ.get("CWP_SKIP_CLAUDE") == "1":
                self.skipTest("claude が PATH に無い（--skip-claude）")
            self.fail("claude が PATH に無い（validate.py --skip-claude で明示して飛ばせる）")
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "plugin"
            shutil.copytree(PLUGIN, target)
            for src in MOD_TESTS.glob("*.test.ts"):
                shutil.copy(src, target / src.name)
            r = subprocess.run(
                [str(CLAUDE), "plugin", "test", str(target)], capture_output=True,
                encoding="utf-8", errors="replace", timeout=120,
            )
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertRegex(r.stdout + r.stderr, r"\b[1-9]\d* pass\b")


if __name__ == "__main__":
    unittest.main()
