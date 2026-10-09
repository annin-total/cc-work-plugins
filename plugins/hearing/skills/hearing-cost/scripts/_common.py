"""collect 系のモジュールが共通で使う小物。"""

from __future__ import annotations

import json
import os
from typing import Any, Dict, Iterator, List, Optional, Tuple

DEFAULT_MAX_LINE_BYTES = 50_000_000
SKIP_WALK_DIRS = ("node_modules", ".git")


class ArgError(Exception):
    """引数の誤り（終了コード 2）。"""


def inc(d: Dict[str, int], k: str, n: int = 1) -> None:
    d[k] = d.get(k, 0) + n


def unescape(raw: str) -> str:
    if "\\" not in raw:
        return raw
    try:
        v = json.loads('"' + raw + '"')
        return v if isinstance(v, str) else ""
    except ValueError:
        return ""


def iter_lines(path: str, max_bytes: int) -> Iterator[Tuple[int, Optional[bytes]]]:
    """(行番号, 行バイト列) を返す。上限超えは None。改行は除く。"""
    with open(path, "rb") as f:
        n = 0
        while True:
            raw = f.readline(max_bytes + 2)
            if not raw:
                return
            n += 1
            if raw.endswith(b"\n"):
                body = raw.rstrip(b"\r\n")
            elif len(raw) < max_bytes + 2:
                body = raw.rstrip(b"\r")
            else:
                while True:
                    chunk = f.readline(1 << 20)
                    if not chunk or chunk.endswith(b"\n"):
                        break
                yield n, None
                continue
            if len(body) > max_bytes:
                yield n, None
                continue
            if n == 1 and body.startswith(b"\xef\xbb\xbf"):
                body = body[3:]
            yield n, body


def write_json(path: str, data: Any) -> None:
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        json.dump(data, f, ensure_ascii=False, indent=1, sort_keys=False)
        f.write("\n")


def skill_files(root: str, recursive: bool) -> List[str]:
    """SKILL.md の一覧。recursive では <...>/skills/<名前>/SKILL.md を探し、node_modules と .git は入らない。"""
    found: List[str] = []
    if not os.path.isdir(root):
        return found
    if not recursive:
        for name in sorted(os.listdir(root)):
            p = os.path.join(root, name, "SKILL.md")
            if os.path.isfile(p):
                found.append(p)
        return found
    for dirpath, dirs, files in os.walk(root):
        dirs[:] = [d for d in dirs if d not in SKIP_WALK_DIRS]
        if "SKILL.md" in files and os.path.basename(os.path.dirname(dirpath)) == "skills":
            found.append(os.path.join(dirpath, "SKILL.md"))
    return sorted(found)
