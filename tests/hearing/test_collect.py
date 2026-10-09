"""collect サブコマンドのテスト。"""

import json
import unittest

from helpers import ConfigDir, assistant, cost_state, load_module, run, tool_result, usage, user

SID = "11111111-aaaa-bbbb-cccc-000000000001"
SID2 = "11111111-aaaa-bbbb-cccc-000000000002"
TS = "2026-09-10T10:00:00.000Z"


class CollectTestBase(unittest.TestCase):
    def setUp(self) -> None:
        self.cfg = ConfigDir()

    def tearDown(self) -> None:
        self.cfg.cleanup()

    def collect(self, *extra: str, **kw):  # type: ignore[no-untyped-def]
        rc, so, se, data, _text = self.cfg.collect(*extra, **kw)
        self.assertEqual(rc, 0, se)
        self.assertEqual(se, "")
        self.assertTrue(so.isascii())
        self.assertLessEqual(len(so.strip().splitlines()), 3)
        return data


class DedupTest(CollectTestBase):
    def test_seven_identical_lines_count_once(self) -> None:
        rows = [assistant("msg_1", SID, TS, rid="req_1", uuid="u%d" % i) for i in range(7)]
        self.cfg.write("p/a.jsonl", rows)
        d = self.collect()
        self.assertEqual(d["coverage"]["records_before_dedup"], 7)
        self.assertEqual(d["coverage"]["records_after_dedup"], 1)
        self.assertEqual(d["coverage"]["dedup_removed"], 6)
        self.assertEqual(d["totals"]["tokens_by_type"]["output"], 100)
        self.assertEqual(d["totals"]["api_calls"], 1)

    def test_partial_first_line_is_max_merged_order_independent(self) -> None:
        partial = assistant("msg_2", SID, TS, rid="r2", u=usage(inp=10, out=5, cc=0, cr=5000), uuid="a")
        final = assistant("msg_2", SID, "2026-09-10T10:00:05.000Z", rid="r2",
                          u=usage(inp=3, out=700, cc=1200, cr=4000, c5=1200), uuid="b")
        for order in ([partial, final], [final, partial]):
            self.cfg.write("p/a.jsonl", order)
            t = self.collect()["totals"]["tokens_by_type"]
            self.assertEqual((t["input"], t["output"], t["cache_creation"], t["cache_read"]), (10, 700, 1200, 5000))
            self.assertEqual(t["cache_creation_5m"], 1200)

    def test_copy_across_files_and_sidechain_counts_once(self) -> None:
        row = assistant("msg_3", SID, TS, rid="r3")
        self.cfg.write("p/%s.jsonl" % SID, [row])
        side = dict(row, isSidechain=True, agentId="agent1")
        self.cfg.write("p/%s/subagents/agent-agent1.jsonl" % SID, [side])
        d = self.collect()
        self.assertEqual(d["coverage"]["records_after_dedup"], 1)
        self.assertEqual(d["totals"]["tokens_by_type"]["output"], 100)

    def test_uuid_fallback_counted(self) -> None:
        self.cfg.write("p/a.jsonl", [assistant(None, SID, TS, uuid="only-uuid"), assistant(None, SID, TS, uuid="only-uuid")])
        d = self.collect()
        self.assertEqual(d["coverage"]["dedup_fallback_uuid"], 2)
        self.assertEqual(d["coverage"]["records_after_dedup"], 1)

    def test_synthetic_and_missing_usage(self) -> None:
        self.cfg.write("p/a.jsonl", [
            assistant("msg_s", SID, TS, model="<synthetic>"),
            assistant("msg_m", SID, TS, u=None),
            assistant("msg_n", SID, TS, u="not-a-dict"),
            assistant("msg_ok", SID, TS),
        ])
        d = self.collect()
        self.assertEqual(d["coverage"]["synthetic_lines"], 1)
        self.assertEqual(d["coverage"]["usage_missing_lines"], 2)
        self.assertEqual(d["totals"]["api_calls"], 3)
        self.assertEqual(d["totals"]["tokens_by_type"]["output"], 100)

    def test_iterations_not_read(self) -> None:
        self.cfg.write("p/a.jsonl", [assistant("msg_i", SID, TS)])
        self.assertEqual(self.collect()["totals"]["tokens_by_type"]["input"], 10)


