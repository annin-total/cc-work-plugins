"""無人・自動実行の手がかり（起動のしかた・ターンの出どころ・定期実行系の呼び出し）を集計する。_collector.py から呼ばれる。"""

from __future__ import annotations

from typing import Any, Dict, Set, Tuple

from _base import _add_tokens, _short_value, _sorted_counts, _tri, _tri_add, _zero_tokens

SCHEDULE_TOOLS = ("ScheduleWakeup", "CronCreate", "CronDelete", "CronList")
SCHEDULE_COMMANDS = ("loop", "schedule")
NOT_RECORDED = "not_recorded"
ORIGIN_FIELDS = (("turn_origin", "turnOrigin"), ("prompt_source", "promptSource"))


class Automation:
    """期間内の行から、セッションの起動のしかたと user 行の出どころを溜める。"""

    def __init__(self) -> None:
        self.session_entry: Dict[str, Tuple[float, str]] = {}
        self.session_entry_values: Dict[str, Set[str]] = {}
        self.origins = {name: _tri() for name, _ in ORIGIN_FIELDS}
        self.by_version: Dict[str, Dict[str, int]] = {}

    def add_entrypoint(self, sid: str, ts: float, raw: Any) -> None:
        """セッションの起動のしかた。最も早い行の値を採り、値が混在したら mixed に数える。"""
        if not sid or not isinstance(raw, str) or not raw:
            return
        value = _short_value(raw)
        self.session_entry_values.setdefault(sid, set()).add(value)
        cur = self.session_entry.get(sid)
        if cur is None or (ts, value) < cur:
            self.session_entry[sid] = (ts, value)

    def add_user(self, vals: Dict[str, Any], version: str) -> None:
        """tool 結果でも sidechain でもない user 行 1 件。出どころの記録がある行とない行を分けて数える。"""
        row = self.by_version.setdefault(version, {"user_lines": 0, "turn_origin_observed": 0,
                                                   "prompt_source_observed": 0})
        row["user_lines"] += 1
        for name, key in ORIGIN_FIELDS:
            raw = vals.get(key)
            value = _short_value(raw) if isinstance(raw, str) and raw else None
            _tri_add(self.origins[name], value)
            if value is not None:
                row[name + "_observed"] += 1

    def report(self, sessions: Dict[str, Dict[str, Any]], tools: Dict[str, int],
               commands: Dict[str, int]) -> Dict[str, Any]:
        """sessions: 期間内のセッション集計（api_calls・tokens・tools を持つ）。tools・commands: 名前別の件数。"""
        entry: Dict[str, Dict[str, Any]] = {}
        for sid, s in sessions.items():
            name = self.session_entry[sid][1] if sid in self.session_entry else NOT_RECORDED
            e = entry.setdefault(name, {"sessions": 0, "api_calls": 0, "tokens": _zero_tokens()})
            e["sessions"] += 1
            e["api_calls"] += s["api_calls"]
            _add_tokens(e["tokens"], s["tokens"])
        mixed = sum(1 for sid in sessions if len(self.session_entry_values.get(sid, ())) > 1)
        schedule = {name: {"calls": tools.get(name, 0),
                           "sessions": sum(1 for s in sessions.values() if s["tools"].get(name))}
                    for name in SCHEDULE_TOOLS}
        return {
            "entrypoint": {"by_entrypoint": dict(sorted(entry.items())), "mixed_sessions": mixed,
                           "note": "セッションの値は期間内で最も早い行の entrypoint。記録の無いセッションは "
                                   + NOT_RECORDED + "（0 件ではない）。tokens は種別ごとで合算しない"},
            "turn_origin": {**{k: _origin(v) for k, v in self.origins.items()},
                            "by_version": dict(sorted(self.by_version.items())),
                            "note": "対象は tool 結果・sidechain 以外の user 行。absent_n は記録なし（古い版や、"
                                    "記録が付かない行）で 0 件ではない"},
            "schedule": {"tools": schedule,
                         "commands": {name: commands.get(name, 0) for name in SCHEDULE_COMMANDS}},
        }


def _origin(t: Dict[str, Any]) -> Dict[str, Any]:
    return {"observed_n": t["observed_n"], "absent_n": t["absent_n"], "values": _sorted_counts(t["values"])}
