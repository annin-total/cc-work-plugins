#!/usr/bin/env python3
"""セッションタイトル自動リネームの hook と /retitle スキルを、Claude Code の設定ディレクトリに導入・確認・削除する。

使い方: python install.py [--check | --uninstall] [--config-dir DIR]
設定ディレクトリは --config-dir、環境変数 CLAUDE_CONFIG_DIR、~/.claude の順に決める。
hook はこのスクリプトを実行した Python で起動するよう登録する（シェルを介さない exec form）。
"""

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Optional

HERE = Path(__file__).resolve().parent
HOOK_SRC = HERE / "retitle.py"
SKILL_TEMPLATE = HERE.parent / "assets" / "retitle-skill.md"
HOOK_NAME = "retitle.py"
EVENT = "UserPromptSubmit"
_OURS = re.compile(r"(^|[/\\\s\"'])" + re.escape(HOOK_NAME) + r"([\"'\s]|$)")
MIN_CLAUDE_VERSION = (2, 1, 139)  # hook の args（exec form）が入った版


def _config_dir(arg: Optional[str]) -> Path:
    raw = arg or os.environ.get("CLAUDE_CONFIG_DIR") or str(Path.home() / ".claude")
    return Path(raw).expanduser().resolve()


def _paths(cfg: Path) -> "tuple[Path, Path, Path]":
    return (
        cfg / "settings.json",
        cfg / "hooks" / HOOK_NAME,
        cfg / "skills" / "retitle" / "SKILL.md",
    )


def _load_settings(path: Path) -> dict:
    if not path.exists():
        return {}
    text = path.read_text(encoding="utf-8-sig")
    data = json.loads(text) if text.strip() else {}
    if not isinstance(data, dict):
        raise TypeError(f"{path} の中身が JSON のオブジェクトではありません")
    return data


def _save_settings(path: Path, data: dict) -> None:
    # シンボリックリンク（dotfiles の管理など）を壊さないよう、リンク先の実体を書き換える
    real = path.resolve()
    real.parent.mkdir(parents=True, exist_ok=True)
    if real.exists():
        shutil.copy2(
            real,
            real.with_name(f"{real.name}.bak-retitle-{time.strftime('%Y%m%d%H%M%S')}"),
        )
    tmp = real.with_name(real.name + ".tmp-retitle")
    tmp.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    os.replace(tmp, real)


def _is_ours(hook: dict) -> bool:
    parts = [str(hook.get("command", ""))] + [str(a) for a in hook.get("args") or []]
    return any(_OURS.search(p) for p in parts)


def _strip_ours(settings: dict) -> int:
    """settings から自分の hook を除き、除いた数を返す。空になった入れ物も消す。"""
    groups = settings.get("hooks", {}).get(EVENT, [])
    removed, kept = 0, []
    for group in groups:
        hooks = [h for h in group.get("hooks", []) if not _is_ours(h)]
        removed += len(group.get("hooks", [])) - len(hooks)
        if hooks:
            kept.append({**group, "hooks": hooks})
    if EVENT in settings.get("hooks", {}):
        if kept:
            settings["hooks"][EVENT] = kept
        else:
            del settings["hooks"][EVENT]
        if not settings["hooks"]:
            del settings["hooks"]
    return removed


def _claude_version() -> Optional["tuple[int, ...]"]:
    exe = shutil.which("claude")
    if not exe:
        return None
    try:
        out = subprocess.run(
            [exe, "--version"], check=False, capture_output=True, text=True, timeout=30
        )
        return tuple(int(x) for x in out.stdout.split()[0].split("."))
    except (OSError, subprocess.SubprocessError, ValueError, IndexError):
        return None


