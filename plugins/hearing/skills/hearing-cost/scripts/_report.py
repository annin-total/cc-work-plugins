"""集計結果の組み立て。"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Set, Tuple

from _base import (
    DEFAULT_CLEANUP_DAYS, RETENTION_NEAR_DAYS, SCHEMA_VERSION, TOKEN_TYPES, _add_tokens, _new_role,
    _new_session, _short_value, _sorted_counts, _tri, _tri_add, _zero_tokens, _zero_type_tokens,
)
from _collector import Collector
from _common import inc
from _parse import classify_model, iso
from _report_sections import ReportSectionsMixin


class Report(ReportSectionsMixin):
    """Collector の状態から出力 JSON を組み立てる。"""

    def __init__(self, c: Collector, settings: Dict[str, Any], installed: Dict[str, Any],
                 personal: Set[str], now: float) -> None:
        self.c = c
        self.settings = settings
        self.installed = installed
        self.personal = personal
        self.now = now

    def _local(self, epoch: float) -> datetime:
        dt = datetime.fromtimestamp(epoch, timezone.utc)
        return dt.astimezone() if self.c.local_tz else dt

    def build(self) -> Dict[str, Any]:
        c = self.c
        totals = _zero_tokens()
        buckets: Dict[str, Dict[str, Any]] = {}
        sessions: Dict[str, Dict[str, Any]] = {}
        session_all: Dict[str, Dict[str, Dict[str, int]]] = {}
        effort = {"effort": _tri(), "per_turn_effort": _tri()}
        by_version: Dict[str, Dict[str, int]] = {}
        by_day: Dict[str, int] = {}
        by_hour: Dict[str, int] = {"%02d" % h: 0 for h in range(24)}
        tools: Dict[str, int] = {}
        exts: Dict[str, int] = {}
        skills: Dict[str, int] = {}
        mcp: Dict[str, Dict[str, Any]] = {}
        api_calls = side_calls = 0
        in_period_keys: Set[str] = set()
        model_rows: Dict[str, List[Tuple[float, str, str, str]]] = {}
        sess_versions: Dict[str, Set[str]] = {}
        c.cov["records_after_dedup"] = len(c.records)
        c.cov["excluded_session_records"] = len(c.excluded_keys - set(c.records))
        for key in sorted(c.records):
            rec = c.records[key]
            cls = classify_model(rec["model"])
            fam = cls["bucket"] or "unknown"
            sa = session_all.setdefault(rec["sid"], {}).setdefault(fam, _zero_type_tokens())
            for k in TOKEN_TYPES:
                sa[k] += rec["u"][k]
            if rec["ts"] is None:
                c.cov["records_timestamp_missing"] += 1
                continue
            if not c._in_period(rec["ts"]):
                c.cov["records_out_of_period"] += 1
                continue
            in_period_keys.add(key)
            api_calls += 1
            side_calls += 1 if rec["side"] else 0
            _add_tokens(totals, rec["u"])
            b = buckets.setdefault(fam, {"api_calls": 0, "generations": {}, "tokens": _zero_tokens(),
                                         "by_role": {"main": _new_role(), "sidechain": _new_role()}})
            b["api_calls"] += 1
            inc(b["generations"], cls["generation"] or "unknown")
            _add_tokens(b["tokens"], rec["u"])
            role = b["by_role"]["sidechain" if rec["side"] else "main"]
            role["api_calls"] += 1
            role["output_unfinalized_calls"] += 0 if rec["final"] else 1
            _add_tokens(role["tokens"], rec["u"])
            ver = _short_value(rec["version"]) if rec["version"] else "unknown"
            v = by_version.setdefault(ver, {"records": 0, "effort_observed": 0, "per_turn_effort_observed": 0})
            v["records"] += 1
            for name, field in (("effort", "effort"), ("per_turn_effort", "pte")):
                _tri_add(effort[name], rec[field])
                if rec[field] is not None:
                    v[name + "_observed"] += 1
            lt = self._local(rec["ts"])
            inc(by_day, lt.strftime("%Y-%m-%d"))
            inc(by_hour, "%02d" % lt.hour)
            if rec["sid"]:
                sess_versions.setdefault(rec["sid"], set()).add(ver)
                if not rec["side"] and rec["model"]:
                    model_rows.setdefault(rec["sid"], []).append((rec["ts"], key, rec["model"], ver))
            s = sessions.setdefault(rec["sid"], _new_session())
            s["api_calls"] += 1
            s["sidechain_calls"] += 1 if rec["side"] else 0
            _add_tokens(s["tokens"], rec["u"])
            inc(s["models"], fam)
            if rec["cwd"]:
                inc(s["cwds"], rec["cwd"])
            if rec["effort"] is not None:
                inc(s["effort"], rec["effort"])
        for tid in sorted(c.tool_uses):
            key, name, ext, skill = c.tool_uses[tid]
            if key not in in_period_keys:
                continue
            sid = c.records[key]["sid"]
            s = sessions.setdefault(sid, _new_session())
            inc(tools, name)
            inc(s["tools"], name)
            if ext:
                inc(exts, ext)
                inc(s["exts"], ext)
            if skill:
                inc(skills, skill)
            if name.startswith("mcp__"):
                parts = name.split("__")
                server = parts[1] if len(parts) > 2 and parts[1] else "(unparsable)"
                m = mcp.setdefault(server, {"calls": 0, "tools": set()})
                m["calls"] += 1
                m["tools"].add(name)
        for sid, ts_list in c.session_ts.items():
            s = sessions.setdefault(sid, _new_session())
            s["ts"] = ts_list
        c.ctx.add_model_changes(model_rows)
        return self._assemble(totals, buckets, sessions, session_all, effort, by_version, by_day,
                              by_hour, tools, exts, skills, mcp, api_calls, side_calls, sess_versions)

    def _assemble(self, totals: Dict[str, int], buckets: Dict[str, Any], sessions: Dict[str, Any],
                  session_all: Dict[str, Any], effort: Dict[str, Any], by_version: Dict[str, Any],
                  by_day: Dict[str, int], by_hour: Dict[str, int], tools: Dict[str, int],
                  exts: Dict[str, int], skills: Dict[str, int], mcp: Dict[str, Any],
                  api_calls: int, side_calls: int, sess_versions: Dict[str, Set[str]]) -> Dict[str, Any]:
        c = self.c
        cov = dict(c.cov)
        bad = sum(cov["lines_unreadable"].values()) + cov["lines_oversize_skipped"]
        cov["coverage_ratio"] = round((cov["lines_total"] - bad) / cov["lines_total"], 4) if cov["lines_total"] else None
        cov["dedup_removed"] = cov["records_before_dedup"] - cov["records_after_dedup"]
        sess_out = self._sessions(sessions, totals)
        return {
            "schema_version": SCHEMA_VERSION,
            "generated_at": iso(self.now),
            "params": {"start": iso(c.start), "end": iso(c.end), "timezone": "local" if c.local_tz else "utc",
                       "utc_offset_minutes": self._offset_minutes(), "exclude_session_given": bool(c.exclude),
                       "max_line_bytes": c.max_bytes},
            "coverage": cov,
            "history_range": {"oldest_ts": iso(c.oldest), "newest_ts": iso(c.newest),
                              "files_with_lines": c.files_with_lines},
            "retention": self._retention(),
            "settings": self.settings,
            "line_types": dict(sorted(c.line_types.items())),
            "versions": dict(sorted(c.versions.items())),
            "totals": {"api_calls": api_calls, "sidechain_api_calls": side_calls,
                       "tokens_by_type": totals, "active_days": len(by_day),
                       "note": "token types are listed separately on purpose; do not add them up"},
            "models": {"buckets": dict(sorted(buckets.items()))},
            "effort": {"effort": effort["effort"], "per_turn_effort": effort["per_turn_effort"],
                       "by_version": dict(sorted(by_version.items())),
                       "note": "absent_n means not recorded (e.g. older version), not zero or low"},
            "sessions": sess_out,
            "context_ops": c.ctx.report(len(sessions), sess_versions, self._longest(sessions)),
            "automation": c.auto.report(sessions, tools, c.commands),
            "projects": self._projects(sessions),
            "tools": {"calls_by_name": _sorted_counts(tools), "file_extensions": _sorted_counts(exts),
                      "result_chars": self._result_chars(), "tool_results_dir": dict(c.tool_results_dir)},
            "skills": self._skills(skills),
            "mcp": {"servers_used": len(mcp), "configured_servers_count": self.settings.get("mcp_servers_count"),
                    "servers": {k: {"calls": v["calls"], "distinct_tools": len(v["tools"])}
                                for k, v in sorted(mcp.items())}},
            "cost_state": self._cost_state(session_all, set(sessions)),
            "timeline": {"timezone": "local" if c.local_tz else "utc", "by_day": dict(sorted(by_day.items())),
                         "by_hour": by_hour},
        }

    def _offset_minutes(self) -> int:
        if not self.c.local_tz:
            return 0
        off = datetime.fromtimestamp(self.now, timezone.utc).astimezone().utcoffset()
        return int(off.total_seconds() // 60) if off else 0

    def _retention(self) -> Dict[str, Any]:
        c = self.c
        days = self.settings.get("cleanup_period_days")
        src = "settings" if days is not None else "default_assumed"
        eff_days = days if days is not None else DEFAULT_CLEANUP_DAYS
        starts_after = c.oldest is not None and c.oldest > c.start + 86400
        cutoff = self.now - eff_days * 86400
        near = c.oldest is not None and abs(c.oldest - cutoff) <= RETENTION_NEAR_DAYS * 86400
        return {"cleanup_period_days": eff_days, "cleanup_period_days_source": src,
                "history_starts_after_period_start": starts_after, "oldest_near_cleanup_cutoff": near,
                "suspected_gap": bool(starts_after and near),
                "note": "suspicion only; older history may have been removed by retention or never existed"}
