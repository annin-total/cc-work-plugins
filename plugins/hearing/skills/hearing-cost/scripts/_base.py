"""collect が使う定数と汎用の小物。"""

from __future__ import annotations

import hashlib
import os
import re
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional, Tuple

from _common import inc

SCHEMA_VERSION = "1.0"
SESSION_GAP_SECONDS = 30 * 60
TOP_N = 5
DEFAULT_CLEANUP_DAYS = 30
RETENTION_NEAR_DAYS = 2
TOKEN_TYPES = ("input", "output", "cache_creation", "cache_read")
TOKEN_SUBTYPES = ("cache_creation_5m", "cache_creation_1h")
ALL_TOKEN_KEYS = TOKEN_TYPES + TOKEN_SUBTYPES
USAGE_FIELDS = {
    "input": "input_tokens",
    "output": "output_tokens",
    "cache_creation": "cache_creation_input_tokens",
    "cache_read": "cache_read_input_tokens",
}
CACHE_SUBFIELDS = {
    "cache_creation_5m": "ephemeral_5m_input_tokens",
    "cache_creation_1h": "ephemeral_1h_input_tokens",
}
MODEL_USAGE_FIELDS = {
    "input": "inputTokens",
    "output": "outputTokens",
    "cache_creation": "cacheCreationInputTokens",
    "cache_read": "cacheReadInputTokens",
}
FILE_TOOL_KEYS = ("file_path", "notebook_path")
RESULT_BUCKETS = ((1_000, "lt_1k"), (10_000, "1k_10k"), (50_000, "10k_50k"), (200_000, "50k_200k"))
RESULT_BUCKET_MAX = "ge_200k"
LENGTH_BUCKETS = ((10, "lt_10m"), (30, "10m_30m"), (60, "30m_1h"), (180, "1h_3h"), (480, "3h_8h"))
LENGTH_BUCKET_MAX = "ge_8h"
SETTINGS_SCALAR_KEYS = {"effortLevel": "effort_level", "alwaysThinkingEnabled": "always_thinking_enabled"}
AUTOCOMPACT_ENV = "CLAUDE_AUTOCOMPACT_PCT_OVERRIDE"
MODEL_ALIASES = ("default", "best", "opus", "sonnet", "haiku", "fable", "opusplan")
KNOWN_FAMILIES = ("opus", "sonnet", "haiku", "fable")
TOP_LINE_TYPES = {
    "user", "assistant", "system", "attachment", "summary", "cost-state", "queue-operation",
    "last-prompt", "ai-title", "atis-latch", "mode", "file-history-snapshot", "progress",
    "custom-title", "tag", "agent-name", "pr-link",
}
TOP_FIELDS = (
    "type", "timestamp", "sessionId", "agentId", "uuid", "cwd", "version",
    "isSidechain", "isMeta", "isCompactSummary", "message", "modelUsage", "subtype", "compactMetadata",
    "entrypoint", "turnOrigin", "promptSource",
)

EPOCH0 = datetime(1970, 1, 1, tzinfo=timezone.utc)
MIN_TS = datetime(2020, 1, 1, tzinfo=timezone.utc).timestamp()
TS_FUTURE_MARGIN_SECONDS = 86400
RE_NAME = re.compile(r"^[A-Za-z0-9_:.@\-]{1,100}$")
RE_SHORT_VALUE = re.compile(r"^[A-Za-z0-9_.\-]{1,24}$")
RE_EXT = re.compile(r"^\.[a-z0-9]{1,10}$")
RE_TS = re.compile(
    r"^(\d{4})-(\d{2})-(\d{2})(?:[T ](\d{2}):(\d{2})(?::(\d{2})(?:\.(\d{1,9}))?)?)?\s*(Z|[+-]\d{2}:?\d{2})?$"
)
RE_ASSISTANT = re.compile(r'"type"\s*:\s*"assistant"')
RE_TOKEN = re.compile(r'"([^"\\]*(?:\\.[^"\\]*)*)"(\s*:)?|[{}\[\]]')
RE_COMMAND = re.compile(r"<command-name>\s*/?([A-Za-z0-9_:.@\-]{1,100})\s*</command-name>")
RE_FAMILY = re.compile(r"(?<![a-z])(opus|sonnet|haiku|fable)(?![a-z])")
RE_NEW_FAMILY = re.compile(r"claude-([a-z]{2,20})-\d")
RE_ARN_MODEL = re.compile(r"(?<![a-z\-])(?:foundation-model|inference-profile)/([^/\s\"]+)")
RE_GEN_AFTER = r"{fam}-(\d{{1,2}})(?:-(\d{{1,2}}))?(?!\d)"
RE_GEN_BEFORE = r"claude-(\d{{1,2}})(?:[-.](\d{{1,2}}))?-{fam}"


