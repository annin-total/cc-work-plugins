#!/usr/bin/env python3
"""gitignore 対象なのに Git が追跡しているパスを検査・追跡解除する。

ローカルファイルは変更しない。commit / push / 履歴改変は行わない。
"""

from __future__ import annotations

import argparse
import hashlib
import os
import subprocess
import sys
import tempfile
from pathlib import Path

RM_INDEX_ARGS = ["rm", "--cached", "-f", "-q"]


class SyncError(Exception):
    pass


def run_git(
    args: list[str], cwd: Path | None = None
) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(
        ["git", *args],
        cwd=cwd,
        check=False,
        capture_output=True,
    )


def decode(data: bytes) -> str:
    return data.decode("utf-8", errors="replace")


def split_nul(data: bytes) -> list[str]:
    if not data:
        return []
    return [decode(part) for part in data.split(b"\0") if part]


def fail(message: str) -> int:
    print(f"エラー: {message}", file=sys.stderr)
    return 1


def fingerprint(path: Path) -> str:
    if path.is_symlink():
        return "symlink:" + os.readlink(path)
    if not path.exists():
        return ""
    if path.is_dir():
        return "dir"
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return "file:" + digest.hexdigest()


def snapshot(paths: list[str], root: Path) -> dict[str, str]:
    return {path: fingerprint(root / path) for path in paths}


def assert_unchanged(before: dict[str, str], root: Path) -> None:
    after = snapshot(list(before), root)
    changed = [path for path, value in before.items() if after.get(path) != value]
    if changed:
        raise SyncError("ローカルファイルが変化しました: " + ", ".join(changed))


def git_toplevel() -> Path:
    result = run_git(["rev-parse", "--show-toplevel"])
    if result.returncode != 0:
        raise SyncError("Git の作業ツリーではありません。")
    return Path(decode(result.stdout).strip()).resolve()


def upstream_ref(root: Path) -> str | None:
    result = run_git(["rev-parse", "--abbrev-ref", "@{upstream}"], cwd=root)
    if result.returncode != 0:
        return None
    ref = decode(result.stdout).strip()
    return ref or None


def tracked_ignored(root: Path) -> list[str]:
    result = run_git(["ls-files", "-ci", "--exclude-standard", "-z"], cwd=root)
    if result.returncode != 0:
        raise SyncError(
            decode(result.stderr).strip() or "追跡中の無視対象を取得できません。"
        )
    return split_nul(result.stdout)


def tree_paths(ref: str, root: Path) -> list[str]:
    result = run_git(["ls-tree", "-r", "--name-only", "-z", ref], cwd=root)
    if result.returncode != 0:
        raise SyncError(
            f"{ref} のツリーを取得できません: {decode(result.stderr).strip()}"
        )
    return split_nul(result.stdout)


def ignored_paths(paths: list[str], root: Path) -> list[str]:
    if not paths:
        return []
    payload = "\0".join(paths) + "\0"
    result = subprocess.run(
        ["git", "check-ignore", "--no-index", "-z", "--stdin"],
        cwd=root,
        check=False,
        capture_output=True,
        input=payload.encode("utf-8"),
    )
    if result.returncode not in (0, 1):
        raise SyncError(
            decode(result.stderr).strip() or "gitignore 判定に失敗しました。"
        )
    return split_nul(result.stdout)


def print_section(title: str, paths: list[str]) -> None:
    print(f"{title}: {len(paths)} 件")
    for path in paths:
        print(f"  {path}")


def inspect(root: Path) -> tuple[list[str], list[str], list[str], str | None]:
    index_paths = tracked_ignored(root)
    has_head = run_git(["rev-parse", "HEAD"], cwd=root).returncode == 0
    head_paths = ignored_paths(tree_paths("HEAD", root), root) if has_head else []
    remote = upstream_ref(root)
    remote_paths = ignored_paths(tree_paths(remote, root), root) if remote else []
    return index_paths, head_paths, remote_paths, remote


def report(
    index_paths: list[str],
    head_paths: list[str],
    remote_paths: list[str],
    remote: str | None,
) -> None:
    print_section("index（追跡中かつ無視対象）", index_paths)
    print_section("HEAD（最新コミットに含まれ無視対象）", head_paths)
    if remote:
        print_section(f"{remote}（リモート追跡ブランチに含まれ無視対象）", remote_paths)
    else:
        print("リモート追跡ブランチ: 未設定")
    if not index_paths and not head_paths and not remote_paths:
        print("gitignore と追跡状態は一致しています。")
        return
    if index_paths:
        print("次の操作: --untrack で index から外す（作業ツリーは残る）")
    elif head_paths:
        print(
            "index は一致。HEAD を揃えるには commit が必要（このスクリプトは commit しない）"
        )
    else:
        print(
            "index と HEAD は一致。リモートを揃えるには push が必要（このスクリプトは push しない）"
        )


def untrack(paths: list[str], root: Path) -> None:
    if RM_INDEX_ARGS[:2] != ["rm", "--cached"]:
        raise SyncError("内部エラー: 追跡解除は git rm --cached のみです。")
    if not paths:
        print("追跡解除するパスはありません。")
        return

    before = snapshot(paths, root)
    with tempfile.NamedTemporaryFile(
        prefix="gitignore-sync-", suffix=".nul", delete=False
    ) as tmp:
        tmp.write("\0".join(paths).encode("utf-8") + b"\0")
        spec_path = tmp.name

    try:
        result = run_git(
            [
                *RM_INDEX_ARGS,
                f"--pathspec-from-file={spec_path}",
                "--pathspec-file-nul",
            ],
            cwd=root,
        )
    finally:
        Path(spec_path).unlink(missing_ok=True)

    if result.returncode != 0:
        raise SyncError(
            decode(result.stderr).strip() or "index からの追跡解除に失敗しました。"
        )

    remaining = tracked_ignored(root)
    if remaining:
        raise SyncError(
            "追跡解除後も index に無視対象が残っています: " + ", ".join(remaining)
        )

    assert_unchanged(before, root)
    print(f"追跡解除しました: {len(paths)} 件（ローカルファイルは未変更）")
    for path in paths:
        print(f"  {path}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="gitignore 対象の追跡を検査し、必要なら index からのみ外す"
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="検査のみ（デフォルト。--untrack 未指定時と同じ）",
    )
    parser.add_argument(
        "--untrack",
        action="store_true",
        help="無視対象を index から外す（作業ツリーは削除しない）",
    )
    return parser.parse_args()


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    args = parse_args()
    try:
        root = git_toplevel()
        index_paths, head_paths, remote_paths, remote = inspect(root)
        if args.untrack:
            untrack(index_paths, root)
            index_paths, head_paths, remote_paths, remote = inspect(root)
        report(index_paths, head_paths, remote_paths, remote)
        if args.untrack:
            return 0
        return 0 if not index_paths else 2
    except SyncError as error:
        return fail(str(error))


if __name__ == "__main__":
    raise SystemExit(main())
