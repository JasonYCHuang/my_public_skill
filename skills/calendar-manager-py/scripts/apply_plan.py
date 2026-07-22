#!/usr/bin/env python3
"""
Execute a validated plan.json against the calendar, then *prove* it landed.

    python3 apply_plan.py apply plan.json [--dry-run] [--report PATH] [--json]
    python3 apply_plan.py check plan.json events.json [--json]
    python3 apply_plan.py range plan.json          # check 該抓哪段區間，印出來

**apply** (iCloud backend only — it's the one a plain Python process can
drive): normalize → validate → for each operation: execute via CalDAV, then
**read the event back from the server** and compare every field. The parent
skill stated this as prose ("run a list_events check after every create —
non-negotiable"); here it is not optional, and the per-op result lands in an
apply-report.json next to the plan. Exit 0 only if every operation executed
AND read back correctly.

Two prose traps from the parent skill become code here:

- **iCloud update is full-field overwrite.** A plan `update` op has *patch*
  semantics: list only the fields to change; this script reads the event's
  current fields first and carries the rest over, so changing a start time
  can no longer silently blank the location.
- **"Verify it persisted."** Every create/update is followed by a server
  read-back (uid matched inside the event's own time window) comparing
  summary, location, start, end; a delete is followed by a read-back that
  asserts the uid is gone.

**check** (backend-agnostic): for Google or any backend the agent writes to
with its own tools, fetch the affected range back to an events.json (the
same Google-REST shape generate_calendar.py eats) and let this compare the
plan's creates against what the server now says. This replaces "trust the
tool call succeeded" with the same read-back discipline, just split across
two steps. update/delete ops can't be matched without uids in that shape and
are reported as skipped — for full verification use the iCloud backend or
check those by hand.
"""
import argparse
import json
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
for p in (_HERE, os.path.join(_HERE, "icloud")):
    if p not in sys.path:
        sys.path.insert(0, p)

import job as J  # noqa: E402
from validate_plan import DT_FMT, normalize, validate  # noqa: E402


def _log(msg):
    print(msg, file=sys.stderr)


def _die(msg, code=2):
    _log(msg)
    sys.exit(code)


def _load_plan(path):
    with open(path, encoding="utf-8") as f:
        plan = json.load(f)
    notes = normalize(plan)
    for n in notes:
        _log(f"ℹ️  {n}")
    errors, warnings = validate(plan)
    for w in warnings:
        _log(f"⚠️  {w}")
    if errors:
        for e in errors:
            _log(f"❌ {e}")
        _die(f"\nplan.json 驗證失敗（{len(errors)} 項），未執行任何寫入。")
    return plan, warnings


# ---------------------------------------------------------------------------
# apply — iCloud CalDAV, with read-back verification per op
# ---------------------------------------------------------------------------

def _fields_of(comp):
    """The four fields we verify, formatted like the plan writes them."""
    from _common import format_local
    return {
        "summary": str(comp.get("summary", "")),
        "location": str(comp.get("location", "") or ""),
        "start": format_local(comp.get("dtstart").dt),
        "end": format_local(comp.get("dtend").dt),
    }


def _readback(cal, uid, start_s, end_s):
    """Fetch the event back from the server inside its own window (iCloud
    rejects uid-filtered REPORTs, so match uid client-side)."""
    from datetime import timedelta
    from _common import parse_local
    lo = parse_local(start_s) - timedelta(minutes=1)
    hi = parse_local(end_s) + timedelta(minutes=1)
    for ev in cal.search(start=lo, end=hi, event=True, expand=False):
        if str(ev.icalendar_component.get("uid")) == uid:
            return ev
    return None


def _compare(expected, got):
    diffs = [f"{k}：預期「{v}」實際「{got[k]}」"
             for k, v in expected.items() if got[k] != v]
    return {"ok": not diffs, "detail": "；".join(diffs) or "讀回一致"}


def _apply_create(cal, op):
    from _common import build_vevent, parse_local
    uid, ical = build_vevent(op["summary"], op.get("location") or None,
                             parse_local(op["start"]), parse_local(op["end"]))
    cal.save_event(ical)
    ev = _readback(cal, uid, op["start"], op["end"])
    if ev is None:
        return uid, {"ok": False, "detail": "寫入後讀回找不到該 uid——事件沒有持久化"}
    expected = {"summary": op["summary"], "location": op.get("location") or "",
                "start": op["start"], "end": op["end"]}
    return uid, _compare(expected, _fields_of(ev))