def parent_session_file(config_dir: str, path: str) -> str:
    """設定ディレクトリからの相対パス。サブエージェント等のファイルは親セッションの jsonl に読み替える。"""
    parts = os.path.relpath(path, config_dir).split(os.sep)
    if len(parts) > 3:  # projects/<proj>/<sessionId>/subagents/... -> projects/<proj>/<sessionId>.jsonl
        parts = parts[:2] + [parts[2] + ".jsonl"]
    return "/".join(parts)


def _int(v: Any) -> int:
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        return 0
    return max(int(v), 0)


def _label(prefix: str, raw: str) -> str:
    return prefix + "-" + hashlib.sha256(raw.encode("utf-8", "replace")).hexdigest()[:8]


def _safe_name(v: Any) -> Optional[str]:
    if isinstance(v, str) and RE_NAME.match(v):
        return v
    return None


def _short_value(v: Any) -> str:
    if isinstance(v, str) and RE_SHORT_VALUE.match(v):
        return v
    return "other"


def _zero_tokens() -> Dict[str, int]:
    return {k: 0 for k in ALL_TOKEN_KEYS}


def _zero_type_tokens() -> Dict[str, int]:
    return {k: 0 for k in TOKEN_TYPES}


def _add_tokens(dst: Dict[str, int], src: Dict[str, int]) -> None:
    for k in ALL_TOKEN_KEYS:
        dst[k] = dst.get(k, 0) + src.get(k, 0)


def _content_chars(content: Any) -> int:
    if isinstance(content, str):
        return len(content)
    if isinstance(content, list):
        total = 0
        for item in content:
            if isinstance(item, dict) and isinstance(item.get("text"), str):
                total += len(item["text"])
        return total
    return 0


def _extension(path: str) -> str:
    base = re.split(r"[\\/]", path)[-1]
    ext = os.path.splitext(base)[1].lower()
    if not ext:
        return "(none)"
    return ext if RE_EXT.match(ext) else "(other)"


def _bucket(n: float, buckets: Tuple[Tuple[int, str], ...], top: str) -> str:
    for limit, name in buckets:
        if n < limit:
            return name
    return top


def _percentile(values: List[float], q: float) -> float:
    if not values:
        return 0.0
    s = sorted(values)
    return s[min(int(round(q * (len(s) - 1))), len(s) - 1)]


def _new_role() -> Dict[str, Any]:
    return {"api_calls": 0, "output_unfinalized_calls": 0, "tokens": _zero_tokens()}


def _new_session() -> Dict[str, Any]:
    return {"api_calls": 0, "sidechain_calls": 0, "tokens": _zero_tokens(), "models": {}, "cwds": {},
            "effort": {}, "tools": {}, "exts": {}, "ts": [], "minutes": 0.0, "segments": 0}


def _tri() -> Dict[str, Any]:
    return {"observed_n": 0, "absent_n": 0, "values": {}}


def _tri_add(t: Dict[str, Any], v: Optional[str]) -> None:
    if v is None:
        t["absent_n"] += 1
    else:
        t["observed_n"] += 1
        inc(t["values"], v)


def _ranked(d: Dict[str, Any], value: Callable[[Any], Any]) -> List[Tuple[str, Any]]:
    """値の降順・キーの昇順に並べた (キー, 値) の列。"""
    return sorted(d.items(), key=lambda kv: (-value(kv[1]), kv[0]))


def _sorted_counts(d: Dict[str, int]) -> Dict[str, int]:
    return dict(sorted(d.items(), key=lambda kv: (-kv[1], kv[0])))
