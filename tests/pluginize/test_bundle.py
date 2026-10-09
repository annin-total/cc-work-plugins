"""pluginize の同梱物と、リポジトリの設定から pluginize を有効にする記述が実体と食い違わないことを確かめる。"""

import json
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SKILL_DIR = ROOT / "plugins" / "pluginize" / "skills" / "pluginize"


def _frontmatter(text: str) -> dict:
    m = re.match(r"---\n(.*?)\n---\n", text, re.DOTALL)
    if m is None:
        raise AssertionError("SKILL.md の先頭に frontmatter が無い")
    return dict(line.split(": ", 1) for line in m.group(1).splitlines() if ": " in line)


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


class SkillBundleTest(unittest.TestCase):
    def setUp(self) -> None:
        self.text = (SKILL_DIR / "SKILL.md").read_text(encoding="utf-8")

    def test_frontmatter_name_matches_directory(self) -> None:
        meta = _frontmatter(self.text)
        self.assertEqual(meta.get("name"), SKILL_DIR.name)
        self.assertTrue(meta.get("description", "").strip())

    def test_relative_links_resolve(self) -> None:
        links = re.findall(r"\]\(([^)#:]+)\)", self.text)
        self.assertTrue(links, "SKILL.md が references を指していない")
        for link in links:
            self.assertTrue((SKILL_DIR / link).is_file(), f"リンク先が無い: {link}")


class ProjectSettingsTest(unittest.TestCase):
    def test_enabled_plugins_exist_in_declared_marketplace(self) -> None:
        settings = _load(ROOT / ".claude" / "settings.json")
        market = _load(ROOT / ".claude-plugin" / "marketplace.json")
        self.assertIn(market["name"], settings["extraKnownMarketplaces"])
        names = {p["name"] for p in market["plugins"]}
        for key in settings["enabledPlugins"]:
            plugin, _, marketplace = key.partition("@")
            self.assertEqual(marketplace, market["name"], key)
            self.assertIn(plugin, names, key)


if __name__ == "__main__":
    unittest.main()