def _apply_update(cal, op):
    from _common import find_event_by_uid, parse_local
    uid = op["uid"]
    ev = find_event_by_uid(cal, uid)
    comp = ev.icalendar_component
    current = _fields_of(comp)
    # patch semantics: fields absent from the op keep their current value —
    # the full-overwrite trap lives and dies here, not in the model's memory.
    merged = {
        "summary": op.get("summary", current["summary"]),
        "location": op.get("location", current["location"]),
        "start": op.get("start", current["start"]),
        "end": op.get("end", current["end"]),
    }
    comp.pop("summary", None)
    comp.add("summary", merged["summary"])
    comp.pop("location", None)
    if merged["location"]:
        comp.add("location", merged["location"])
    comp.pop("dtstart", None)
    comp.add("dtstart", parse_local(merged["start"]))
    comp.pop("dtend", None)
    comp.add("dtend", parse_local(merged["end"]))
    ev.save()
    back = _readback(cal, uid, merged["start"], merged["end"])
    if back is None:
        return uid, {"ok": False, "detail": "更新後讀回找不到該 uid"}
    return uid, _compare(merged, _fields_of(back))


def _apply_delete(cal, op):
    from _common import find_event_by_uid
    uid = op["uid"]
    ev = find_event_by_uid(cal, uid)
    fields = _fields_of(ev.icalendar_component)
    ev.delete()
    back = _readback(cal, uid, fields["start"], fields["end"])
    if back is not None:
        return uid, {"ok": False, "detail": "刪除後事件仍能讀回"}
    return uid, {"ok": True, "detail": "已刪除，讀回確認不存在"}


