"""マーケットプレイスの検査をまとめて実行し、結果を一覧で出す。1 件でも失敗なら終了コード 1。"""

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import List, Optional, Tuple

ROOT = Path(__file__).resolve().parents[1]
CLAUDE = "claude"
REQUIRED_KEYS = ("name", "version", "description", "author", "license")
Result = Tuple[str, str, str]  # (PASS|FAIL|SKIP, 検査名, 失敗時の詳細)


def _run(cmd: List[str], cwd: Path) -> Tuple[int, str]:
    env = dict(os.environ, PYTHONIOENCODING="utf-8")
    r = subprocess.run(cmd, cwd=cwd, capture_output=True, encoding="utf-8", errors="replace", env=env)
    return r.returncode, r.stdout + r.stderr


def _plugin_dirs(root: Path) -> List[Path]:
    base = root / "plugins"
    return sorted(p for p in base.iterdir() if p.is_dir()) if base.is_dir() else []


def _plugin_targets(root: Path) -> List[Path]:
    template = root / "templates" / "plugin"
    return _plugin_dirs(root) + ([template] if template.is_dir() else [])


def _rel(path: Path, root: Path) -> str:
    return path.relative_to(root).as_posix() or "."


def check_claude(root: Path, skip: bool) -> List[Result]:
    exe = shutil.which(CLAUDE)
    results = []
    for target in [root] + _plugin_targets(root):
        name = f"claude plugin validate {_rel(target, root)} --strict"
        if exe is None:
            results.append(("SKIP", name, "") if skip else ("FAIL", name, "claude が PATH に無い（--skip-claude で明示して飛ばせる）"))
            continue
        code, out = _run([exe, "plugin", "validate", str(target), "--strict"], root)
        results.append(("PASS", name, "") if code == 0 else ("FAIL", name, out))
    return results


def _load_json(path: Path) -> Optional[dict]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def check_marketplace(root: Path) -> List[Result]:
    name = "marketplace.json の登録と plugins/ の一致"
    data = _load_json(root / ".claude-plugin" / "marketplace.json")
    if data is None:
        return [("FAIL", name, ".claude-plugin/marketplace.json を読めない")]
    errors = []
    registered = set()
    for entry in data.get("plugins", []):
        src = (root / entry.get("source", "")).resolve()
        registered.add(src)
        manifest = _load_json(src / ".claude-plugin" / "plugin.json")
        if manifest is None:
            errors.append(f"{entry.get('name')}: 実体（plugin.json）が無い: {entry.get('source')}")
        elif not (entry.get("name") == manifest.get("name") == src.name):
            errors.append(f"name が不一致: marketplace={entry.get('name')} plugin.json={manifest.get('name')} dir={src.name}")
    for d in _plugin_dirs(root):
        if d.resolve() not in registered:
            errors.append(f"登録漏れ: {_rel(d, root)}")
    return [("FAIL" if errors else "PASS", name, "\n".join(errors))]


def check_plugins(root: Path) -> List[Result]:
    results = []
    for d in _plugin_targets(root):
        name = f"{_rel(d, root)} の README.md と plugin.json の必須項目"
        manifest = _load_json(d / ".claude-plugin" / "plugin.json") or {}
        errors = [f"plugin.json に {k} が無い" for k in REQUIRED_KEYS if not manifest.get(k)]
        if not (d / "README.md").is_file():
            errors.append("README.md が無い")
        if d.parent.name == "plugins" and not (root / "tests" / d.name).is_dir():
            errors.append(f"tests/{d.name}/ が無い")
        results.append(("FAIL" if errors else "PASS", name, "\n".join(errors)))
    return results


def check_tests(root: Path) -> List[Result]:
    results = []
    base = root / "tests"
    for d in sorted(p for p in base.iterdir() if p.is_dir() and p.name != "__pycache__") if base.is_dir() else []:
        code, out = _run([sys.executable, "-m", "unittest", "discover", "-s", str(d)], root)
        m = re.search(r"^Ran (\d+) tests?", out, re.MULTILINE)
        count = int(m.group(1)) if m else 0
        name = f"unittest tests/{d.name}（{count} 件）"
        if count == 0:
            results.append(("FAIL", name, "テストが 0 件\n" + out))
        else:
            results.append(("PASS", name, "") if code == 0 else ("FAIL", name, out))
    return results


def run_checks(root: Path, skip_claude: bool) -> List[Result]:
    return check_claude(root, skip_claude) + check_marketplace(root) + check_plugins(root) + check_tests(root)


def main(argv: Optional[List[str]] = None) -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--skip-claude", action="store_true", help="claude が PATH に無いとき、その検査を SKIP にする")
    args = parser.parse_args(argv)
    print(f"Python {sys.version.split()[0]} ({sys.executable})")
    results = run_checks(ROOT, args.skip_claude)
    for status, name, detail in results:
        print(f"{status}  {name}")
        if status == "FAIL" and detail:
            print("      " + detail.strip().replace("\n", "\n      "))
    failed = sum(1 for r in results if r[0] == "FAIL")
    skipped = sum(1 for r in results if r[0] == "SKIP")
    print(f"\n{len(results)} 件中 失敗 {failed} 件・SKIP {skipped} 件")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
