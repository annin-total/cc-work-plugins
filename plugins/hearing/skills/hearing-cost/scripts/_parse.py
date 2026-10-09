"""時刻・行の読み取り・モデル判別。"""

from __future__ import annotations

import json
import re
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

from _base import (
    EPOCH0, RE_ARN_MODEL, RE_FAMILY, RE_GEN_AFTER, RE_GEN_BEFORE, RE_NEW_FAMILY, RE_TOKEN, RE_TS,
    SESSION_GAP_SECONDS, TOP_FIELDS,
)
from _common import unescape


def parse_ts(s: Any, naive_local: bool = False) -> Optional[float]:
    """ISO8601 を epoch 秒に。読めなければ None。"""
    if not isinstance(s, str):
        return None
    m = RE_TS.match(s.strip())
    if not m:
        return None
    y, mo, d, hh, mm, ss, frac, tz = m.groups()
    try:
        dt = datetime(int(y), int(mo), int(d), int(hh or 0), int(mm or 0), int(ss or 0),
                      int((frac or "0")[:6].ljust(6, "0")))
        if tz is None:
            dt = dt.astimezone() if naive_local else dt.replace(tzinfo=timezone.utc)
        elif tz == "Z":
            dt = dt.replace(tzinfo=timezone.utc)
        else:
            sign = 1 if tz[0] == "+" else -1
            digits = tz[1:].replace(":", "")
            off = timedelta(hours=int(digits[:2]), minutes=int(digits[2:]))
            dt = dt.replace(tzinfo=timezone(sign * off))  # 24 時間以上の差は ValueError
        return dt.timestamp()
    except (ValueError, OverflowError, OSError):
        return None


def iso(epoch: Optional[float]) -> Optional[str]:
    if epoch is None:
        return None
    try:
        return (EPOCH0 + timedelta(seconds=epoch)).strftime("%Y-%m-%dT%H:%M:%SZ")
    except OverflowError:
        return None


def session_length(ts_list: List[float]) -> Tuple[float, int]:
    """(稼働分, 区間数)。行の間隔が 30 分を超えたら分割し、区間内の間隔を足す。"""
    if not ts_list:
        return 0.0, 0
    s = sorted(ts_list)
    active = 0.0
    segments = 1
    for a, b in zip(s, s[1:]):
        gap = b - a
        if gap > SESSION_GAP_SECONDS:
            segments += 1
        else:
            active += gap
    return active / 60.0, segments


def top_fields(line: str, wanted: Tuple[str, ...] = TOP_FIELDS) -> Tuple[Dict[str, Any], Dict[str, int]]:
    """JSON 行を全体パースせず、深さ 1 のキーの文字列値・真偽値と、値の開始位置を抜く。"""
    vals: Dict[str, Any] = {}
    offs: Dict[str, int] = {}
    depth = 0
    pending: Optional[str] = None
    for m in RE_TOKEN.finditer(line):
        tok = m.group(0)
        if tok in ("{", "["):
            if pending is not None:
                offs[pending] = m.start()
                pending = None
            depth += 1
            continue
        if tok in ("}", "]"):
            depth -= 1
            continue
        if m.group(2) and depth == 1:
            key = m.group(1)
            if key in wanted:
                rest = line[m.end():m.end() + 8].lstrip()
                if rest.startswith("true"):
                    vals[key] = True
                elif rest.startswith("false"):
                    vals[key] = False
                elif rest.startswith('"'):
                    pending = key
                elif rest[:1] in ("{", "["):
                    pending = key
            continue
        if pending is not None and not m.group(2):
            vals[pending] = unescape(m.group(1))
            pending = None
    return vals, offs


def decode_at(line: str, off: int) -> Any:
    try:
        return json.JSONDecoder().raw_decode(line, off)[0]
    except (ValueError, IndexError):
        return None


# ---------------------------------------------------------------- モデル判別

def classify_model(model: Any) -> Dict[str, Optional[str]]:
    """モデル ID をバケット（ファミリー名/other_claude/non_claude/unknown）と世代に分ける。"""
    if not isinstance(model, str) or not model.strip():
        return {"bucket": "unknown", "family": None, "generation": None}
    s = model.strip().lower()
    if s.startswith("arn:"):
        m = RE_ARN_MODEL.search(s)
        if not m:
            return {"bucket": "unknown", "family": None, "generation": None}
        s = m.group(1)
    if "anthropic." not in s and "claude-" not in s:
        return {"bucket": "non_claude", "family": None, "generation": None}
    fam_m = RE_FAMILY.search(s)
    family = fam_m.group(1) if fam_m else None
    if family is None:
        nm = RE_NEW_FAMILY.search(s)
        if nm and nm.group(1) != "instant":
            family = nm.group(1)
    if family is None:
        return {"bucket": "other_claude", "family": None, "generation": None}
    return {"bucket": family, "family": family, "generation": _generation(s, family)}


def _generation(s: str, family: str) -> Optional[str]:
    fam = re.escape(family)
    m = re.search(RE_GEN_AFTER.format(fam=fam), s) or re.search(RE_GEN_BEFORE.format(fam=fam), s)
    if not m:
        return None
    return m.group(1) + ("-" + m.group(2) if m.group(2) else "")
