"""parse_entries.py — the terse-format rules that used to be prose."""
import json
import subprocess
import sys
from pathlib import Path

from parse_entries import parse_line, parse_lines

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
KNOWN = ["深圳", "淮安", "台灣", "在家"]


def _parse(line, year=2026, known=KNOWN):
    return parse_line(line, year, known)


class TestFormatA:
    def test_canonical_line(self):
        op, issue = _parse("行事曆加入：7/15 1930 深圳 印度文A1 chap 04")
        assert issue is None
        assert op == {"op": "create", "summary": "印度文A1 chap 04",
                      "location": "深圳", "start": "2026-07-15 19:30"}

    def test_no_prefix_needed(self):
        op, _ = _parse("7/15 1930 深圳 開會")
        assert op["start"] == "2026-07-15 19:30"

    def test_three_digit_time(self):
        op, _ = _parse("7/15 930 深圳 早會")
        assert op["start"] == "2026-07-15 09:30"

    def test_colon_time_with_pm_marker(self):
        op, _ = _parse("7/13 晚上7:00 深圳 讀書")
        assert op["start"] == "2026-07-13 19:00"

    def test_pm_marker_left_alone_when_already_24h(self):
        op, _ = _parse("7/13 晚上19:00 深圳 讀書")
        assert op["start"] == "2026-07-13 19:00"

    def test_morning_marker(self):
        op, _ = _parse("7/13 早上09:30 深圳 晨會")
        assert op["start"] == "2026-07-13 09:30"

    def test_next_year(self):
        op, _ = _parse("明年 1/05 0900 台灣 新年會議")
        assert op["start"] == "2027-01-05 09:00"

    def test_until_end_time(self):
        op, _ = _parse("8/1 0900 到 11:30 淮安 季度規劃")
        assert op["start"] == "2026-08-01 09:00"
        assert op["end"] == "2026-08-01 11:30"
        assert op["summary"] == "季度規劃"

    def test_summary_verbatim(self):
        op, _ = _parse("7/15 1930 深圳 chap02 & 第3章, mixed!")
        assert op["summary"] == "chap02 & 第3章, mixed!"


class TestNoSpaceForm:
    def test_known_location_split_off(self):
        op, issue = _parse("7/13晚上19:00在家閱讀印度文A1第1章")
        assert issue is None
        assert op["location"] == "在家"
        assert op["summary"] == "閱讀印度文A1第1章"

    def test_unknown_run_on_text_is_not_guessed(self):
        op, issue = _parse("7/13晚上19:00閱讀印度文A1第1章")
        assert op["location"] == ""
        assert op["summary"] == "閱讀印度文A1第1章"
        assert issue and "缺地點" in issue

    def test_longest_known_location_wins(self):
        op, _ = _parse("7/13 1900 深圳灣讀書", known=["深圳", "深圳灣"])
        assert op["location"] == "深圳灣"
        assert op["summary"] == "讀書"


class TestFailures:
    def test_garbage_line(self):
        op, issue = _parse("亂七八糟的一行")
        assert op is None and "無法解析" in issue

    def test_impossible_date(self):
        op, issue = _parse("2/30 0900 深圳 會")
        assert op is None and "日期不存在" in issue

    def test_missing_time(self):
        op, issue = _parse("7/15 深圳 開會")
        assert op is None and "找不到時間" in issue

    def test_missing_summary(self):
        op, issue = _parse("7/15 1930 深圳")
        # single token after time, known location, nothing left as summary
        assert op is None and "缺事項" in issue

    def test_blank_line_skipped(self):
        assert _parse("   ") == (None, None)


class TestParseLines:
    def test_aggregates_ops_and_issues(self):
        ops, issues = parse_lines(
            ["7/15 1930 深圳 chap 04", "咕嚕咕嚕", "7/16 1930 深圳 chap 05"],
            year=2026, known_locations=KNOWN)
        assert len(ops) == 2
        assert len(issues) == 1

    def test_default_known_locations_from_loc_class(self):
        import generate_calendar as G
        ops, _ = parse_lines([f"7/15 1930 {list(G.LOC_CLASS)[0]}會議"], year=2026)
        assert ops[0]["location"] == list(G.LOC_CLASS)[0]


class TestCli:
    def _run(self, text, *args):
        return subprocess.run(
            [sys.executable, str(SCRIPTS / "parse_entries.py"), "-", *args],
            input=text, capture_output=True, text=True)

    def test_clean_input_exits_zero(self):
        out = self._run("7/15 1930 深圳 chap 04\n",
                        "--calendar", "c", "--year", "2026", "--json")
        assert out.returncode == 0, out.stderr
        data = json.loads(out.stdout)
        assert data["ok"] is True
        assert data["plan"]["operations"][0]["end"] == "2026-07-15 20:30"  # normalized

    def test_gaps_exit_nonzero_and_are_listed(self):
        out = self._run("7/13晚上19:00閱讀第1章\n",
                        "--calendar", "c", "--year", "2026", "--json")
        assert out.returncode == 1
        data = json.loads(out.stdout)
        assert any("缺地點" in i for i in data["issues"])

    def test_missing_calendar_is_a_gap(self):
        out = self._run("7/15 1930 深圳 chap 04\n", "--year", "2026", "--json")
        assert out.returncode == 1
        assert any("--calendar" in i for i in json.loads(out.stdout)["issues"])

    def test_series_warning_surfaces(self):
        out = self._run("7/16 1930 深圳 chap 05\n7/17 0930 深圳 chap 05\n",
                        "--calendar", "c", "--year", "2026", "--json")
        data = json.loads(out.stdout)
        assert any("編號相同" in w for w in data["warnings"])

    def test_out_writes_plan_file(self, tmp_path):
        plan_f = tmp_path / "plan.json"
        out = self._run("7/15 1930 深圳 chap 04\n",
                        "--calendar", "c", "--year", "2026", "--out", str(plan_f))
        assert out.returncode == 0
        plan = json.loads(plan_f.read_text(encoding="utf-8"))
        assert plan["calendar"] == "c"
        assert plan["operations"][0]["location"] == "深圳"