class RobustnessTest(CollectTestBase):
    def test_huge_line_skipped(self) -> None:
        big = assistant("msg_big", SID, TS, content=[{"type": "text", "text": "x" * 5000}])
        self.cfg.write("p/a.jsonl", [big, assistant("msg_small", SID, TS)])
        d = self.collect("--max-line-bytes", "2000")
        self.assertEqual(d["coverage"]["lines_oversize_skipped"], 1)
        self.assertEqual(d["totals"]["api_calls"], 1)
        self.assertLess(d["coverage"]["coverage_ratio"], 1.0)

    def test_huge_last_line_without_newline(self) -> None:
        p = self.cfg.write("p/a.jsonl", [assistant("msg_small", SID, TS)])
        with open(p, "ab") as f:
            f.write(json.dumps(assistant("msg_big", SID, TS, content=[{"type": "text", "text": "y" * 9000}])).encode())
        d = self.collect("--max-line-bytes", "2000")
        self.assertEqual(d["coverage"]["lines_oversize_skipped"], 1)
        self.assertEqual(d["totals"]["api_calls"], 1)

    def test_broken_lines_counted_by_kind(self) -> None:
        self.cfg.write("p/a.jsonl", [
            '{"type":"assistant","message":{"id":"x", broken',
            "not json at all",
            '{"no_type_here": 1}',
            "",
            assistant("msg_ok", SID, TS),
        ])
        d = self.collect()
        kinds = d["coverage"]["lines_unreadable"]
        self.assertEqual(kinds.get("json_decode"), 1)
        self.assertEqual(kinds.get("not_object"), 1)
        self.assertEqual(kinds.get("no_type"), 1)
        self.assertEqual(kinds.get("empty"), 1)
        self.assertEqual(d["totals"]["api_calls"], 1)

    def test_bom_crlf_invalid_bytes(self) -> None:
        p = self.cfg.write("p/a.jsonl", [assistant("msg_a", SID, TS), assistant("msg_b", SID, TS)],
                           raw_suffix="\r\n", encoding_bom=True)
        with open(p, "ab") as f:
            f.write(b'{"type":"user","sessionId":"s","timestamp":"2026-09-10T10:00:00Z","message":{"content":"\xff\xfe"}}\r\n')
        d = self.collect()
        self.assertEqual(d["totals"]["api_calls"], 2)
        self.assertEqual(d["coverage"]["lines_invalid_utf8"], 1)
        self.assertEqual(d["coverage"]["coverage_ratio"], 1.0)

    def test_nested_type_does_not_confuse_line_type(self) -> None:
        att = {"parentUuid": None, "attachment": {"type": "user", "content": [{"type": "text"}]},
               "type": "attachment", "sessionId": SID, "timestamp": TS}
        self.cfg.write("p/a.jsonl", [att])
        d = self.collect()
        self.assertEqual(d["line_types"], {"attachment": 1})


