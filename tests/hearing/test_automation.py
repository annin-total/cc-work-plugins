"""automation（起動のしかた・ターンの出どころ・定期実行系の呼び出し）のテスト。"""

import unittest
from typing import Any, Dict, Optional

from helpers import ConfigDir, assistant, user

SID = "44444444-aaaa-bbbb-cccc-000000000001"
SID2 = "44444444-aaaa-bbbb-cccc-000000000002"
SID3 = "44444444-aaaa-bbbb-cccc-000000000003"
TS = "2026-09-12T09:00:00.000Z"


def with_fields(row: Dict[str, Any], **fields: Optional[str]) -> Dict[str, Any]:
    return {**row, **{k: v for k, v in fields.items() if v is not None}}


def tool_call(name: str) -> Dict[str, Any]:
    return {"type": "tool_use", "id": "t-" + name, "name": name, "input": {}}


class AutomationTest(unittest.TestCase):
    def setUp(self) -> None:
        self.cfg = ConfigDir()

    def tearDown(self) -> None:
        self.cfg.cleanup()

    def auto(self, files: Dict[str, Any], **kw: Any) -> Dict[str, Any]:
        for sid, rows in files.items():
            self.cfg.write("-p/%s.jsonl" % sid, rows)
        rc, _so, _se, data, _t = self.cfg.collect(**kw)
        self.assertEqual(rc, 0)
        assert data is not None
        return data["automation"]

    def test_entrypoint_split_by_session(self) -> None:
        a = self.auto({
            SID: [with_fields(assistant("m1", SID, TS), entrypoint="cli"),
                  with_fields(assistant("m2", SID, "2026-09-12T09:01:00.000Z"), entrypoint="cli")],
            SID2: [with_fields(assistant("m3", SID2, TS), entrypoint="sdk-cli")],
            SID3: [assistant("m4", SID3, TS)],
        })["entrypoint"]
        by = a["by_entrypoint"]
        self.assertEqual({k: v["sessions"] for k, v in by.items()}, {"cli": 1, "sdk-cli": 1, "not_recorded": 1})
        self.assertEqual(by["cli"]["api_calls"], 2)
        self.assertEqual(by["cli"]["tokens"]["output"], 200)
        self.assertEqual(by["cli"]["tokens"]["cache_read"], 10000)
        self.assertEqual(a["mixed_sessions"], 0)

    def test_entrypoint_first_seen_and_mixed(self) -> None:
        a = self.auto({SID: [
            with_fields(assistant("m2", SID, "2026-09-12T09:05:00.000Z"), entrypoint="sdk-py"),
            with_fields(user(SID, TS, uuid="u1"), entrypoint="cli"),
        ]})["entrypoint"]
        self.assertEqual(list(a["by_entrypoint"]), ["cli"])
        self.assertEqual(a["mixed_sessions"], 1)

    def test_turn_origin_absent_in_old_version(self) -> None:
        a = self.auto({SID: [
            with_fields(user(SID, TS, uuid="u1"), turnOrigin="human", promptSource="typed"),
            with_fields(user(SID, "2026-09-12T09:01:00.000Z", uuid="u2"), turnOrigin="sdk", promptSource="sdk"),
            with_fields(user(SID, "2026-09-12T09:02:00.000Z", uuid="u3"), version="2.1.219"),
            user(SID, "2026-09-12T09:03:00.000Z", uuid="u4", side=True),
        ]})["turn_origin"]
        self.assertEqual(a["turn_origin"], {"observed_n": 2, "absent_n": 1, "values": {"human": 1, "sdk": 1}})
        self.assertEqual(a["prompt_source"]["values"], {"sdk": 1, "typed": 1})
        self.assertEqual(a["by_version"]["2.1.286"]["turn_origin_observed"], 2)

    def test_schedule_tools_and_commands(self) -> None:
        calls = [assistant("m1", SID, TS, content=[tool_call("ScheduleWakeup")]),
                 assistant("m2", SID, "2026-09-12T09:01:00.000Z", content=[tool_call("ScheduleWakeup")])]
        for i, row in enumerate(calls):
            row["message"]["content"][0]["id"] = "t%d" % i
        cmd = user(SID2, TS, "<command-name>/loop</command-name><command-args></command-args>", uuid="c1")
        a = self.auto({SID: calls, SID2: [cmd, assistant("m3", SID2, TS)]})["schedule"]
        self.assertEqual(a["tools"]["ScheduleWakeup"], {"calls": 2, "sessions": 1})
        self.assertEqual(a["tools"]["CronCreate"], {"calls": 0, "sessions": 0})
        self.assertEqual(a["commands"], {"loop": 1, "schedule": 0})

    def test_duplicate_lines_counted_once(self) -> None:
        row = with_fields(user(SID, TS, uuid="dup"), turnOrigin="human", promptSource="typed")
        a = self.auto({SID: [row, row, assistant("m1", SID, TS, content=[tool_call("CronCreate")]),
                             assistant("m1", SID, TS, content=[tool_call("CronCreate")])]})
        self.assertEqual(a["turn_origin"]["turn_origin"]["observed_n"], 1)
        self.assertEqual(a["schedule"]["tools"]["CronCreate"]["calls"], 1)

    def test_out_of_period_excluded(self) -> None:
        old = "2026-08-01T09:00:00.000Z"
        a = self.auto({SID: [
            with_fields(assistant("m1", SID, old, content=[tool_call("ScheduleWakeup")]), entrypoint="sdk-cli"),
            with_fields(user(SID, old, uuid="u1"), turnOrigin="human"),
        ]})
        self.assertEqual(a["entrypoint"]["by_entrypoint"], {})
        self.assertEqual(a["turn_origin"]["turn_origin"]["observed_n"], 0)
        self.assertEqual(a["schedule"]["tools"]["ScheduleWakeup"]["calls"], 0)


if __name__ == "__main__":
    unittest.main()
