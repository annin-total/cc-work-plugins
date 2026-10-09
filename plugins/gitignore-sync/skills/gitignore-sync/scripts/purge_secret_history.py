#!/usr/bin/env python3
"""誤って push した秘密ファイルを、作業ツリーを変えずに履歴から外す。

rewrite は origin の一時クローンだけで行う。push は --confirm-push のときだけ。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path, PureWindowsPath

READONLY_REF_MARKERS = ("refs/pull/", "refs/merge-requests/", "refs/changes/")


class PurgeError(Exception):
    pass


def run(args: list[str], cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        args,
        cwd=cwd,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env={**os.environ, "GIT_TERMINAL_PROMPT": "0"},
    )


def run_git(
    args: list[str], cwd: Path | None = None
) -> subprocess.CompletedProcess[str]:
    return run(["git", *args], cwd=cwd)


def fail(message: str) -> int:
    print(f"エラー: {message}", file=sys.stderr)
    return 1


def git_toplevel() -> Path:
    result = run_git(["rev-parse", "--show-toplevel"])
    if result.returncode != 0:
        raise PurgeError("Git の作業ツリーではありません。")
    return Path(result.stdout.strip()).resolve()


def origin_url(root: Path) -> str:
    result = run_git(["remote", "get-url", "origin"], cwd=root)
    if result.returncode != 0 or not result.stdout.strip():
        raise PurgeError("origin がありません。履歴消去は中止します。")
    return result.stdout.strip()


def validate_path(path: str) -> str:
    if os.name == "nt":
        path = path.replace("\\", "/")
    if (
        path != path.strip()
        or not path
        or path.startswith(("/", "~"))
        or PureWindowsPath(path).drive
    ):
        raise PurgeError(f"リポジトリ相対パスを指定してください: {path!r}")
    parts = path.split("/")
    if any(part in ("", ".", "..") for part in parts):
        raise PurgeError(f"パスが不正です: {path}")
    if parts[0] == ".git" or any(char in path for char in "*?[]"):
        raise PurgeError(f"このパスは指定できません: {path}")
    return path


def fingerprint(path: Path) -> str:
    if path.is_symlink():
        return "symlink:" + os.readlink(path)
    if not path.exists():
        return ""
    if path.is_file():
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        return "file:" + digest.hexdigest()
    if path.is_dir():
        digest = hashlib.sha256()
        for child in sorted(item for item in path.rglob("*") if item.is_file()):
            digest.update(str(child.relative_to(path)).encode())
            digest.update(fingerprint(child).encode())
        return "dir:" + digest.hexdigest()
    return "other"


def snapshot(paths: list[str], root: Path) -> dict[str, str]:
    return {path: fingerprint(root / path) for path in paths}


def assert_unchanged(before: dict[str, str], root: Path) -> None:
    changed = [
        path for path, value in before.items() if fingerprint(root / path) != value
    ]
    if changed:
        raise PurgeError("ローカルファイルが変化しました: " + ", ".join(changed))


def expand_renames(root: Path, paths: list[str]) -> list[str]:
    result = run_git(
        ["log", "--all", "-M", "--diff-filter=R", "--name-status", "--pretty=format:"],
        cwd=root,
    )
    if result.returncode != 0:
        raise PurgeError(result.stderr.strip() or "改名履歴を取得できません。")
    pairs: list[tuple[str, str]] = []
    for line in result.stdout.splitlines():
        parts = line.split("\t")
        if len(parts) == 3 and parts[0].startswith("R"):
            pairs.append((parts[1], parts[2]))
    found = set(paths)
    grew = True
    while grew:
        grew = False
        for old, new in pairs:
            if old in found or new in found:
                for item in (old, new):
                    if item not in found:
                        found.add(item)
                        grew = True
    return sorted(found)


def history_hits(root: Path, paths: list[str], revisions: list[str]) -> list[str]:
    hits: list[str] = []
    for path in paths:
        result = run_git(
            ["log", *revisions, "--full-history", "-1", "--oneline", "--", path],
            cwd=root,
        )
        if result.returncode == 0 and result.stdout.strip():
            hits.append(path)
    return hits


def try_fetch(root: Path) -> None:
    result = run_git(["fetch", "--prune", "origin"], cwd=root)
    if result.returncode != 0:
        print(
            "警告: git fetch に失敗したため、手元のリモート追跡情報で判断します。",
            file=sys.stderr,
        )


def unignored(root: Path, paths: list[str]) -> list[str]:
    missing: list[str] = []
    for path in paths:
        result = run_git(["check-ignore", "--no-index", "--", path], cwd=root)
        if result.returncode != 0:
            missing.append(path)
    return missing


def filter_repo_bin() -> str:
    binary = shutil.which("git-filter-repo")
    if not binary:
        raise PurgeError(
            "git-filter-repo がありません。macOS は brew install git-filter-repo、"
            "Windows は pip install git-filter-repo などで入れてから再実行してください。"
            " 2.47 以降が必要です。"
        )
    help_text = run([binary, "--help"])
    if "--sensitive-data-removal" not in help_text.stdout + help_text.stderr:
        raise PurgeError("git-filter-repo が古すぎます。2.47 以降を入れてください。")
    return binary


def requested_paths(values: list[str]) -> list[str]:
    if not values:
        raise PurgeError("--path を1つ以上指定してください。")
    return [validate_path(value) for value in values]


def command_plan(paths: list[str]) -> int:
    root = git_toplevel()
    paths = expand_renames(root, requested_paths(paths))
    try_fetch(root)
    remote_hits = history_hits(root, paths, ["--remotes"])
    local_hits = history_hits(root, paths, ["--all"])
    print("対象パス: " + ", ".join(paths))
    print("リモート履歴にあるパス: " + (", ".join(remote_hits) or "なし"))
    print("ローカル履歴にあるパス: " + (", ".join(local_hits) or "なし"))
    missing = unignored(root, paths)
    if missing:
        print("gitignore に無いパス: " + ", ".join(missing))
    print("認証情報は、履歴を消しても失効しません。先にローテーションしてください。")
    if not remote_hits:
        print("リモート履歴に対象が無いため、rewrite はしません。")
        return 2
    print("rewrite は一時クローンだけで、リモートはまだ変更しません。")
    return 0


def command_rewrite(paths: list[str], confirm: bool) -> int:
    if not confirm:
        raise PurgeError(
            "--confirm-rewrite が必要です。plan の結果を確認してから実行してください。"
        )
    root = git_toplevel()
    paths = expand_renames(root, requested_paths(paths))
    try_fetch(root)
    if not history_hits(root, paths, ["--remotes"]):
        raise PurgeError("リモート履歴に対象がありません。rewrite を中止しました。")
    url = origin_url(root)
    parent = Path(tempfile.mkdtemp(prefix="gitignore-secret-purge-"))
    clone = parent / "repo"
    if root == clone or root in clone.parents:
        raise PurgeError("一時クローンをリポジトリ内に作れません。")
    cloned = run(["git", "clone", "--no-local", url, str(clone)])
    if cloned.returncode != 0:
        raise PurgeError(cloned.stderr.strip() or "一時クローンに失敗しました。")
    paths = expand_renames(clone, paths)
    before = snapshot(paths, root)
    binary = filter_repo_bin()
    command = [binary, "--sensitive-data-removal", "--invert-paths"]
    for path in paths:
        command.extend(["--path", path])
    filtered = run(command, cwd=clone)
    sys.stdout.write(filtered.stdout)
    sys.stderr.write(filtered.stderr)
    if filtered.returncode != 0:
        raise PurgeError("git-filter-repo に失敗しました。リモートは変更していません。")
    for path in paths:
        remains = run_git(
            ["log", "--all", "--full-history", "-1", "--oneline", "--", path],
            cwd=clone,
        )
        if remains.stdout.strip():
            raise PurgeError(f"書き換え後も履歴に残っています: {path}")
    if run_git(["remote", "get-url", "origin"], cwd=clone).returncode != 0:
        added = run_git(["remote", "add", "origin", url], cwd=clone)
        if added.returncode != 0:
            raise PurgeError(added.stderr.strip() or "origin を戻せません。")
    assert_unchanged(before, root)
    state = {
        "source": str(root),
        "origin": url,
        "clone": str(clone),
        "paths": paths,
    }
    (parent / "state.json").write_text(
        json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"STATE_DIR={parent}")
    print("履歴から外したパス: " + ", ".join(paths))
    print("リモートはまだ更新していません。")
    return 0


def load_state(state_dir: str) -> tuple[Path, dict[str, object]]:
    parent = Path(state_dir).resolve()
    path = parent / "state.json"
    if not path.is_file():
        raise PurgeError(
            "state.json がありません。rewrite の STATE_DIR を指定してください。"
        )
    state = json.loads(path.read_text(encoding="utf-8"))
    source = Path(str(state["source"])).resolve()
    clone = Path(str(state["clone"])).resolve()
    if source == parent or source == clone or source in clone.parents:
        raise PurgeError("作業ツリー自身は書き換え対象にできません。")
    return parent, state


def command_push(state_dir: str, confirm: bool) -> int:
    if not confirm:
        raise PurgeError(
            "--confirm-push が必要です。書き換え結果を確認してから実行してください。"
        )
    _parent, state = load_state(state_dir)
    clone = Path(str(state["clone"]))
    url = origin_url(clone)
    if url != state["origin"]:
        raise PurgeError("一時クローンの origin が rewrite 時と違います。")
    pushed = run_git(["push", "--force", "--mirror", "origin"], cwd=clone)
    output = pushed.stdout + pushed.stderr
    print(output, end="" if output.endswith("\n") or not output else "\n")
    if pushed.returncode == 0:
        print("mirror push しました。")
        return 0
    rejected = [
        line
        for line in output.splitlines()
        if line.startswith(" !") or line.startswith("!")
    ]
    if rejected and all(
        any(marker in line for marker in READONLY_REF_MARKERS) for line in rejected
    ):
        print("読み取り専用の PR 参照以外は更新しました。")
        return 0
    raise PurgeError("mirror push に失敗しました。作業ツリーは変更していません。")


def command_adopt(state_dir: str) -> int:
    _parent, state = load_state(state_dir)
    root = git_toplevel()
    source = Path(str(state["source"])).resolve()
    if root != source:
        raise PurgeError("rewrite した作業ツリーと現在の作業ツリーが違います。")
    raw_paths = state["paths"]
    if not isinstance(raw_paths, list) or not all(
        isinstance(item, str) for item in raw_paths
    ):
        raise PurgeError("state.json の paths が不正です。")
    paths = raw_paths
    branch = run_git(["branch", "--show-current"], cwd=root).stdout.strip()
    if not branch:
        raise PurgeError("detached HEAD では adopt できません。")
    remote_branch = f"origin/{branch}"
    if run_git(["rev-parse", "--verify", remote_branch], cwd=root).returncode != 0:
        raise PurgeError(f"{remote_branch} がありません。adopt を中止します。")
    unpushed = run_git(["rev-list", "--count", f"{remote_branch}..HEAD"], cwd=root)
    if unpushed.returncode != 0:
        raise PurgeError(
            unpushed.stderr.strip() or "未 push コミットを確認できません。"
        )
    if int(unpushed.stdout.strip() or "0") > 0:
        raise PurgeError(
            "未 push のコミットがあります。adopt を中止しました。このクローンから push しないでください。"
        )
    staged = run_git(["diff", "--cached", "--name-only", "-z"], cwd=root)
    extra = [name for name in staged.stdout.split("\0") if name and name not in paths]
    if extra:
        raise PurgeError("対象外のステージ済み変更があります: " + ", ".join(extra))
    before = snapshot(paths, root)
    fetched = run_git(["fetch", "--prune", "origin"], cwd=root)
    if fetched.returncode != 0:
        raise PurgeError(fetched.stderr.strip() or "git fetch に失敗しました。")
    reset = run_git(["reset", "--mixed", remote_branch], cwd=root)
    if reset.returncode != 0:
        raise PurgeError(reset.stderr.strip() or "git reset --mixed に失敗しました。")
    assert_unchanged(before, root)
    print(f"{branch} を {remote_branch} に合わせました。ローカルファイルは未変更です。")
    others = run_git(
        ["for-each-ref", "--format=%(refname:short)", "refs/heads"], cwd=root
    )
    dirty_branches: list[str] = []
    for name in others.stdout.splitlines():
        if name == branch:
            continue
        for path in paths:
            hit = run_git(["ls-tree", "-r", "--name-only", name, "--", path], cwd=root)
            if hit.stdout.strip():
                dirty_branches.append(name)
                break
    if dirty_branches:
        print("古い履歴が残るローカルブランチ: " + ", ".join(dirty_branches))
        print("これらのブランチは push しないでください。")
    missing = unignored(root, paths)
    if missing:
        print("gitignore に無いパス: " + ", ".join(missing))
    print(
        "手元の reflog とオブジェクトには秘密が残っている場合があります。gc は自動では行いません。"
    )
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="秘密ファイルを Git 履歴から外す")
    commands = parser.add_subparsers(dest="command", required=True)
    plan = commands.add_parser("plan")
    plan.add_argument("--path", action="append", required=True)
    rewrite = commands.add_parser("rewrite")
    rewrite.add_argument("--path", action="append", required=True)
    rewrite.add_argument("--confirm-rewrite", action="store_true")
    push = commands.add_parser("push")
    push.add_argument("--state", required=True)
    push.add_argument("--confirm-push", action="store_true")
    adopt = commands.add_parser("adopt")
    adopt.add_argument("--state", required=True)
    return parser.parse_args()


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    args = parse_args()
    try:
        if args.command == "plan":
            return command_plan(args.path)
        if args.command == "rewrite":
            return command_rewrite(args.path, args.confirm_rewrite)
        if args.command == "push":
            return command_push(args.state, args.confirm_push)
        return command_adopt(args.state)
    except PurgeError as error:
        return fail(str(error))


if __name__ == "__main__":
    raise SystemExit(main())