class PeriodTest(CollectTestBase):
    def test_boundaries_and_missing_timestamp(self) -> None:
        self.cfg.write("p/a.jsonl", [
            assistant("m_start", SID, "2026-09-01T00:00:00Z"),
            assistant("m_end", SID, "2026-10-01T00:00:00Z"),
            assistant("m_before", SID, "2026-08-31T23:59:59.999Z"),
            assistant("m_none", SID, None),
            assistant("m_bad", SID, "yesterday"),
        ])
        d = self.collect()
        self.assertEqual(d["totals"]["api_calls"], 1)
        self.assertEqual(d["coverage"]["records_out_of_period"], 2)
        self.assertEqual(d["coverage"]["records_timestamp_missing"], 2)
        self.assertEqual(d["history_range"]["oldest_ts"], "2026-08-31T23:59:59Z")

    def test_exclude_session(self) -> None:
        self.cfg.write("p/a.jsonl", [assistant("m1", SID, TS), assistant("m2", SID2, TS),
                                     assistant("m3", SID2, TS, side=True, agent="ag")])
        d = self.collect("--exclude-session", SID2)
        self.assertEqual(d["totals"]["api_calls"], 1)
        self.assertEqual(d["coverage"]["excluded_session_records"], 2)
        self.assertEqual(d["sessions"]["count"], 1)

    def test_session_length_split_at_30_minutes(self) -> None:
        self.cfg.write("p/a.jsonl", [
            user(SID, "2026-09-10T10:00:00Z", uuid="t1"), assistant("m1", SID, "2026-09-10T10:10:00Z"),
            user(SID, "2026-09-10T10:50:00Z", uuid="t2"), assistant("m2", SID, "2026-09-10T10:55:00Z"),
        ])
        d = self.collect()
        det = list(d["sessions"]["details"].values())[0]
        self.assertEqual(det["active_minutes"], 15.0)
        self.assertEqual(det["segments"], 2)
        self.assertEqual(det["turns"], 2)

    def test_retention_flag(self) -> None:
        self.cfg.write("p/a.jsonl", [assistant("m1", SID, TS)])
        d = self.collect(start="2026-01-01T00:00:00Z")
        self.assertTrue(d["retention"]["history_starts_after_period_start"])
        self.assertIn("suspected_gap", d["retention"])

    def test_local_tz_flag(self) -> None:
        self.cfg.write("p/a.jsonl", [assistant("m1", SID, TS)])
        d = self.collect("--local-tz", env={"TZ": "Asia/Tokyo"})
        self.assertEqual(d["timeline"]["timezone"], "local")
        self.assertEqual(sum(d["timeline"]["by_hour"].values()), 1)


class FilesTest(CollectTestBase):
    def test_subagents_workflows_and_orphaned(self) -> None:
        self.cfg.write("p/%s.jsonl" % SID, [assistant("m1", SID, TS)])
        self.cfg.write("p/%s/subagents/agent-a1.jsonl" % SID, [assistant("m2", SID, TS, side=True, agent="a1")])
        self.cfg.write("p/%s/workflows/w1/agent-a2.jsonl" % SID, [assistant("m3", SID, TS, side=True, agent="a2")])
        self.cfg.write("p/old.jsonl.orphaned", [assistant("m4", SID, TS)])
        self.cfg.write("p/x.orphaned-123.jsonl", [assistant("m5", SID, TS)])
        self.cfg.write("p/y.superseded.jsonl", [assistant("m6", SID, TS)])
        d = self.collect()
        cov = d["coverage"]
        self.assertEqual(cov["files_total"], 6)
        self.assertEqual(cov["files_processed"], 3)
        self.assertEqual(cov["files_orphaned"], 2)
        self.assertEqual(cov["files_superseded"], 1)
        self.assertEqual(d["totals"]["api_calls"], 3)
        self.assertEqual(d["totals"]["sidechain_api_calls"], 2)
        self.assertEqual(d["sessions"]["subagents_distinct"], 2)

    def test_tool_results_dir_and_result_chars(self) -> None:
        tu = [{"type": "tool_use", "id": "toolu_1", "name": "Read", "input": {"file_path": "/a/b/c.PY"}}]
        self.cfg.write("p/%s.jsonl" % SID, [assistant("m1", SID, TS, content=tu),
                                            tool_result(SID, TS, "toolu_1", "z" * 12000)])
        tr = self.cfg.projects / "p" / SID / "tool-results"
        tr.mkdir(parents=True)
        (tr / "big.txt").write_text("q" * 300)
        d = self.collect()
        self.assertEqual(d["tools"]["result_chars"]["chars_total"], 12000)
        self.assertEqual(d["tools"]["result_chars"]["buckets"], {"10k_50k": 1})
        self.assertEqual(d["tools"]["result_chars"]["by_tool"]["Read"]["count"], 1)
        self.assertEqual(d["tools"]["result_chars"]["top_max_by_tool"], [{"tool": "Read", "chars_max": 12000}])
        self.assertEqual(d["tools"]["tool_results_dir"], {"files": 1, "bytes": 300})
        self.assertEqual(d["tools"]["file_extensions"], {".py": 1})


    def test_result_chars_top_max_by_tool_is_ranked_and_limited(self) -> None:
        names = ["Read", "Bash", "Grep", "Glob", "Edit", "Write", "Task"]
        uses = [{"type": "tool_use", "id": "t%d" % i, "name": n, "input": {}} for i, n in enumerate(names)]
        rows = [assistant("m1", SID, TS, content=uses)]
        rows += [tool_result(SID, TS, "t%d" % i, "x" * (100 * (i + 1))) for i in range(len(names))]
        rows += [tool_result(SID, TS, "t0", "x" * 50)]  # 同じ tool の小さい結果は最大値を変えない
        self.cfg.write("p/%s.jsonl" % SID, rows)
        top = self.collect()["tools"]["result_chars"]["top_max_by_tool"]
        self.assertEqual([t["tool"] for t in top], ["Task", "Write", "Edit", "Glob", "Grep"])
        self.assertEqual(top[0]["chars_max"], 700)


