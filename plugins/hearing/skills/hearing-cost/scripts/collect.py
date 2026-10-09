#!/usr/bin/env python3
"""hearing-cost の集計スクリプト。サブコマンド collect が履歴を決定的に集計して集計 JSON を書き、init が実行ごとの作業フォルダを作る。

Python 3.8 以上・標準ライブラリのみ。集計 JSON は簡潔さのため本文・コマンド・cwd の生文字列を含めない。
"""

from __future__ import annotations

import sys

sys.dont_write_bytecode = True  # 配布先に __pycache__ を作らない

import argparse  # noqa: E402
import os  # noqa: E402
from datetime import datetime, timezone  # noqa: E402
from typing import List, Optional  # noqa: E402

from _collector import Collector  # noqa: E402
from _common import DEFAULT_MAX_LINE_BYTES, ArgError, write_json  # noqa: E402
from _parse import classify_model, iso, parse_ts  # noqa: E402,F401 - テストが collect から参照する
from _report import Report  # noqa: E402
from _settings import installed_skills, read_settings  # noqa: E402
from _workspace import format_result, init_workspace  # noqa: E402


def cmd_collect(args: argparse.Namespace) -> int:
    start = parse_ts(args.start, args.local_tz)
    end = parse_ts(args.end, args.local_tz)
    if start is None or end is None:
        raise ArgError("start/end must be ISO8601")
    if start >= end:
        raise ArgError("start must be before end")
    if args.max_line_bytes <= 0:
        raise ArgError("max-line-bytes must be positive")
    config_dir = os.path.abspath(os.path.expanduser(args.config_dir))
    if not os.path.isdir(config_dir):
        raise ArgError("config-dir not found")
    now = datetime.now(timezone.utc).timestamp()
    col = Collector(config_dir, start, end, args.exclude_session or None, args.max_line_bytes, args.local_tz, now)
    col.run()
    installed, personal = installed_skills(config_dir)
    report = Report(col, read_settings(config_dir), installed, personal, now).build()
    write_json(args.out, report)
    cov = report["coverage"]
    print("collect ok: files=%d processed=%d lines=%d" % (cov["files_total"], cov["files_processed"], cov["lines_total"]))
    print("api_calls_in_period=%d sessions=%d dedup_removed=%d coverage_ratio=%s" % (
        report["totals"]["api_calls"], report["sessions"]["count"], cov["dedup_removed"], cov["coverage_ratio"]))
    return 0


def cmd_init(args: argparse.Namespace) -> int:
    out = format_result(init_workspace(args.root)) + "\n"
    sys.stdout.buffer.write(out.encode("utf-8"))
    sys.stdout.flush()
    return 0


# ---------------------------------------------------------------- CLI

class _Parser(argparse.ArgumentParser):
    def error(self, message: str) -> None:  # type: ignore[override]
        sys.stderr.write("argument error\n")
        raise SystemExit(2)


def build_parser() -> argparse.ArgumentParser:
    p = _Parser(prog="collect.py")
    sub = p.add_subparsers(dest="cmd", parser_class=_Parser)
    c = sub.add_parser("collect")
    c.add_argument("--config-dir", required=True)
    c.add_argument("--start", required=True)
    c.add_argument("--end", required=True)
    c.add_argument("--out", required=True)
    c.add_argument("--exclude-session", default=None)
    c.add_argument("--max-line-bytes", type=int, default=DEFAULT_MAX_LINE_BYTES)
    c.add_argument("--local-tz", action="store_true")
    i = sub.add_parser("init")
    i.add_argument("--root", required=True)
    return p


def main(argv: Optional[List[str]] = None) -> int:
    try:
        args = build_parser().parse_args(argv)
        if args.cmd == "collect":
            return cmd_collect(args)
        if args.cmd == "init":
            return cmd_init(args)
        sys.stderr.write("argument error\n")
        return 2
    except ArgError as e:
        sys.stderr.write("argument error: %s\n" % e)
        return 2
    except SystemExit as e:
        return int(e.code) if isinstance(e.code, int) else 2
    except BaseException as e:  # noqa: BLE001 - 例外メッセージは出さず種類名だけ出す
        sys.stderr.write("error: %s\n" % type(e).__name__)
        return 3


if __name__ == "__main__":
    sys.exit(main())
