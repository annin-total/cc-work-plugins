"""scripts/validate.py が、壊れたマーケットプレイスを失敗として検出することを確かめる。"""

import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "validate.py"
_spec = importlib.util.spec_from_file_location("validate", SCRIPT)
validate = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(validate)

PASSING_TEST = "import unittest\nclass T(unittest.TestCase):\n    def test_ok(self):\n        pass\n"
FAILING_TEST = "import unittest\nclass T(unittest.TestCase):\n    def test_ng(self):\n        self.fail()\n"


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _make_marketplace(root: Path, names=("alpha",)) -> None:
    entries = [{"name": n, "source": f"./plugins/{n}"} for n in names]
    _write(root / ".claude-plugin" / "marketplace.json", json.dumps({"name": "m", "plugins": entries}))
    for n in names:
        manifest = {"name": n, "version": "0.1.0", "description": "d", "author": {"name": "a"}, "license": "MIT"}
        _write(root / "plugins" / n / ".claude-plugin" / "plugin.json", json.dumps(manifest))
        _write(root / "plugins" / n / "README.md", "# x\n")
        _write(root / "tests" / n / "test_x.py", PASSING_TEST)


class ValidateTest(unittest.TestCase):
    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        _make_marketplace(self.root)

    def _failed(self, skip_claude: bool = True) -> list:
        with mock.patch.object(validate.shutil, "which", return_value=None):
            results = validate.run_checks(self.root, skip_claude)
        return [name for status, name, _ in results if status == "FAIL"]

    def test_valid_marketplace_passes(self) -> None:
        self.assertEqual(self._failed(), [])

    def test_unregistered_plugin_dir(self) -> None:
        _make_marketplace(self.root, names=("alpha", "beta"))
        _make_marketplace(self.root, names=("alpha",))  # beta の実体だけ残る
        self.assertTrue(any("marketplace.json" in n for n in self._failed()))

    def test_registered_plugin_without_dir(self) -> None:
        data = {"name": "m", "plugins": [{"name": "alpha", "source": "./plugins/alpha"}, {"name": "ghost", "source": "./plugins/ghost"}]}
        _write(self.root / ".claude-plugin" / "marketplace.json", json.dumps(data))
        self.assertTrue(any("marketplace.json" in n for n in self._failed()))

    def test_name_mismatch(self) -> None:
        path = self.root / "plugins" / "alpha" / ".claude-plugin" / "plugin.json"
        manifest = json.loads(path.read_text(encoding="utf-8"))
        manifest["name"] = "other"
        _write(path, json.dumps(manifest))
        self.assertTrue(any("marketplace.json" in n for n in self._failed()))

    def test_missing_readme(self) -> None:
        (self.root / "plugins" / "alpha" / "README.md").unlink()
        self.assertIn("plugins/alpha の README.md と plugin.json の必須項目", self._failed())

    def test_missing_required_key(self) -> None:
        path = self.root / "plugins" / "alpha" / ".claude-plugin" / "plugin.json"
        manifest = json.loads(path.read_text(encoding="utf-8"))
        del manifest["license"]
        _write(path, json.dumps(manifest))
        self.assertIn("plugins/alpha の README.md と plugin.json の必須項目", self._failed())

    def test_plugin_without_tests_dir(self) -> None:
        (self.root / "tests" / "alpha" / "test_x.py").unlink()
        (self.root / "tests" / "alpha").rmdir()
        self.assertIn("plugins/alpha の README.md と plugin.json の必須項目", self._failed())

    def test_tests_dir_with_zero_tests(self) -> None:
        _write(self.root / "tests" / "empty" / "helpers.py", "")
        self.assertIn("unittest tests/empty（0 件）", self._failed())

    def test_failing_test(self) -> None:
        _write(self.root / "tests" / "alpha" / "test_ng.py", FAILING_TEST)
        self.assertIn("unittest tests/alpha（2 件）", self._failed())

    def test_missing_claude_fails_unless_skipped(self) -> None:
        self.assertTrue(any(n.startswith("claude plugin validate") for n in self._failed(skip_claude=False)))
        with mock.patch.object(validate.shutil, "which", return_value=None):
            statuses = {s for s, n, _ in validate.run_checks(self.root, True) if n.startswith("claude")}
        self.assertEqual(statuses, {"SKIP"})

    def test_claude_failure_is_reported(self) -> None:
        # claude の代わりに Python を呼ばせ、非 0 終了を失敗として拾うかを見る
        with mock.patch.object(validate.shutil, "which", return_value=sys.executable):
            results = validate.run_checks(self.root, False)
        self.assertTrue(any(s == "FAIL" and n.startswith("claude") for s, n, _ in results))


if __name__ == "__main__":
    unittest.main()
