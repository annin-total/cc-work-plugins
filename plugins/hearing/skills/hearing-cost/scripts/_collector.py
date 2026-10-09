"""履歴の走査と行の振り分け。"""

from __future__ import annotations

import json
import os
from typing import Any, Dict, List, Optional, Set, Tuple

from _base import (
    MIN_TS, MODEL_USAGE_FIELDS, RE_ASSISTANT, TOP_FIELDS, TS_FUTURE_MARGIN_SECONDS, _int, _zero_type_tokens,
    parent_session_file,
)
from _automation import Automation
from _common import inc, iter_lines
from _context_ops import ContextOps
from _parse import classify_model, parse_ts, top_fields
from _records import RecordMixin


class Collector(RecordMixin):
    """projects/ 配下の jsonl を読み、集計 JSON を作る。"""

    def __init__(self, config_dir: str, start: float, end: float, exclude: Optional[str],
                 max_bytes: int, local_tz: bool, now: float) -> None:
        self.config_dir = config_dir
        self.start = start
        self.end = end
        self.exclude = exclude
        self.max_bytes = max_bytes
        self.local_tz = local_tz
        self.max_ts = now + TS_FUTURE_MARGIN_SECONDS
        self.cov: Dict[str, Any] = {
            "files_total": 0, "files_processed": 0, "files_unreadable": 0,
            "files_orphaned": 0, "files_superseded": 0, "lines_total": 0, "lines_processed": 0,
            "lines_unreadable": {}, "lines_oversize_skipped": 0, "lines_invalid_utf8": 0,
            "assistant_lines": 0, "records_before_dedup": 0, "records_after_dedup": 0,
            "dedup_fallback_uuid": 0, "dedup_no_key": 0, "synthetic_lines": 0,
            "usage_missing_lines": 0, "records_out_of_period": 0, "records_timestamp_missing": 0,
            "records_timestamp_out_of_range": 0, "projects_dir_found": False, "walk_errors": 0,
            "excluded_session_lines": 0, "excluded_session_records": 0, "user_lines_duplicate": 0,
        }
        self.line_types: Dict[str, int] = {}
        self.versions: Dict[str, int] = {}
        self.records: Dict[str, Dict[str, Any]] = {}
        self.excluded_keys: Set[str] = set()
        self.tool_uses: Dict[str, Tuple[str, str, Optional[str], Optional[str]]] = {}
        self.tool_results: Dict[str, Tuple[int, float, str]] = {}
        self.seen_user: Set[str] = set()
        self.commands: Dict[str, int] = {}
        self.ctx = ContextOps()
        self.auto = Automation()
        self.session_ts: Dict[str, List[float]] = {}
        self.session_agents: Dict[str, Set[str]] = {}
        self.session_turns: Dict[str, int] = {}
        self.session_files: Dict[str, Dict[str, int]] = {}
        self.cur_file = ""
        self.cost_state: Dict[str, Dict[str, Dict[str, int]]] = {}
        self.attribution: Dict[str, Set[str]] = {}
        self.attribution_lines: Dict[str, int] = {}
        self.oldest: Optional[float] = None
        self.newest: Optional[float] = None
        self.files_with_lines = 0
        self.tool_results_dir = {"files": 0, "bytes": 0}

    # ---- 走査

    def run(self) -> None:
        root = os.path.join(self.config_dir, "projects")
        self.cov["projects_dir_found"] = os.path.isdir(root)
        paths = self._walk(root) if self.cov["projects_dir_found"] else []
        for i, p in enumerate(paths):
            self.cov["files_total"] += 1
            name = os.path.basename(p)
            if ".orphaned" in name:
                self.cov["files_orphaned"] += 1
                continue
            if ".superseded" in name:
                self.cov["files_superseded"] += 1
                continue
            if not name.endswith(".jsonl"):
                inc(self.line_types, "_unknown_file")
                continue
            self._read_file(p, i)

    def _walk(self, root: str) -> List[str]:
        """projects/ を 1 回だけ歩き、jsonl 系のパスを返しつつ tool-results/ 以下の件数とバイトも数える。"""
        paths: List[str] = []

        def on_error(_e: OSError) -> None:
            self.cov["walk_errors"] += 1

        for dirpath, dirs, files in os.walk(root, onerror=on_error):
            dirs.sort()
            in_results = "tool-results" in os.path.relpath(dirpath, root).split(os.sep)
            for name in sorted(files):
                if ".jsonl" in name:
                    paths.append(os.path.join(dirpath, name))
                if in_results:
                    try:
                        self.tool_results_dir["bytes"] += os.path.getsize(os.path.join(dirpath, name))
                        self.tool_results_dir["files"] += 1
                    except OSError:
                        continue
        return paths

    def _broken(self, kind: str) -> None:
        inc(self.cov["lines_unreadable"], kind)

    def _read_file(self, path: str, fidx: int) -> None:
        had = False
        self.cur_file = parent_session_file(self.config_dir, path)
        try:
            for lineno, body in iter_lines(path, self.max_bytes):
                self.cov["lines_total"] += 1
                had = True
                if body is None:
                    self.cov["lines_oversize_skipped"] += 1
                    continue
                if not body.strip():
                    self._broken("empty")
                    continue
                text = body.decode("utf-8", errors="replace")
                if "\ufffd" in text and b"\xef\xbf\xbd" not in body:
                    self.cov["lines_invalid_utf8"] += 1
                try:
                    ok = self._line(text, fidx, lineno)
                except Exception as e:  # noqa: BLE001 - 例外メッセージは出さず種類だけ数える
                    self._broken("error_" + type(e).__name__)
                    continue
                if ok:
                    self.cov["lines_processed"] += 1
        except OSError:
            self.cov["files_unreadable"] += 1
            return
        self.cov["files_processed"] += 1
        if had:
            self.files_with_lines += 1

    def _ts(self, raw: Any) -> Optional[float]:
        """timestamp を epoch 秒に。読めない・範囲外（2020 年より前、現在の翌日より後）は None。"""
        ts = parse_ts(raw)
        if ts is not None and not MIN_TS <= ts <= self.max_ts:
            self.cov["records_timestamp_out_of_range"] += 1
            return None
        return ts

    def _seen_ts(self, ts: Optional[float]) -> None:
        if ts is None:
            return
        if self.oldest is None or ts < self.oldest:
            self.oldest = ts
        if self.newest is None or ts > self.newest:
            self.newest = ts

    def _in_period(self, ts: Optional[float]) -> bool:
        return ts is not None and self.start <= ts < self.end

    def _line(self, text: str, fidx: int, lineno: int) -> bool:
        # assistant 行だけ全体を json.loads する。残りは数 GB の履歴や巨大行でも遅くならないよう、
        # 深さ 1 のキーだけを正規表現で抜く（全行 json.loads はしない）。
        if RE_ASSISTANT.search(text):
            try:
                d = json.loads(text)
            except ValueError:
                self._broken("json_decode")
                return False
            if not isinstance(d, dict):
                self._broken("not_object")
                return False
            if d.get("type") == "assistant":
                inc(self.line_types, "assistant")
                self._assistant(d, fidx, lineno)
                return True
            vals = {k: d.get(k) for k in TOP_FIELDS if k in d and not isinstance(d.get(k), (dict, list))}
            return self._other(vals, {}, text, d)
        stripped = text.strip()
        if not stripped.startswith("{"):
            self._broken("not_object")
            return False
        if not stripped.endswith("}"):
            self._broken("truncated")
            return False
        vals, offs = top_fields(text)
        return self._other(vals, offs, text, None)

    def _cost_state(self, sid: str, mu: Any) -> None:
        if not sid or not isinstance(mu, dict):
            return
        snap: Dict[str, Dict[str, int]] = {}
        for model, vals in mu.items():
            if not isinstance(vals, dict):
                continue
            bucket = classify_model(model)["bucket"] or "unknown"
            t = snap.setdefault(bucket, _zero_type_tokens())
            for k, f in MODEL_USAGE_FIELDS.items():
                t[k] += _int(vals.get(f))
        prev = self.cost_state.get(sid)
        if prev is None or _snap_total(snap) >= _snap_total(prev):
            self.cost_state[sid] = snap


def _snap_total(snap: Dict[str, Dict[str, int]]) -> int:
    return sum(sum(v.values()) for v in snap.values())
