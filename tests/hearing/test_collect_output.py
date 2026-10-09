"""collect の出力の性質（本文を含めない・ラベル・上位セッションの参照）のテスト。"""

import json
import unittest

from helpers import ConfigDir, assistant, cost_state, tool_result, usage, user

SID = "22222222-aaaa-bbbb-cccc-000000000001"
TS = "2026-09-12T09:00:00.000Z"
SAMPLE_CWD = "/home/bodyuser/bodyproj"
BODY_MARKERS = [
    "BODYBODY", "AKIAFAKEBODY", "sk-body", "本文サンプル", "bodycmd", "BODYTHINK",
    "BODYRESULT", "BODYBROKEN", "BODYERR", "BODYTITLE", "BODYARN",
]


def body_rows():  # type: ignore[no-untyped-def]
    tools = [
        {"type": "tool_use", "id": "tc1", "name": "Bash",
         "input": {"command": "bodycmd --token sk-bodyABCDEFGHIJKLMNOP"}},
        {"type": "tool_use", "id": "tc2", "name": "Read", "input": {"file_path": SAMPLE_CWD + "/BODYBODY.secret"}},
    ]
    content = [{"type": "thinking", "thinking": "BODYTHINK"}, {"type": "text", "text": "BODYBODY 本文サンプル"}] + tools
    return [
        user(SID, TS, "BODYBODY 本文サンプル AKIAFAKEBODY1234567", cwd=SAMPLE_CWD, uuid="cu1"),
        user(SID, TS, "<command-name>/allowed-cmd</command-name><command-args>BODYBODY</command-args>",
             cwd=SAMPLE_CWD, uuid="cu2"),
        assistant("m1", SID, TS, content=content, cwd=SAMPLE_CWD,
                  model="arn:aws:bedrock:us-east-1:123456789012:application-inference-profile/BODYARN"),
        tool_result(SID, TS, "tc1", "BODYRESULT AKIAFAKEBODY1234567 " + SAMPLE_CWD),
        {"type": "ai-title", "sessionId": SID, "aiTitle": "BODYTITLE"},
        {"type": "last-prompt", "sessionId": SID, "lastPrompt": "BODYBODY"},
        '{"type":"assistant","message":{"content":"BODYBROKEN BODYERR \\ud800',
        '{"type":"user","message":{"content":"BODYBROKEN ' + SAMPLE_CWD,
        "\x00\x01BODYBROKEN",
        '[1, "BODYERR"]',
        '{"type":"assistant","message":"BODYERR","timestamp":5,"sessionId":["BODYERR"]}',
        cost_state(SID, {"arn:aws:bedrock:us-east-1:123456789012:foundation-model/anthropic.claude-haiku-4-5": {"input": 1}}),
    ]


class OutputShapeTest(unittest.TestCase):
    def setUp(self) -> None:
        self.cfg = ConfigDir()

    def tearDown(self) -> None:
        self.cfg.cleanup()

    def test_bodies_are_not_in_aggregate_json(self) -> None:
        self.cfg.write("-home-bodyuser-bodyproj/%s.jsonl" % SID, body_rows())
        self.cfg.write("-home-bodyuser-bodyproj/%s/subagents/agent-x.jsonl" % SID,
                       [assistant("m2", SID, TS, side=True, agent="x", cwd=SAMPLE_CWD)])
        (self.cfg.root / "settings.json").write_text(json.dumps({
            "model": "arn:aws:bedrock:us-east-1:123456789012:inference-profile/BODYARN",
            "env": {"SECRET": "BODYBODY"}, "mcpServers": {"bodycmd": {"token": "sk-bodyXXXXXXXXXXXX"}},
            "effortLevel": "BODYBODY with spaces"}))
        sk = self.cfg.root / "skills" / "s1"
        sk.mkdir(parents=True)
        (sk / "SKILL.md").write_text("---\nname: s1\ndescription: BODYBODY desc\n---\n", encoding="utf-8")
        for extra in ([], ["--local-tz"], ["--max-line-bytes", "300"]):
            rc, so, se, d, text = self.cfg.collect(*extra)
            self.assertEqual(rc, 0, se)
            blob = text + so + se
            for m in BODY_MARKERS:
                self.assertNotIn(m, blob, m)
            self.assertNotIn("123456789012", blob)
            self.assertNotIn(SAMPLE_CWD, blob)
            self.assertGreater(sum(d["coverage"]["lines_unreadable"].values()), 0)
        rc, so, se, d, text = self.cfg.collect(env={"PYTHONIOENCODING": "cp932"})
        self.assertEqual(rc, 0)
        for m in BODY_MARKERS:
            self.assertNotIn(m, text + so + se)

    def test_project_label_is_stable(self) -> None:
        self.cfg.write("-home-bodyuser-bodyproj/%s.jsonl" % SID, body_rows())
        _rc, _so, _se, d1, _t = self.cfg.collect()
        _rc, _so, _se, d2, _t = self.cfg.collect()
        labels = [p["label"] for p in d1["projects"]["top_by_output"]]
        self.assertEqual(labels, [p["label"] for p in d2["projects"]["top_by_output"]])
        self.assertRegex(labels[0], r"^P-[0-9a-f]{8}$")

    def test_top_sessions_carry_session_id_and_parent_file(self) -> None:
        self.cfg.write("-home-bodyuser-bodyproj/%s.jsonl" % SID,
                       [assistant("m1", SID, TS, cwd=SAMPLE_CWD, u=usage(out=10))])
        self.cfg.write("-home-bodyuser-bodyproj/%s/subagents/agent-x.jsonl" % SID,
                       [assistant("m%d" % i, SID, TS, side=True, agent="x", cwd=SAMPLE_CWD) for i in range(2, 5)])
        _rc, _so, _se, d, _t = self.cfg.collect()
        top = d["sessions"]["top_by_output"][0]
        self.assertEqual(top["session_id"], SID)
        self.assertEqual(top["file"], "projects/-home-bodyuser-bodyproj/%s.jsonl" % SID)
        self.assertRegex(top["session"], r"^S-[0-9a-f]{8}$")
        self.assertIn(top["session"], d["sessions"]["details"])