class RoleSplitTest(CollectTestBase):
    def test_main_and_sidechain_tokens_by_family(self) -> None:
        self.cfg.write("p/%s.jsonl" % SID, [
            assistant("m1", SID, TS, u=usage(inp=1, out=100, cc=10, cr=20, c5=4, c1=6), stop="end_turn"),
            assistant("m2", SID, TS, model="claude-sonnet-5-5", u=usage(inp=2, out=7, cc=0, cr=0)),
        ])
        self.cfg.write("p/%s/subagents/agent-a.jsonl" % SID, [
            assistant("m3", SID, TS, side=True, agent="a", u=usage(inp=3, out=8, cc=30, cr=40, c5=0, c1=30)),
            assistant("m3", SID, TS, side=True, agent="a", u=usage(inp=3, out=9, cc=30, cr=40, c5=0, c1=30)),
            assistant("m4", SID, TS, side=True, agent="a", u=usage(inp=1, out=50), stop="tool_use"),
        ])
        b = self.collect()["models"]["buckets"]
        opus = b["opus"]["by_role"]
        self.assertEqual(opus["main"]["tokens"]["output"], 100)
        self.assertEqual(opus["main"]["tokens"]["cache_creation_5m"], 4)
        self.assertEqual(opus["main"]["output_unfinalized_calls"], 0)
        self.assertEqual(opus["sidechain"]["api_calls"], 2)
        self.assertEqual(opus["sidechain"]["tokens"]["output"], 59)
        self.assertEqual(opus["sidechain"]["tokens"]["cache_creation_1h"], 30)
        self.assertEqual(opus["sidechain"]["output_unfinalized_calls"], 1)
        self.assertEqual(b["sonnet"]["by_role"]["main"]["output_unfinalized_calls"], 1)
        self.assertEqual(b["sonnet"]["by_role"]["sidechain"]["api_calls"], 0)
        for k in ("input", "output", "cache_creation", "cache_read"):
            self.assertEqual(opus["main"]["tokens"][k] + opus["sidechain"]["tokens"][k], b["opus"]["tokens"][k])


class CostStateTest(CollectTestBase):
    def test_outside_transcript(self) -> None:
        self.cfg.write("p/a.jsonl", [
            assistant("m1", SID, TS, u=usage(inp=10, out=100, cc=1000, cr=5000)),
            cost_state(SID, {"claude-opus-5-5": {"input": 5, "output": 50}}),
            cost_state(SID, {"claude-opus-5-5": {"input": 12, "output": 130, "cache_creation": 1000, "cache_read": 5000},
                             "claude-haiku-4-5-20251001": {"input": 800, "output": 40}}),
        ])
        rc, so, se, d, text = self.cfg.collect()
        self.assertEqual(rc, 0)
        fam = d["cost_state"]["by_family"]
        self.assertEqual(d["cost_state"]["confidence"], "estimate")
        self.assertEqual(fam["haiku"]["outside_transcript"]["input"], 800)
        self.assertTrue(fam["haiku"]["only_in_cost_state"])
        self.assertEqual(fam["opus"]["outside_transcript"]["output"], 30)
        self.assertNotIn("98.76", text)
        self.assertNotIn("12.34", text)
        self.assertNotIn("cost_usd", text.lower())


