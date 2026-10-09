"""Report の出力セクション。"""

from __future__ import annotations

from typing import Any, Dict, List, Set, Tuple

from _base import (
    LENGTH_BUCKET_MAX, LENGTH_BUCKETS, RESULT_BUCKET_MAX, RESULT_BUCKETS, TOKEN_TYPES, TOP_N, _add_tokens,
    _bucket, _label, _percentile, _ranked, _sorted_counts, _zero_tokens, _zero_type_tokens,
)
from _common import inc
from _parse import session_length
from _settings import classify_skill


class ReportSectionsMixin:
    def _sessions(self, sessions: Dict[str, Any], totals: Dict[str, int]) -> Dict[str, Any]:
        lengths: List[float] = []
        dist: Dict[str, int] = {}
        agents: Set[str] = set()
        details: Dict[str, Any] = {}
        for sid in sorted(sessions):
            s = sessions[sid]
            minutes, segs = session_length(s["ts"])
            s["minutes"], s["segments"] = minutes, segs
            lengths.append(minutes)
            inc(dist, _bucket(minutes, LENGTH_BUCKETS, LENGTH_BUCKET_MAX))
            agents |= self.c.session_agents.get(sid, set())
        tops: Dict[str, List[Dict[str, Any]]] = {}
        for ttype, name in (("output", "top_by_output"), ("cache_creation", "top_by_cache_creation"),
                            ("input", "top_by_input"), ("cache_read", "top_by_cache_read")):
            ranked = _ranked(sessions, lambda s: s["tokens"][ttype])[:TOP_N]
            tops[name] = []
            for sid, s in ranked:
                if s["tokens"][ttype] <= 0:
                    continue
                share = s["tokens"][ttype] / totals[ttype] if totals[ttype] else 0.0
                files = self.c.session_files.get(sid, {})
                top_file = max(sorted(files), key=lambda k: files[k]) if files else None
                tops[name].append({"session": _label("S", sid), "session_id": sid, "file": top_file,
                                   "value": s["tokens"][ttype], "share": round(share, 4)})
                details[_label("S", sid)] = self._session_detail(sid, s)
        out: Dict[str, Any] = {
            "count": len(sessions), "subagents_distinct": len(agents),
            "length_definition": "split when the gap between lines exceeds 30 minutes; sum active time",
            "active_minutes": {"total": round(sum(lengths), 1), "median": round(_percentile(lengths, 0.5), 1),
                               "p90": round(_percentile(lengths, 0.9), 1), "max": round(max(lengths or [0.0]), 1)},
            "length_buckets": dist,
        }
        out.update(tops)
        out["details"] = dict(sorted(details.items()))
        return out

    @staticmethod
    def _longest(sessions: Dict[str, Any]) -> List[Tuple[str, float, str]]:
        ranked = _ranked(sessions, lambda s: s["minutes"])
        return [(sid, s["minutes"], _label("S", sid)) for sid, s in ranked]

    def _session_detail(self, sid: str, s: Dict[str, Any]) -> Dict[str, Any]:
        cwd = _main_cwd(s)
        return {"project": _label("P", cwd) if cwd else None, "api_calls": s["api_calls"],
                "turns": self.c.session_turns.get(sid, 0), "active_minutes": round(s["minutes"], 1),
                "segments": s["segments"], "subagents": len(self.c.session_agents.get(sid, set())),
                "sidechain_ratio": round(s["sidechain_calls"] / s["api_calls"], 4) if s["api_calls"] else 0.0,
                "tokens": s["tokens"], "model_buckets": _sorted_counts(s["models"]),
                "effort": _sorted_counts(s["effort"]), "tools": _sorted_counts(s["tools"]),
                "file_extensions": _sorted_counts(s["exts"])}

    def _projects(self, sessions: Dict[str, Any]) -> Dict[str, Any]:
        proj: Dict[str, Dict[str, Any]] = {}
        for sid in sorted(sessions):
            s = sessions[sid]
            if not s["cwds"]:
                continue
            cwd = _main_cwd(s)
            p = proj.setdefault(_label("P", cwd), {"sessions": 0, "api_calls": 0, "tokens": _zero_tokens()})
            p["sessions"] += 1
            p["api_calls"] += s["api_calls"]
            _add_tokens(p["tokens"], s["tokens"])
        ranked = _ranked(proj, lambda v: v["tokens"]["output"])[:TOP_N]
        return {"count": len(proj), "label_rule": "P- + first 8 hex of sha256(cwd)",
                "top_by_output": [dict(label=k, **v) for k, v in ranked]}

    def _result_chars(self) -> Dict[str, Any]:
        dist: Dict[str, int] = {}
        by_tool: Dict[str, Dict[str, int]] = {}
        max_by_tool: Dict[str, int] = {}
        total = count = mx = 0
        for tid in sorted(self.c.tool_results):
            n, ts, _sid = self.c.tool_results[tid]
            if not self.c._in_period(ts):
                continue
            count += 1
            total += n
            mx = max(mx, n)
            inc(dist, _bucket(n, RESULT_BUCKETS, RESULT_BUCKET_MAX))
            tu = self.c.tool_uses.get(tid)
            name = tu[1] if tu else "(unmatched)"
            t = by_tool.setdefault(name, {"count": 0, "chars": 0})
            t["count"] += 1
            t["chars"] += n
            max_by_tool[name] = max(max_by_tool.get(name, 0), n)
        top_max = _ranked(max_by_tool, lambda v: v)[:TOP_N]
        return {"count": count, "chars_total": total, "chars_max": mx, "buckets": dist,
                "top_max_by_tool": [{"tool": k, "chars_max": v} for k, v in top_max],
                "by_tool": dict(sorted(by_tool.items(), key=lambda kv: (-kv[1]["chars"], kv[0])))}

    def _skills(self, skill_calls: Dict[str, int]) -> Dict[str, Any]:
        cls = lambda n: classify_skill(n, self.personal)  # noqa: E731
        attr = {k: {"sessions": len(v), "lines": self.c.attribution_lines.get(k, 0), "classification": cls(k)}
                for k, v in sorted(self.c.attribution.items())}
        return {
            "skill_tool": {k: {"calls": v, "classification": cls(k)} for k, v in sorted(skill_calls.items())},
            "slash_commands": {k: {"count": v, "classification": cls(k)} for k, v in sorted(self.c.commands.items())},
            "attribution_skill": attr,
            "attribution_note": "sessions = distinct (sessionId, skill); lines are not invocation counts; "
                                "counted from lines whose timestamp is in the period",
            "classification_rule": "':' in name = plugin; matches config-dir/skills = personal; "
                                   "otherwise builtin_or_unknown",
            "installed": self.installed,
        }

    def _cost_state(self, session_all: Dict[str, Any], period_sessions: Set[str]) -> Dict[str, Any]:
        cs: Dict[str, Dict[str, int]] = {}
        tr: Dict[str, Dict[str, int]] = {}
        n = 0
        for sid in sorted(self.c.cost_state):
            if sid not in period_sessions:
                continue
            n += 1
            _add_by_family(cs, self.c.cost_state[sid])
            _add_by_family(tr, session_all.get(sid, {}))
        by_family = {}
        for fam in sorted(set(cs) | set(tr)):
            a = cs.get(fam, _zero_type_tokens())
            b = tr.get(fam, _zero_type_tokens())
            by_family[fam] = {"cost_state": a, "transcript": b,
                              "outside_transcript": {k: a[k] - b[k] for k in TOKEN_TYPES},
                              "only_in_cost_state": fam not in tr}
        return {"confidence": "estimate", "sessions_with_snapshot": n, "by_family": by_family,
                "note": "last snapshot per session (largest cumulative) minus deduplicated assistant usage of "
                        "the same sessions over all history; resume/fork behaviour unconfirmed; "
                        "sidechain output_tokens in transcripts is often a start-of-stream value "
                        "(see models.buckets.*.by_role.sidechain.output_unfinalized_calls), so a large "
                        "output gap is expected; money fields are discarded"}


def _main_cwd(s: Dict[str, Any]) -> str:
    """記録が最も多い cwd（同数ならキーの昇順で先）。無ければ空文字。"""
    return max(sorted(s["cwds"]), key=lambda k: s["cwds"][k]) if s["cwds"] else ""


def _add_by_family(dst: Dict[str, Dict[str, int]], src: Dict[str, Dict[str, int]]) -> None:
    for fam, toks in src.items():
        d = dst.setdefault(fam, _zero_type_tokens())
        for k in TOKEN_TYPES:
            d[k] += toks[k]
