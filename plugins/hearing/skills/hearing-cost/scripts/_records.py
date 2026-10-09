"""Collector の行種別ごとの処理。状態は Collector が持つ。"""

from __future__ import annotations

from typing import Any, Dict, Optional

from _base import (
    CACHE_SUBFIELDS, FILE_TOOL_KEYS, RE_COMMAND, TOP_LINE_TYPES, USAGE_FIELDS, _content_chars, _extension,
    _int, _safe_name, _short_value, _zero_tokens,
)
from _common import inc
from _parse import decode_at


class RecordMixin:
    # ---- assistant 行

    def _assistant(self, d: Dict[str, Any], fidx: int, lineno: int) -> None:
        self.cov["assistant_lines"] += 1
        msg = d.get("message") if isinstance(d.get("message"), dict) else {}
        ts = self._ts(d.get("timestamp"))
        self._seen_ts(ts)
        if msg.get("model") == "<synthetic>":
            self.cov["synthetic_lines"] += 1
            return
        mid, rid, uid = msg.get("id"), d.get("requestId"), d.get("uuid")
        if (isinstance(mid, str) and mid) or (isinstance(rid, str) and rid):
            key = "m:" + (mid if isinstance(mid, str) else "") + "|" + (rid if isinstance(rid, str) else "")
        elif isinstance(uid, str) and uid:
            key = "u:" + uid
            self.cov["dedup_fallback_uuid"] += 1
        else:
            key = "n:%d:%d" % (fidx, lineno)
            self.cov["dedup_no_key"] += 1
        sid = d.get("sessionId") if isinstance(d.get("sessionId"), str) else ""
        if self.exclude and sid == self.exclude:
            self.cov["excluded_session_lines"] += 1
            self.excluded_keys.add(key)
            return
        self.cov["records_before_dedup"] += 1
        if sid and self._in_period(ts):
            self.session_ts.setdefault(sid, []).append(ts)  # type: ignore[arg-type]
            inc(self.session_files.setdefault(sid, {}), self.cur_file)
            self.auto.add_entrypoint(sid, ts, d.get("entrypoint"))  # type: ignore[arg-type]
            agent = d.get("agentId")
            if isinstance(agent, str) and agent:
                self.session_agents.setdefault(sid, set()).add(agent)
        ver = d.get("version") if isinstance(d.get("version"), str) else "unknown"
        inc(self.versions, _short_value(ver) if ver != "unknown" else ver)
        rec = self.records.get(key)
        if rec is None:
            rec = {"ts": None, "sid": sid, "agent": "", "side": False, "cwd": "", "model": "",
                   "effort": None, "pte": None, "version": "", "u": _zero_tokens(),
                   "final": False, "tools": set(), "attr": None}
            self.records[key] = rec
        self._merge(rec, d, msg, ts, key)

    def _merge(self, rec: Dict[str, Any], d: Dict[str, Any], msg: Dict[str, Any],
               ts: Optional[float], key: str) -> None:
        if ts is not None and (rec["ts"] is None or ts < rec["ts"]):
            rec["ts"] = ts
        for field, src in (("sid", d.get("sessionId")), ("agent", d.get("agentId")), ("cwd", d.get("cwd")),
                           ("model", msg.get("model")), ("version", d.get("version"))):
            if isinstance(src, str) and src and (not rec[field] or src < rec[field]):
                rec[field] = src
        rec["side"] = rec["side"] or d.get("isSidechain") is True
        for field, src in (("effort", d.get("effort")), ("pte", d.get("perTurnEffort"))):
            if src is not None:
                v = _short_value(src) if not isinstance(src, (int, float)) else _short_value(str(src))
                # 文字列の大小に意味はない。意味があるのは「欠落（None）か値ありか」だけで、
                # 値が割れたときも順序に依らず同じ値になるよう最大を取る。
                if rec[field] is None or v > rec[field]:
                    rec[field] = v
        attr = _safe_name(d.get("attributionSkill"))
        if attr and (rec["attr"] is None or attr < rec["attr"]):
            rec["attr"] = attr
        if attr and rec["sid"] and self._in_period(ts):
            self.attribution.setdefault(attr, set()).add(rec["sid"])
            inc(self.attribution_lines, attr)
        if isinstance(msg.get("stop_reason"), str) and msg["stop_reason"]:
            rec["final"] = True  # サブエージェントの行は stop_reason が null のまま output_tokens が開始時の値で止まる
        usage = msg.get("usage")
        if isinstance(usage, dict):
            u = rec["u"]
            for k, f in USAGE_FIELDS.items():
                u[k] = max(u[k], _int(usage.get(f)))
            cc = usage.get("cache_creation")
            if isinstance(cc, dict):
                for k, f in CACHE_SUBFIELDS.items():
                    u[k] = max(u[k], _int(cc.get(f)))
        else:
            self.cov["usage_missing_lines"] += 1
        content = msg.get("content")
        if isinstance(content, list):
            for idx, block in enumerate(content):
                if isinstance(block, dict) and block.get("type") == "tool_use":
                    self._tool_use(block, key, idx, rec)

    def _tool_use(self, block: Dict[str, Any], key: str, idx: int, rec: Dict[str, Any]) -> None:
        name = _safe_name(block.get("name")) or "(unparsable)"
        tid = block.get("id") if isinstance(block.get("id"), str) and block.get("id") else "%s#%s#%d" % (key, name, idx)
        inp = block.get("input") if isinstance(block.get("input"), dict) else {}
        ext = None
        for k in FILE_TOOL_KEYS:
            if isinstance(inp.get(k), str):
                ext = _extension(inp[k])
                break
        skill = None
        if name == "Skill":
            skill = _safe_name(inp.get("skill")) or "(unparsable)"
        self.tool_uses[tid] = (key, name, ext, skill)
        rec["tools"].add(tid)

    # ---- assistant 以外の行

    def _other(self, vals: Dict[str, Any], offs: Dict[str, int], text: str,
               parsed: Optional[Dict[str, Any]]) -> bool:
        ltype = vals.get("type")
        if not isinstance(ltype, str) or not ltype:
            self._broken("no_type")
            return False
        inc(self.line_types, ltype if ltype in TOP_LINE_TYPES else "_other")
        sid = vals.get("sessionId") if isinstance(vals.get("sessionId"), str) else ""
        if ltype == "cost-state":
            mu = parsed.get("modelUsage") if parsed else (decode_at(text, offs["modelUsage"]) if "modelUsage" in offs else None)
            self._cost_state(sid, mu)
            return True
        if self.exclude and sid and sid == self.exclude:
            self.cov["excluded_session_lines"] += 1
            return True
        ts = self._ts(vals.get("timestamp"))
        self._seen_ts(ts)
        if not self._in_period(ts) or not sid:
            return True
        self.session_ts.setdefault(sid, []).append(ts)  # type: ignore[arg-type]
        agent = vals.get("agentId")
        if isinstance(agent, str) and agent:
            self.session_agents.setdefault(sid, set()).add(agent)
        self.auto.add_entrypoint(sid, ts, vals.get("entrypoint"))
        if ltype == "user":
            self._user(vals, offs, text, parsed, sid, ts)  # type: ignore[arg-type]
        elif ltype == "system" and vals.get("subtype") == "compact_boundary":
            meta = parsed.get("compactMetadata") if parsed else (
                decode_at(text, offs["compactMetadata"]) if "compactMetadata" in offs else None)
            ver = _short_value(vals.get("version")) if vals.get("version") else "unknown"
            self.ctx.add_boundary(str(vals.get("uuid") or ""), sid, ver, meta)
        return True

    def _user(self, vals: Dict[str, Any], offs: Dict[str, int], text: str,
              parsed: Optional[Dict[str, Any]], sid: str, ts: float) -> None:
        uid = vals.get("uuid")
        if isinstance(uid, str) and uid:
            if uid in self.seen_user:
                self.cov["user_lines_duplicate"] += 1
                return
            self.seen_user.add(uid)
        has_result = '"tool_result"' in text
        if "<command-name>" in text:
            ver = _short_value(vals.get("version")) if vals.get("version") else "unknown"
            for name in RE_COMMAND.findall(text):
                inc(self.commands, name)
                self.ctx.add_command(name, sid, ver)
        if has_result:
            msg = parsed.get("message") if parsed else (decode_at(text, offs["message"]) if "message" in offs else None)
            self._tool_results(msg, sid, ts)
        else:
            if vals.get("isSidechain") is not True:
                ver = _short_value(vals.get("version")) if vals.get("version") else "unknown"
                self.auto.add_user(vals, ver)
            if not (vals.get("isMeta") is True or vals.get("isSidechain") is True
                    or vals.get("isCompactSummary") is True):
                self.session_turns[sid] = self.session_turns.get(sid, 0) + 1

    def _tool_results(self, msg: Any, sid: str, ts: float) -> None:
        if not isinstance(msg, dict) or not isinstance(msg.get("content"), list):
            return
        for block in msg["content"]:
            if not isinstance(block, dict) or block.get("type") != "tool_result":
                continue
            tid = block.get("tool_use_id") if isinstance(block.get("tool_use_id"), str) else ""
            if not tid:
                tid = "anon#%d" % len(self.tool_results)
            n = _content_chars(block.get("content"))
            prev = self.tool_results.get(tid)
            if prev is None or n > prev[0]:
                self.tool_results[tid] = (n, ts, sid)
