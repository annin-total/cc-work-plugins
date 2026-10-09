"""文脈の区切り・切り替え操作（compact・clear・resume・model）の回数を集計する。_collector.py から呼ばれる。"""

from __future__ import annotations

from typing import Any, Dict, List, Set, Tuple

from _common import inc

SLASH_OPS = {"clear": "clear", "resume": "resume_command", "model": "model_command"}
COMPACT_OPS = {"manual": "compact_manual", "auto": "compact_auto"}
OP_NAMES = ("compact_manual", "compact_auto", "clear", "resume_command", "model_command", "model_change")
TOP_N = 5
NOT_DETECTED = ["rewind", "resume_cli_flags", "branch"]


def _median(values: List[int]) -> float:
    s = sorted(values)
    n = len(s)
    return float(s[n // 2]) if n % 2 else (s[n // 2 - 1] + s[n // 2]) / 2


class ContextOps:
    """期間内の操作を (op, sessionId, 版) の組で溜め、uuid で重複を除く。"""

    def __init__(self) -> None:
        self.events: List[Tuple[str, str, str]] = []
        self.pre_tokens: List[int] = []
        self.seen_boundary: Set[str] = set()

    def add_command(self, name: str, sid: str, version: str) -> None:
        op = SLASH_OPS.get(name)
        if op:
            self.events.append((op, sid, version))

    def add_boundary(self, uuid: str, sid: str, version: str, meta: Any) -> None:
        if uuid:
            if uuid in self.seen_boundary:
                return
            self.seen_boundary.add(uuid)
        if not isinstance(meta, dict):
            return
        op = COMPACT_OPS.get(meta.get("trigger"))  # type: ignore[arg-type]
        if op is None:
            return
        self.events.append((op, sid, version))
        pre = meta.get("preTokens")
        if op == "compact_auto" and isinstance(pre, int) and not isinstance(pre, bool) and pre >= 0:
            self.pre_tokens.append(pre)

    def add_model_changes(self, per_session: Dict[str, List[Tuple[float, str, str, str]]]) -> None:
        """per_session: sid -> (ts, key, model, version) の列。本体の隣り合う記録でモデルが変わった回数を数える。"""
        for sid, rows in per_session.items():
            rows.sort()
            for prev, cur in zip(rows, rows[1:]):
                if prev[2] != cur[2]:
                    self.events.append(("model_change", sid, cur[3]))

    def report(self, session_count: int, session_versions: Dict[str, Set[str]],
               longest: List[Tuple[str, float, str]]) -> Dict[str, Any]:
        """longest: 長い順の (sid, 稼働分, ラベル)。session_versions: sid -> 期間内に見えた版。"""
        by_op: Dict[str, Dict[str, int]] = {op: {} for op in OP_NAMES}
        by_ver: Dict[str, Dict[str, Any]] = {}
        for sids in session_versions.values():
            for v in sids:
                by_ver.setdefault(v, {"sessions": 0, **{op: 0 for op in OP_NAMES}})["sessions"] += 1
        for op, sid, ver in self.events:
            inc(by_op[op], sid)
            by_ver.setdefault(ver or "unknown", {"sessions": 0, **{o: 0 for o in OP_NAMES}})[op] += 1
        ops: Dict[str, Any] = {}
        for op in OP_NAMES:
            total = sum(by_op[op].values())
            ops[op] = {"total": total, "sessions": len(by_op[op]),
                       "per_session": round(total / session_count, 3) if session_count else None}
        pre = self.pre_tokens
        return {
            "definition": "compact は system 行 compact_boundary の trigger（manual/auto）。clear・resume・model は "
                          "<command-name> の起動回数（model_command は切り替えなしの起動を含む）。model_change は "
                          "本体の隣り合う assistant 記録でモデルが変わった回数",
            "ops": ops,
            "auto_compact_pre_tokens": {"observed_n": len(pre),
                                        "median": _median(pre) if pre else None, "max": max(pre) if pre else None},
            "longest_sessions": [{"session": label, "active_minutes": round(mins, 1),
                                  "ops": {op: by_op[op].get(sid, 0) for op in OP_NAMES}}
                                 for sid, mins, label in longest[:TOP_N]],
            "by_version": dict(sorted(by_ver.items())),
            "not_detected": NOT_DETECTED,
            "note": "by_version で 0 件の版は記録が無い版かもしれない。0 回と記録なしを区別して読む",
        }