def cmd_apply(args):
    plan, _ = _load_plan(args.plan_json)
    backend = plan.get("backend", "icloud")
    if backend != "icloud":
        _die(
            f"backend 是「{backend}」：apply 只能直接驅動 icloud。\n"
            "Google/其他後端請由 agent 用它的行事曆工具執行這份 plan，"
            "寫完把該區間抓回 events.json，再跑：\n"
            f"  python3 {os.path.basename(__file__)} check {args.plan_json} events.json")

    ops = plan["operations"]
    if args.dry_run:
        for i, op in enumerate(ops, start=1):
            _log(f"（dry-run）op#{i} {op.get('op')}：{op.get('summary', op.get('uid', ''))}")
        _log(f"（dry-run）驗證通過，共 {len(ops)} 筆操作，未寫入。")
        return 0

    from _common import get_calendar
    cal = get_calendar(plan["calendar"])

    handlers = {"create": _apply_create, "update": _apply_update, "delete": _apply_delete}
    results = []
    for i, op in enumerate(ops, start=1):
        label = op.get("summary") or op.get("uid") or ""
        try:
            uid, res = handlers[op["op"]](cal, op)
        except SystemExit as e:  # find_event_by_uid raises SystemExit on miss
            uid, res = op.get("uid"), {"ok": False, "detail": str(e)}
        except Exception as e:  # noqa: BLE001 — one op failing must not hide the rest
            uid, res = op.get("uid"), {"ok": False, "detail": f"{type(e).__name__}: {e}"}
        mark = "✓" if res["ok"] else "✗"
        _log(f"{mark} op#{i} {op['op']}「{label}」— {res['detail']}")
        results.append({"index": i, "op": op["op"], "summary": op.get("summary", ""),
                        "uid": uid, "ok": res["ok"], "detail": res["detail"]})

    report = {
        "schema": "calendar-manager-py/apply-report@1",
        "plan": os.path.abspath(args.plan_json),
        "calendar": plan["calendar"],
        "backend": backend,
        "applied_at": J.now_iso(),
        "ok": all(r["ok"] for r in results),
        "operations": results,
    }
    report_path = args.report or os.path.join(
        os.path.dirname(os.path.abspath(args.plan_json)), "apply-report.json")
    J.atomic_write_text(report_path, json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    _log(f"\nreport: {report_path}")
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    _log("全部寫入並讀回一致。" if report["ok"] else "有操作未通過讀回覆核——見上方 ✗。")
    return 0 if report["ok"] else 1


# ---------------------------------------------------------------------------
# check — compare a plan against a fetched events.json (any backend)
# ---------------------------------------------------------------------------

def _event_key(ev):
    """(summary, 'YYYY-MM-DD HH:MM' or 'YYYY-MM-DD') from a Google-REST-shaped
    event."""
    start = ev.get("start", {})
    if "date" in start:
        when = start["date"]
    else:
        when = start.get("dateTime", "")[:16].replace("T", " ")
    return (ev.get("summary", ""), when)


def _op_expected(op):
    if op.get("all_day"):
        return (op["summary"], op["start"][:10])
    return (op["summary"], op["start"])


def cmd_check(args):
    plan, _ = _load_plan(args.plan_json)
    with open(args.events_json, encoding="utf-8") as f:
        events = json.load(f)
    index = {}
    for ev in events:
        index.setdefault(_event_key(ev), []).append(ev)

    results = []
    for i, op in enumerate(plan["operations"], start=1):
        if op["op"] != "create":
            results.append({"index": i, "op": op["op"], "ok": None,
                            "detail": "events.json 無 uid，無法覆核 update/delete——用 iCloud 後端或人工確認"})
            continue
        key = _op_expected(op)
        hits = index.get(key, [])
        if not hits:
            results.append({"index": i, "op": "create", "summary": op["summary"],
                            "ok": False, "detail": f"讀回的事件中找不到「{key[0]}」@ {key[1]}"})
            continue
        ev = hits[0]
        diffs = []
        want_loc = op.get("location") or ""
        got_loc = ev.get("location") or ""
        if want_loc and got_loc != want_loc:
            diffs.append(f"location：預期「{want_loc}」實際「{got_loc}」"
                         "（Google connector 的 create 可能沒把 location 寫進去——"
                         "用 update event 補一次再重抓覆核）")
        if not op.get("all_day"):
            end = ev.get("end", {}).get("dateTime", "")[:16].replace("T", " ")
            if end and op.get("end") and end != op["end"]:
                diffs.append(f"end：預期「{op['end']}」實際「{end}」")
        results.append({"index": i, "op": "create", "summary": op["summary"],
                        "ok": not diffs, "detail": "；".join(diffs) or "讀回一致"})

    checked = [r for r in results if r["ok"] is not None]
    ok = all(r["ok"] for r in checked) and bool(checked)
    for r in results:
        mark = "✓" if r["ok"] else ("○" if r["ok"] is None else "✗")
        _log(f"{mark} op#{r['index']} {r['op']}「{r.get('summary', '')}」— {r['detail']}")
    if args.json:
        print(json.dumps({"schema": "calendar-manager-py/check-result@1",
                          "ok": ok, "operations": results},
                         ensure_ascii=False, indent=2))
    _log("覆核通過。" if ok else "覆核未全數通過——見上方 ✗/○。")
    return 0 if ok else 1


def cmd_range(args):
    """Print the date range a check-fetch must cover — min/max over the
    plan's operations, so the model never has to work it out."""
    plan, _ = _load_plan(args.plan_json)
    days = []
    for op in plan["operations"]:
        for k in ("start", "end"):
            v = op.get(k)
            if isinstance(v, str) and len(v) >= 10:
                days.append(v[:10])
    if not days:
        _die("plan 的操作裡沒有任何日期（全是 update/delete uid？）——直接用事件本身的日期抓。")
    lo, hi = min(days), max(days)
    if args.json:
        print(json.dumps({"schema": "calendar-manager-py/range@1",
                          "start": lo, "end": hi}))
    else:
        print(f"{lo} {hi}")
        _log(f"ℹ️  用你的 list events 工具抓 {lo} 00:00 到 {hi} 23:59（含），"
             "存成 events.json 後跑 apply_plan.py check")
    return 0


def main():
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("apply", help="執行 plan（iCloud），逐筆讀回覆核")
    p.add_argument("plan_json")
    p.add_argument("--dry-run", action="store_true", help="只驗證並列出將執行的操作")
    p.add_argument("--report", help="apply-report.json 的路徑（預設放在 plan 旁）")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_apply)

    p = sub.add_parser("check", help="用讀回的 events.json 覆核 plan（任何後端）")
    p.add_argument("plan_json")
    p.add_argument("events_json")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_check)

    p = sub.add_parser("range", help="印出 check 需要抓回的日期區間")
    p.add_argument("plan_json")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_range)

    args = ap.parse_args()
    sys.exit(args.func(args))


if __name__ == "__main__":
    main()
