#!/usr/bin/env python3
"""
Deterministically parse the terse entry formats into a plan.json draft.

The parent skill documented the 「行事曆加入：M/D HHMM 城市 事項」 rules as
prose for the model to apply by hand (year completion, HHMM forms, 晚上/早上
markers, default duration, location = the token after the time). Every one
of those rules is mechanical, so here they are code:

    python3 parse_entries.py lines.txt --calendar 測試行事曆 [--year 2026]
    echo "7/15 1930 深圳 印度文A1 chap 04" | python3 parse_entries.py - --calendar c
    ... [--out plan.json] [--json]

Output: a plan.json draft (stdout or --out) plus a per-line **issues list**.
The contract with the model driving this skill:

- A line this parser handles is *settled* — don't re-interpret it.
- A line it can't fully handle comes back as an issue naming exactly what's
  missing (`缺地點`, `無法解析`…). Those gaps — and only those — are the
  model's to resolve, usually by asking the user (the ask-don't-guess rule).
- The draft is then normalize()d and validate()d in-process, so series
  warnings (the chap-05-twice pattern) surface here too, before anything
  is written.

Exit 0 = every line parsed clean (warnings may still be present — relay
them); exit 1 = at least one issue needs a human/model decision.

What deliberately stays OUT of this parser: conversational references
("改 7/16 那個", "那個是 Y") — resolving *which* event a follow-up refers
to is contextual judgment, the soft half. See
references/event-input-formats.md.
"""
import argparse
import datetime
import json
import os
import re
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
for _p in (_HERE, os.path.join(_HERE, "icloud")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import generate_calendar as G  # for the known-location names in loc-class.json


def _team_today():
    """「今天／今年」必須是團隊時區的（icloud/_common.py 的 TZ），不是伺服器
    本地的——雲端主機常是 UTC，台北凌晨的輸入會被補到前一天/前一年。
    _common 的重依賴是惰性載入，這個 import 不需要 caldav。"""
    try:
        from _common import TZ
        return datetime.datetime.now(TZ).date()
    except Exception:  # noqa: BLE001 — 拿不到團隊時區時退回伺服器本地
        return datetime.date.today()

PREFIX_RE = re.compile(r"^行事曆加入[:：]\s*")
DATE_RE = re.compile(r"^(明年)?\s*(\d{1,2})/(\d{1,2})\s*")
# 早上09:30 / 晚上19:00 / 下午3:00 / 1930 / 09:30 / 930
TIME_RE = re.compile(r"^(早上|上午|中午|下午|晚上)?\s*(\d{1,2}):(\d{2})\s*|^(早上|上午|中午|下午|晚上)?\s*(\d{3,4})(?!\d)\s*")
UNTIL_RE = re.compile(r"^到\s*(\d{1,2}):?(\d{2})\s*")

PM_MARKERS = ("下午", "晚上")


def _apply_marker(hour, marker):
    if marker in PM_MARKERS and hour < 12:
        return hour + 12
    return hour


def _take_time(rest):
    """-> (('HH', 'MM') or None, remaining). Accepts HH:MM and HHMM forms,
    with an optional 早上/晚上-style marker."""
    m = TIME_RE.match(rest)
    if not m:
        return None, rest
    if m.group(2) is not None:  # HH:MM form
        marker, h, mm = m.group(1), int(m.group(2)), m.group(3)
    else:  # HHMM / HMM form
        marker, raw = m.group(4), m.group(5)
        h, mm = int(raw[:-2]), raw[-2:]
    h = _apply_marker(h, marker)
    if h > 23 or int(mm) > 59:
        return None, rest
    return (f"{h:02d}", mm), rest[m.end():]


def parse_line(line, year, known_locations):
    """-> (op_dict or None, issue or None). op may be returned *with* an
    issue when it's usable except for one named gap (e.g. missing location:
    the op carries location "" and the issue says to ask)."""
    text = PREFIX_RE.sub("", line.strip())
    if not text:
        return None, None

    m = DATE_RE.match(text)
    if not m:
        return None, f"無法解析（開頭不是 M/D 日期）：「{line.strip()}」"
    next_year, mon, day = bool(m.group(1)), int(m.group(2)), int(m.group(3))
    try:
        date = datetime.date(year + (1 if next_year else 0), mon, day)
    except ValueError:
        return None, f"日期不存在：「{line.strip()}」"
    rest = text[m.end():]

    t, rest = _take_time(rest)
    if t is None:
        return None, f"無法解析（{mon}/{day} 之後找不到時間）：「{line.strip()}」"
    start = f"{date.isoformat()} {t[0]}:{t[1]}"

    end = None
    m = UNTIL_RE.match(rest)
    if m:
        h, mm = int(m.group(1)), m.group(2)
        end = f"{date.isoformat()} {h:02d}:{mm}"
        rest = rest[m.end():]

    rest = rest.strip()
    location, summary = "", rest
    parts = rest.split(None, 1)
    if len(parts) == 2:
        # Format A with spaces: the token right after the time is the location.
        location, summary = parts[0], parts[1]
    else:
        # No-space form ("7/13晚上19:00閱讀…") — only a *known* location name
        # (loc-class.json) may be split off; anything else stays in the
        # summary rather than guessing.
        for loc in sorted(known_locations, key=len, reverse=True):
            if rest.startswith(loc):
                location, summary = loc, rest[len(loc):].strip()
                break

    if not summary:
        return None, f"無法解析（缺事項）：「{line.strip()}」"

    op = {"op": "create", "summary": summary, "location": location, "start": start}
    if end:
        op["end"] = end
    issue = None
    if not location:
        issue = (f"「{summary}」（{start}）缺地點——照 ask-don't-guess 規則問使用者，"
                 "不要沿用鄰近事件的地點")
    return op, issue


def parse_lines(lines, year=None, known_locations=None):
    """-> (operations, issues). known_locations defaults to the loc-class.json
    keys, so a location the team uses daily is recognised even without a
    space before it."""
    year = year or _team_today().year
    if known_locations is None:
        known_locations = list(G.LOC_CLASS.keys())
    ops, issues = [], []
    for line in lines:
        op, issue = parse_line(line, year, known_locations)
        if op:
            ops.append(op)
        if issue:
            issues.append(issue)
    return ops, issues


def main():
    from validate_plan import normalize, validate

    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("input", help="每行一筆的文字檔，或 - 讀 stdin")
    ap.add_argument("--calendar", default="",
                    help="寫進 plan 的行事曆名稱／calendarId（不給會列為 issue）")
    ap.add_argument("--backend", default="icloud", choices=["icloud", "google", "other"])
    ap.add_argument("--year", type=int,
                    help="M/D 補全用的年份（預設＝團隊時區的今年；「明年」自動 +1）")
    ap.add_argument("--out", help="把 plan 草稿寫到這個檔（預設印到 stdout）")
    ap.add_argument("--json", action="store_true",
                    help="stdout 改輸出 {ok, plan, issues, warnings} 摘要")
    args = ap.parse_args()

    raw = (sys.stdin.read() if args.input == "-"
           else open(args.input, encoding="utf-8").read())
    ops, issues = parse_lines(raw.splitlines(), year=args.year)

    plan = {"schema": "calendar-manager-py/plan@1",
            "calendar": args.calendar, "backend": args.backend, "operations": ops}
    if not args.calendar:
        issues.append("未指定 --calendar——寫入前必須補上")

    warnings = []
    if ops:
        for n in normalize(plan):
            print(f"ℹ️  {n}", file=sys.stderr)
        errors, warnings = validate(plan)
        # calendar 缺漏已在 issues 裡；其他 validate 錯誤代表本解析器產出了
        # 壞 op，一樣列為 issue 讓人看到。
        issues += [e for e in errors if "calendar" not in e]
    else:
        issues.append("沒有解析出任何操作")

    for w in warnings:
        print(f"⚠️  {w}", file=sys.stderr)
    for i in issues:
        print(f"✗ {i}", file=sys.stderr)

    plan_text = json.dumps(plan, ensure_ascii=False, indent=2) + "\n"
    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            f.write(plan_text)
        print(f"plan 草稿已寫入：{args.out}", file=sys.stderr)

    if args.json:
        print(json.dumps({"schema": "calendar-manager-py/parse-result@1",
                          "ok": not issues, "plan": plan,
                          "issues": issues, "warnings": warnings},
                         ensure_ascii=False, indent=2))
    elif not args.out:
        print(plan_text, end="")

    print("全部解析完成。" if not issues else f"{len(issues)} 個缺口需要人／模型補。",
          file=sys.stderr)
    sys.exit(0 if not issues else 1)


if __name__ == "__main__":
    main()