class EffortTest(CollectTestBase):
    def test_mixed_versions_absent_is_not_zero(self) -> None:
        self.cfg.write("p/a.jsonl", [
            assistant("m1", SID, TS, version="2.0.10"),
            assistant("m2", SID, TS, version="2.0.10"),
            assistant("m3", SID, TS, version="2.1.286", effort="max", pte="high"),
        ])
        e = self.collect()["effort"]
        self.assertEqual(e["effort"], {"observed_n": 1, "absent_n": 2, "values": {"max": 1}})
        self.assertEqual(e["by_version"]["2.0.10"]["effort_observed"], 0)
        self.assertEqual(e["by_version"]["2.0.10"]["records"], 2)
        self.assertEqual(e["by_version"]["2.1.286"]["per_turn_effort_observed"], 1)


class InputHardeningTest(CollectTestBase):
    def test_out_of_range_timestamps_are_not_adopted(self) -> None:
        self.cfg.write("p/a.jsonl", [
            assistant("m1", SID, "1969-12-31T23:59:59Z"), assistant("m2", SID, "2019-12-31T00:00:00Z"),
            assistant("m3", SID, "2099-01-01T00:00:00Z"), assistant("m4", SID, TS),
            user(SID, "1970-01-01T00:00:00Z", uuid="x1")])
        d = self.collect()
        cov = d["coverage"]
        self.assertEqual(cov["records_timestamp_out_of_range"], 4)
        self.assertEqual(cov["records_timestamp_missing"], 3)
        self.assertEqual(d["totals"]["api_calls"], 1)
        self.assertEqual(d["history_range"]["oldest_ts"], "2026-09-10T10:00:00Z")

    def test_parse_ts_and_iso_edge_cases(self) -> None:
        m = load_module()
        self.assertIsNone(m.parse_ts("2026-09-10T10:00:00+99:00"))
        self.assertEqual(m.iso(-1), "1969-12-31T23:59:59Z")
        self.assertEqual(m.iso(0), "1970-01-01T00:00:00Z")
        self.assertIsNone(m.iso(1e18))

    def test_bad_offset_in_period_args_exit_2(self) -> None:
        rc, _so, se, _d, _t = self.cfg.collect(start="2026-09-01T00:00:00+99:00")
        self.assertEqual(rc, 2)
        self.assertNotIn("99", se)

    def test_missing_projects_dir_is_reported(self) -> None:
        self.cfg.projects.rmdir()
        d = self.collect()
        self.assertFalse(d["coverage"]["projects_dir_found"])
        self.assertEqual(d["coverage"]["walk_errors"], 0)

    def test_walk_errors_are_counted(self) -> None:
        from unittest import mock

        m = load_module()
        col = m.Collector(str(self.cfg.root), 0.0, 1.0, None, 1000, False, 0.0)

        def fake_walk(_root, onerror=None, **_kw):  # type: ignore[no-untyped-def]
            onerror(OSError("denied"))
            return iter(())

        with mock.patch("os.walk", fake_walk):
            col._walk(str(self.cfg.projects))
        self.assertEqual(col.cov["walk_errors"], 1)

    def test_file_kind_is_judged_by_file_name_end(self) -> None:
        self.cfg.write("proj.orphaned-dir/a.jsonl", [assistant("m1", SID, TS)])
        self.cfg.write("p/b.jsonl.bak", [assistant("m2", SID, TS)])
        d = self.collect()
        self.assertEqual(d["coverage"]["files_orphaned"], 0)
        self.assertEqual(d["coverage"]["files_processed"], 1)
        self.assertEqual(d["line_types"]["_unknown_file"], 1)
        self.assertEqual(d["totals"]["api_calls"], 1)

    def test_plugin_skill_walk_skips_node_modules_and_git(self) -> None:
        for rel in ("plugins/p/skills/ok", "plugins/p/node_modules/x/skills/bad", "plugins/p/.git/skills/bad"):
            sk = self.cfg.root / rel
            sk.mkdir(parents=True)
            (sk / "SKILL.md").write_text("---\nname: n\ndescription: abc\n---\n", encoding="utf-8")
        self.cfg.write("p/a.jsonl", [assistant("m1", SID, TS)])
        d = self.collect()
        self.assertEqual(d["skills"]["installed"]["plugin"]["count"], 1)