def _install(cfg: Path) -> None:
    if sys.prefix != sys.base_prefix:
        sys.exit(
            "仮想環境（venv）の Python では導入しません。venv の外の python で実行してください"
        )
    version = _claude_version()
    if version is None:
        print(
            "注意: claude コマンドが見つかりません。判定に claude -p を使うので、PATH に claude を通してください"
        )
    elif version < MIN_CLAUDE_VERSION:
        sys.exit(
            f"Claude Code {'.'.join(map(str, version))} は古すぎます。"
            f"{'.'.join(map(str, MIN_CLAUDE_VERSION))} 以上に更新してください（claude update）"
        )
    settings_path, hook_path, skill_path = _paths(cfg)
    settings = _load_settings(settings_path)  # 壊れていれば何も書かずに例外で止まる
    hook_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(HOOK_SRC, hook_path)
    python = Path(sys.executable).resolve()
    skill = (
        SKILL_TEMPLATE.read_text(encoding="utf-8")
        .replace("{{PYTHON}}", python.as_posix())
        .replace("{{SCRIPT}}", hook_path.as_posix())
    )
    skill_path.parent.mkdir(parents=True, exist_ok=True)
    skill_path.write_text(skill, encoding="utf-8")
    _strip_ours(settings)
    entry = {
        "hooks": [{"type": "command", "command": str(python), "args": [str(hook_path)]}]
    }
    settings.setdefault("hooks", {}).setdefault(EVENT, []).append(entry)
    _save_settings(settings_path, settings)
    print(
        f"導入しました: {hook_path}\n  /retitle: {skill_path}\n  settings: {settings_path}\n  Python: {python}"
    )


def _check(cfg: Path) -> bool:
    settings_path, hook_path, skill_path = _paths(cfg)
    try:
        groups = _load_settings(settings_path).get("hooks", {}).get(EVENT, [])
    except (ValueError, TypeError) as exc:
        print(f"NG settings.json を読めません: {exc}")
        return False
    ours = [h for g in groups for h in g.get("hooks", []) if _is_ours(h)]
    results = {
        "settings.json に hook が 1 つだけ登録されている": len(ours) == 1,
        "hook のスクリプトがある": hook_path.is_file(),
        "/retitle スキルがある": skill_path.is_file(),
    }
    if len(ours) == 1:
        hook = ours[0]
        payload = json.dumps(
            {"session_id": "retitle-install-check", "prompt": "ok", "cwd": str(cfg)}
        )
        try:
            out = subprocess.run(
                [hook["command"], *hook.get("args", [])],
                input=payload.encode("utf-8"),
                check=False,
                capture_output=True,
                timeout=30,
            )
            results["登録したコマンドで hook が正常終了する"] = (
                out.returncode == 0 and not out.stderr
            )
        except OSError:
            results["登録したコマンドで hook が正常終了する"] = False
    for name, ok in results.items():
        print(("OK " if ok else "NG ") + name)
    return all(results.values())


def _uninstall(cfg: Path) -> None:
    settings_path, hook_path, skill_path = _paths(cfg)
    settings = _load_settings(settings_path)
    if _strip_ours(settings):
        _save_settings(settings_path, settings)
    hook_path.unlink(missing_ok=True)
    skill_path.unlink(missing_ok=True)
    if skill_path.parent.is_dir() and not any(skill_path.parent.iterdir()):
        skill_path.parent.rmdir()
    print(f"削除しました（状態の保存先 ~/.cache/cc-retitle は残しています）: {cfg}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--check", action="store_true", help="導入の状態を確かめる")
    mode.add_argument(
        "--uninstall", action="store_true", help="hook と /retitle を取り除く"
    )
    parser.add_argument(
        "--config-dir",
        help="Claude Code の設定ディレクトリ（既定は CLAUDE_CONFIG_DIR か ~/.claude）",
    )
    args = parser.parse_args()
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    cfg = _config_dir(args.config_dir)
    try:
        if args.check:
            sys.exit(0 if _check(cfg) else 1)
        _uninstall(cfg) if args.uninstall else _install(cfg)
    except (ValueError, TypeError) as exc:
        sys.exit(f"中止しました（何も書き換えていません）: {exc}")


if __name__ == "__main__":
    main()
