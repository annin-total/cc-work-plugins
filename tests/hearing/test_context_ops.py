"""context_ops（compact・clear・resume・model の回数）のテスト。"""

import json
import unittest
from typing import Any, Dict, Optional

from helpers import ConfigDir, assistant, user

SID = "33333333-aaaa-bbbb-cccc-000000000001"
SID2 = "33333333-aaaa-bbbb-cccc-000000000002"
TS = "2026-09-12T09:00:00.000Z"


def boundary(sid: str, ts: str, trigger: Any, pre: Optional[int] = 100000, *, uuid: str, version: str = "2.1.286") -> Dict[str, Any]:
    meta: Dict[str, Any] = {"trigger": trigger, "postTokens": 5000}
    if pre is not None:
        meta["preTokens"] = pre
    return {"type": "system", "subtype": "compact_boundary", "sessionId": sid, "timestamp": ts, "uuid": uuid,
            "version": version, "content": "BODYBODY", "compactMetadata": meta}


def command(sid: str, ts: str, name: str, uuid: str) -> Dict[str, Any]:
    return user(sid, ts, "<command-name>/%s</command-name><command-args></command-args>" % name, uuid=uuid)


class ContextOpsTest(unittest.TestCase):
    def setUp(self) -> None:
        self.cfg = ConfigDir()

    def tearDown(self) -> None:
        self.cfg.cleanup()

    def ops(self, rows: Any, rows2: Any = None, **kw: Any) -> Dict[str, Any]:
        self.cfg.write("-p/%s.jsonl" % SID, rows)
        if rows2 is not None:
            self.cfg.write("-p/%s.jsonl" % SID2, rows2)
        rc, _so, _se, data, _t = self.cfg.collect(**kw)
        self.assertEqual(rc, 0)
        assert data is not None
        return data["context_ops"]

    def test_compact_clear_resume_model_counts(self) -> None:
        c = self.ops([
            assistant("m1", SID, TS, model="claude-opus-5-5"),
            boundary(SID, "2026-09-12T09:10:00.000Z", "manual", uuid="b1"),
            boundary(SID, "2026-09-12T09:20:00.000Z", "auto", 800000, uuid="b2"),
            boundary(SID, "2026-09-12T09:30:00.000Z", "auto", 600000, uuid="b3"),
            command(SID, "2026-09-12T09:40:00.000Z", "clear", "c1"),
            command(SID, "2026-09-12T09:41:00.000Z", "resume", "c2"),
            command(SID, "2026-09-12T09:42:00.000Z", "model", "c3"),
            assistant("m2", SID, "2026-09-12T09:43:00.000Z", model="claude-sonnet-4-5"),
            assistant("m3", SID, "2026-09-12T09:44:00.000Z", model="claude-sonnet-4-5"),
            assistant("m4", SID, "2026-09-12T09:45:00.000Z", model="claude-opus-5-5", side=True, agent="a"),
        ])
        ops = c["ops"]
        self.assertEqual({k: v["total"] for k, v in ops.items()},
                         {"compact_manual": 1, "compact_auto": 2, "clear": 1, "resume_command": 1,
                          "model_command": 1, "model_change": 1})
        self.assertEqual(ops["compact_auto"]["sessions"], 1)
        self.assertEqual(ops["compact_auto"]["per_session"], 2.0)
        self.assertEqual(c["auto_compact_pre_tokens"], {"observed_n": 2, "median": 700000.0, "max": 800000})
        self.assertEqual(c["longest_sessions"][0]["ops"]["compact_auto"], 2)
        self.assertEqual(c["by_version"]["2.1.286"]["compact_manual"], 1)
        self.assertNotIn("BODYBODY", json.dumps(c))

    def test_no_record_version_shows_zero_with_sessions(self) -> None:
        c = self.ops([assistant("m1", SID, TS, version="2.0.1")],
                     [assistant("m2", SID2, TS, version="2.1.286"),
                      boundary(SID2, TS, "auto", uuid="b1")])
        self.assertEqual(c["by_version"]["2.0.1"], {"sessions": 1, "compact_manual": 0, "compact_auto": 0,
                                                    "clear": 0, "resume_command": 0, "model_command": 0,
                                                    "model_change": 0})
        self.assertEqual(c["by_version"]["2.1.286"]["compact_auto"], 1)

    def test_out_of_period_excluded(self) -> None:
        c = self.ops([
            assistant("m1", SID, TS),
            boundary(SID, "2026-08-01T00:00:00.000Z", "auto", uuid="b1"),
            command(SID, "2026-10-05T00:00:00.000Z", "clear", "c1"),
        ])
        self.assertTrue(all(v["total"] == 0 for v in c["ops"].values()))
        self.assertEqual(c["auto_compact_pre_tokens"]["observed_n"], 0)
        self.assertIsNone(c["auto_compact_pre_tokens"]["median"])

    def test_duplicate_lines_counted_once(self) -> None:
        b = boundary(SID, TS, "auto", uuid="same")
        k = command(SID, TS, "clear", "same-cmd")
        c = self.ops([assistant("m1", SID, TS), b, b, k, k], [dict(b, sessionId=SID2), dict(k, sessionId=SID2)])
        self.assertEqual(c["ops"]["compact_auto"]["total"], 1)
        self.assertEqual(c["ops"]["clear"]["total"], 1)
        self.assertEqual(c["auto_compact_pre_tokens"]["observed_n"], 1)

    def test_unknown_trigger_ignored(self) -> None:
        c = self.ops([assistant("m1", SID, TS), boundary(SID, TS, "weird", uuid="b1"),
                      boundary(SID, TS, None, uuid="b2")])
        self.assertEqual(c["ops"]["compact_manual"]["total"] + c["ops"]["compact_auto"]["total"], 0)

    def test_settings_auto_compact(self) -> None:
        self.cfg.write("-p/%s.jsonl" % SID, [assistant("m1", SID, TS)])
        (self.cfg.root / "settings.json").write_text(json.dumps(
            {"env": {"CLAUDE_AUTOCOMPACT_PCT_OVERRIDE": "60"}, "autoCompactEnabled": False}))
        _rc, _so, _se, data, _t = self.cfg.collect()
        assert data is not None
        self.assertEqual(data["settings"]["auto_compact_pct_override"], 60)
        self.assertIs(data["settings"]["auto_compact_enabled"], False)
        (self.cfg.root / "settings.json").write_text(json.dumps({"env": {"CLAUDE_AUTOCOMPACT_PCT_OVERRIDE": "x; rm"}}))
        _rc, _so, _se, data, _t = self.cfg.collect()
        assert data is not None
        self.assertIsNone(data["settings"]["auto_compact_pct_override"])
        self.assertIsNone(data["settings"]["auto_compact_enabled"])


if __name__ == "__main__":
    unittest.main()