class SettingsModelTest(CollectTestBase):
    def model(self, value: str):  # type: ignore[no-untyped-def]
        (self.cfg.root / "settings.json").write_text(json.dumps({"model": value}))
        self.cfg.write("p/a.jsonl", [assistant("m1", SID, TS)])
        return self.collect()["settings"]["model"]

    def test_aliases_are_not_non_claude(self) -> None:
        self.assertEqual(self.model("sonnet[1m]"), {"alias": "sonnet", "bucket": "sonnet", "generation": None})
        self.assertEqual(self.model("opus")["bucket"], "opus")
        for alias in ("opusplan", "default", "best"):
            self.assertEqual(self.model(alias), {"alias": alias, "bucket": "unknown", "generation": None})

    def test_full_ids_and_foreign_models_still_classified(self) -> None:
        self.assertEqual(self.model("claude-opus-4-8")["bucket"], "opus")
        self.assertEqual(self.model("gpt-9")["bucket"], "non_claude")


class ModelTest(unittest.TestCase):
    def setUp(self) -> None:
        self.m = load_module()

    def check(self, mid, bucket, gen=None):  # type: ignore[no-untyped-def]
        r = self.m.classify_model(mid)
        self.assertEqual(r["bucket"], bucket, mid)
        if gen is not None:
            self.assertEqual(r["generation"], gen, mid)

    def test_families(self) -> None:
        self.check("us.anthropic.claude-opus-5-5-v1:0", "opus", "5-5")
        self.check("anthropic.claude-sonnet-5-5", "sonnet", "5-5")
        self.check("claude-haiku-4-5-20251001", "haiku", "4-5")
        self.check("claude-opus-4-20250514", "opus", "4")
        self.check("claude-3-5-sonnet-20241022", "sonnet", "3-5")
        self.check("claude-fable-1", "fable", "1")
        self.check("arn:aws:bedrock:us-east-1:123456789012:foundation-model/anthropic.claude-opus-4-8-v1:0", "opus", "4-8")
        self.check("arn:aws:bedrock:us-east-1:123456789012:inference-profile/us.anthropic.claude-sonnet-5-5", "sonnet")
        self.check("arn:aws:bedrock:us-east-1:123456789012:application-inference-profile/abc123", "unknown")
        self.check("my-haiku-fast", "non_claude")
        self.check("gpt-9", "non_claude")
        self.check("claude-maple-6", "maple", "6")
        self.check("claude-instant-v1", "other_claude")
        self.check("", "unknown")
        self.check(None, "unknown")

    def test_buckets_in_output_have_no_combined_total(self) -> None:
        cfg = ConfigDir()
        try:
            cfg.write("p/a.jsonl", [assistant("m1", SID, TS, model="my-haiku-fast"),
                                    assistant("m2", SID, TS, model="claude-opus-5-5")])
            rc, _so, _se, d, _t = cfg.collect()
            self.assertEqual(rc, 0)
            self.assertEqual(set(d["models"]["buckets"]), {"non_claude", "opus"})
            self.assertNotIn("total", d["totals"]["tokens_by_type"])
        finally:
            cfg.cleanup()


