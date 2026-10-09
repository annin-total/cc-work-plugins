"""テスト用の合成 jsonl と collect.py 実行の補助。"""

import importlib.util
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

sys.dont_write_bytecode = True
SCRIPT_DIR = Path(__file__).resolve().parents[2] / "plugins" / "hearing" / "skills" / "hearing-cost" / "scripts"
SCRIPT = SCRIPT_DIR / "collect.py"
START = "2026-09-01T00:00:00Z"
END = "2026-10-01T00:00:00Z"
CWD = "/home/someone/project-x"
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))


def load_module() -> Any:
    spec = importlib.util.spec_from_file_location("hearing_collect", str(SCRIPT))
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


def usage(inp: int = 10, out: int = 100, cc: int = 1000, cr: int = 5000, c5: int = 0, c1: int = 0) -> Dict[str, Any]:
    return {"input_tokens": inp, "output_tokens": out, "cache_creation_input_tokens": cc,
            "cache_read_input_tokens": cr,
            "cache_creation": {"ephemeral_5m_input_tokens": c5, "ephemeral_1h_input_tokens": c1},
            "iterations": [{"input_tokens": 999999}]}


def assistant(mid: Optional[str], sid: str, ts: Optional[str], *, rid: Optional[str] = None,
              model: str = "claude-opus-5-5", u: Any = "default", uuid: Optional[str] = None,
              version: str = "2.1.286", effort: Optional[str] = None, pte: Optional[str] = None,
              side: bool = False, agent: Optional[str] = None, content: Optional[List[Any]] = None,
              cwd: str = CWD, attr: Optional[str] = None, stop: Optional[str] = None) -> Dict[str, Any]:
    msg: Dict[str, Any] = {"model": model, "type": "message", "role": "assistant",
                           "content": content if content is not None else [{"type": "text", "text": "hello"}]}
    if mid is not None:
        msg["id"] = mid
    if stop is not None:
        msg["stop_reason"] = stop
    if u == "default":
        msg["usage"] = usage()
    elif u is not None:
        msg["usage"] = u
    d: Dict[str, Any] = {"parentUuid": None, "isSidechain": side, "cwd": cwd, "sessionId": sid,
                         "version": version, "message": msg, "type": "assistant",
                         "uuid": uuid or ("u-" + str(mid) + "-" + str(ts))}
    if ts is not None:
        d["timestamp"] = ts
    if rid is not None:
        d["requestId"] = rid
    if effort is not None:
        d["effort"] = effort
    if pte is not None:
        d["perTurnEffort"] = pte
    if agent is not None:
        d["agentId"] = agent
    if attr is not None:
        d["attributionSkill"] = attr
    return d


def user(sid: str, ts: str, text: Any = "do the thing", *, uuid: Optional[str] = None,
         side: bool = False, cwd: str = CWD) -> Dict[str, Any]:
    return {"parentUuid": None, "isSidechain": side, "type": "user", "cwd": cwd, "sessionId": sid,
            "message": {"role": "user", "content": text}, "uuid": uuid or ("uu-" + ts + str(len(str(text)))),
            "timestamp": ts, "version": "2.1.286"}


def tool_result(sid: str, ts: str, tool_id: str, body: str) -> Dict[str, Any]:
    return user(sid, ts, [{"tool_use_id": tool_id, "type": "tool_result", "content": body}], uuid="tr-" + tool_id)


def cost_state(sid: str, model_usage: Dict[str, Dict[str, int]]) -> Dict[str, Any]:
    mu = {}
    for m, v in model_usage.items():
        mu[m] = {"inputTokens": v.get("input", 0), "outputTokens": v.get("output", 0),
                 "cacheReadInputTokens": v.get("cache_read", 0),
                 "cacheCreationInputTokens": v.get("cache_creation", 0), "costUSD": 12.34}
    return {"type": "cost-state", "sessionId": sid, "totalCostUSD": 98.76, "modelUsage": mu}


class ConfigDir:
    """一時の設定ディレクトリ。"""

    def __init__(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name) / "cfg"
        self.projects = self.root / "projects"
        self.projects.mkdir(parents=True)
        self.work = Path(self._tmp.name) / "work"
        self.work.mkdir()

    def cleanup(self) -> None:
        self._tmp.cleanup()

    def write(self, rel: str, rows: List[Any], raw_suffix: str = "\n", encoding_bom: bool = False) -> Path:
        p = self.projects / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        parts = []
        for r in rows:
            parts.append(r if isinstance(r, str) else json.dumps(r, ensure_ascii=False, separators=(",", ":")))
        data = raw_suffix.join(parts) + raw_suffix
        raw = data.encode("utf-8")
        if encoding_bom:
            raw = b"\xef\xbb\xbf" + raw
        p.write_bytes(raw)
        return p

    def collect(self, *extra: str, env: Optional[Dict[str, str]] = None,
                start: str = START, end: str = END) -> Tuple[int, str, str, Optional[Dict[str, Any]], str]:
        out = self.work / "agg.json"
        if out.exists():
            out.unlink()
        args = ["collect", "--config-dir", str(self.root), "--start", start, "--end", end, "--out", str(out)]
        rc, so, se = run(args + list(extra), env)
        text = out.read_text(encoding="utf-8") if out.exists() else ""
        return rc, so, se, (json.loads(text) if text else None), text


def run(args: List[str], env: Optional[Dict[str, str]] = None) -> Tuple[int, str, str]:
    e = dict(os.environ)
    if env:
        e.update(env)
    p = subprocess.run([sys.executable, str(SCRIPT)] + args, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=e)
    return p.returncode, p.stdout.decode("utf-8", "replace"), p.stderr.decode("utf-8", "replace")
