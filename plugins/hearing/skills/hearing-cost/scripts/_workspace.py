"""実行ごとの作業フォルダ <root>/hearing-cost/<日時>/work を作る（init サブコマンドの実体）。"""

from __future__ import annotations

import json
import os
from datetime import datetime
from typing import Callable, Dict, Union

from _common import ArgError

BASE_NAME = "hearing-cost"
GITIGNORE_BODY = "*\n"
MAX_SUFFIX = 99
RUN_TIME_FORMAT = "%Y%m%d-%H%M"


def _now() -> datetime:
    return datetime.now()


def _ensure_base(root: str) -> bool:
    """<root>/hearing-cost と .gitignore を用意し、.gitignore を作ったかを返す。"""
    base = os.path.join(root, BASE_NAME)
    if os.path.islink(base) or (os.path.exists(base) and not os.path.isdir(base)):
        raise ArgError("hearing-cost exists but is not a directory")
    if not os.path.isdir(base):
        os.mkdir(base)
    try:
        with open(os.path.join(base, ".gitignore"), "x", encoding="utf-8", newline="\n") as f:
            f.write(GITIGNORE_BODY)
    except FileExistsError:
        return False
    return True


def _make_run_dir(base: str, stamp: str) -> str:
    for n in range(1, MAX_SUFFIX + 1):
        path = os.path.join(base, stamp if n == 1 else "%s-%d" % (stamp, n))
        try:
            os.mkdir(path)
            return path
        except FileExistsError:
            continue
    raise ArgError("too many runs in the same minute")


def init_workspace(root: str, now: Callable[[], datetime] = _now) -> Dict[str, Union[str, bool]]:
    root = os.path.abspath(root)
    if not os.path.isdir(root):
        raise ArgError("root not found")
    created = _ensure_base(root)
    run_dir = _make_run_dir(os.path.join(root, BASE_NAME), now().strftime(RUN_TIME_FORMAT))
    work_dir = os.path.join(run_dir, "work")
    os.mkdir(work_dir)
    return {"run_dir": run_dir, "work_dir": work_dir, "created_gitignore": created}


def format_result(result: Dict[str, Union[str, bool]]) -> str:
    return json.dumps(result, ensure_ascii=False)