class SkillTest(CollectTestBase):
    def test_skill_counting_and_classification(self) -> None:
        sk = self.cfg.root / "skills" / "mine"
        sk.mkdir(parents=True)
        (sk / "SKILL.md").write_text("---\nname: mine\ndescription: abcde\n---\nbody\n", encoding="utf-8")
        tools = [{"type": "tool_use", "id": "t1", "name": "Skill", "input": {"skill": "mine"}},
                 {"type": "tool_use", "id": "t2", "name": "Skill", "input": {"skill": "plug:thing"}},
                 {"type": "tool_use", "id": "t3", "name": "mcp__srv__a", "input": {}},
                 {"type": "tool_use", "id": "t4", "name": "mcp__srv__b", "input": {}},
                 {"type": "tool_use", "id": "t5", "name": "mcp__srv__a", "input": {}}]
        cmd = "<command-message>x</command-message>\n<command-name>/review</command-name>\n<command-args>secret</command-args>"
        rows = [assistant("m1", SID, TS, content=tools, attr="mine")]
        rows += [assistant("m%d" % i, SID, TS, attr="mine") for i in range(2, 6)]
        rows += [assistant("m9", SID2, TS, attr="mine"), user(SID, TS, cmd, uuid="c1")]
        self.cfg.write("p/a.jsonl", rows)
        (self.cfg.root / "settings.json").write_text(json.dumps({"mcpServers": {"a": {"env": {"K": "v"}}, "b": {}},
                                                                 "cleanupPeriodDays": 45, "model": "opus[1m]"}))
        d = self.collect()
        s = d["skills"]
        self.assertEqual(s["skill_tool"]["mine"], {"calls": 1, "classification": "personal"})
        self.assertEqual(s["skill_tool"]["plug:thing"]["classification"], "plugin")
        self.assertEqual(s["slash_commands"]["review"], {"count": 1, "classification": "builtin_or_unknown"})
        self.assertEqual(s["attribution_skill"]["mine"]["sessions"], 2)
        self.assertEqual(s["attribution_skill"]["mine"]["lines"], 6)
        self.assertEqual(s["installed"]["personal"]["count"], 1)
        self.assertEqual(s["installed"]["personal"]["description_chars_total"], 5)
        self.assertEqual(d["mcp"]["servers"]["srv"], {"calls": 3, "distinct_tools": 2})
        self.assertEqual(d["mcp"]["configured_servers_count"], 2)
        self.assertEqual(d["settings"]["cleanup_period_days"], 45)
        self.assertEqual(d["settings"]["model"]["alias"], "opus")
        self.assertEqual(d["tools"]["calls_by_name"]["Skill"], 2)


class EncodingAndExitTest(CollectTestBase):
    def test_cp932_stdout(self) -> None:
        self.cfg.write("p/a.jsonl", [user(SID, TS, "日本語の本文です①㈱"), assistant("m1", SID, TS)])
        rc, so, se, d, _t = self.cfg.collect(env={"PYTHONIOENCODING": "cp932", "PYTHONUTF8": "0", "LANG": "C"})
        self.assertEqual(rc, 0, se)
        self.assertEqual(se, "")
        self.assertEqual(d["totals"]["api_calls"], 1)

    def test_arg_errors_exit_2(self) -> None:
        rc, _so, se = run(["collect", "--config-dir", str(self.cfg.root), "--start", "bad", "--end", "x", "--out", "o"])
        self.assertEqual(rc, 2)
        rc, _so, _se = run(["collect"])
        self.assertEqual(rc, 2)
        rc, _so, _se = run(["nosuch"])
        self.assertEqual(rc, 2)

    def test_unexpected_error_exit_3_type_only(self) -> None:
        self.cfg.write("p/a.jsonl", [assistant("m1", SID, TS)])
        outdir = self.cfg.work / "bad_out_dir"
        outdir.mkdir()
        rc, so, se = run(["collect", "--config-dir", str(self.cfg.root), "--start", "2026-09-01",
                          "--end", "2026-10-01", "--out", str(outdir)])
        self.assertEqual(rc, 3)
        self.assertRegex(se.strip(), r"^error: [A-Za-z]+Error$")


if __name__ == "__main__":
    unittest.main()
