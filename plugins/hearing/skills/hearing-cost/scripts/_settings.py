"""設定と導入済みスキルの読み取り。"""

from __future__ import annotations

import json
import os
import re
from typing import Any, Dict, List, Optional, Set, Tuple

from _base import AUTOCOMPACT_ENV, KNOWN_FAMILIES, MODEL_ALIASES, SETTINGS_SCALAR_KEYS, _short_value
from _common import skill_files
from _parse import classify_model


def _load_json_file(path: str) -> Any:
    try:
        with open(path, "r", encoding="utf-8-sig", errors="replace") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def read_settings(config_dir: str) -> Dict[str, Any]:
    data = _load_json_file(os.path.join(config_dir, "settings.json"))
    out: Dict[str, Any] = {"found": isinstance(data, dict), "cleanup_period_days": None, "model": None,
                           "effort_level": None, "always_thinking_enabled": None,
                           "mcp_servers_count": None, "auto_compact_pct_override": None,
                           "auto_compact_enabled": None}
    if not isinstance(data, dict):
        return out
    cpd = data.get("cleanupPeriodDays")
    if isinstance(cpd, (int, float)) and not isinstance(cpd, bool):
        out["cleanup_period_days"] = int(cpd)
    model = data.get("model")
    if isinstance(model, str):
        alias = model.strip().lower().replace("[1m]", "")
        if alias in MODEL_ALIASES:
            bucket = alias if alias in KNOWN_FAMILIES else "unknown"
            out["model"] = {"alias": alias, "bucket": bucket, "generation": None}
        else:
            cls = classify_model(model)
            out["model"] = {"alias": None, "bucket": cls["bucket"], "generation": cls["generation"]}
    for key, name in SETTINGS_SCALAR_KEYS.items():
        v = data.get(key)
        if isinstance(v, bool):
            out[name] = v
        elif v is not None:
            out[name] = _short_value(v)
    env = data.get("env")
    pct = env.get(AUTOCOMPACT_ENV) if isinstance(env, dict) else None
    if isinstance(pct, (int, float, str)) and not isinstance(pct, bool) and re.fullmatch(r"\d{1,3}", str(pct).strip()):
        out["auto_compact_pct_override"] = int(str(pct).strip())
    if isinstance(data.get("autoCompactEnabled"), bool):
        out["auto_compact_enabled"] = data["autoCompactEnabled"]
    mcp = data.get("mcpServers")
    if isinstance(mcp, dict):
        out["mcp_servers_count"] = len(mcp)
    return out


def _description_chars(text: str) -> int:
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return 0
    body: List[str] = []
    for ln in lines[1:]:
        if ln.strip() == "---":
            break
        body.append(ln)
    for i, ln in enumerate(body):
        if not ln.startswith("description:"):
            continue
        val = ln[len("description:"):].strip()
        if val in ("", "|", ">", "|-", ">-"):
            parts = []
            for nxt in body[i + 1:]:
                if nxt.strip() and not nxt.startswith((" ", "\t")):
                    break
                parts.append(nxt.strip())
            val = " ".join(p for p in parts if p)
        return len(val.strip("\"'"))
    return 0


def _frontmatter_name(text: str) -> Optional[str]:
    m = re.search(r"^name:\s*[\"']?([A-Za-z0-9_:.\-]{1,100})", text, re.M)
    return m.group(1) if m else None


def _skill_stats(paths: List[str]) -> Dict[str, Any]:
    sizes: List[int] = []
    descs: List[int] = []
    for p in paths:
        try:
            sizes.append(os.path.getsize(p))
            with open(p, "r", encoding="utf-8", errors="replace") as f:
                descs.append(_description_chars(f.read(65536)))
        except OSError:
            continue
    return {"count": len(sizes), "skill_md_bytes_total": sum(sizes), "skill_md_bytes_max": max(sizes or [0]),
            "description_chars_total": sum(descs), "description_chars_max": max(descs or [0])}


def installed_skills(config_dir: str) -> Tuple[Dict[str, Any], Set[str]]:
    personal_root = os.path.join(config_dir, "skills")
    personal = skill_files(personal_root, False)
    names: Set[str] = set()
    for p in personal:
        names.add(os.path.basename(os.path.dirname(p)))
        try:
            with open(p, "r", encoding="utf-8", errors="replace") as f:
                n = _frontmatter_name(f.read(65536))
            if n:
                names.add(n)
        except OSError:
            continue
    plugin = skill_files(os.path.join(config_dir, "plugins"), True)
    info = {"personal": _skill_stats(personal), "plugin": _skill_stats(plugin),
            "note": "plugin counts may include cached copies; project skills are not read"}
    return info, names


def classify_skill(name: str, personal: Set[str]) -> str:
    if ":" in name:
        return "plugin"
    if name in personal:
        return "personal"
    return "builtin_or_unknown"
