#!/usr/bin/env python3
"""
Build a month's every deliverable (month HTML + week HTMLs, optionally PNGs)
in one deterministic pass — the -py skill's single entry point for turning
calendar events into verified files.

    python3 build.py <events.json> --year 2026 --month 8 --title-prefix 範例
                     [--job-dir DIR] [--formats html,png] [--skip-weeks]
                     [--allow-missing-font] [--json]
    python3 build.py --from-icloud "行事曆名" --year 2026 --month 8 --title-prefix 範例 ...
    python3 build.py --year 2026 --month 8 --print-range   # 只印該抓的區間，不產檔

The input is an events.json in the Google-REST shape (what a Google
`list_events` tool returns, and what `icloud/list_events.py --json` emits) —
or, with `--from-icloud`, no file at all: the needed range is computed from
the week rules and fetched from CalDAV in-process, so the iCloud path is one
command from calendar to verified files.

What it does, in order, for each run:

  0. **Compute the exact date range** the views need (the month plus the
     Monday-start weeks' spill into neighbours) — the parent skill's "fetch a
     slightly wider range" prose, as arithmetic.
  1. **Create/locate the job directory** and a `.tmp/` scratch area in it
     (job.py). One job = one rendered month = one folder. A copy of the
     events the views were built from is kept as the `events-json` artifact.
  2. **Render every view into `.tmp/`** (generate_calendar.py): the month
     grid plus one file per Monday-start week, titles and filenames derived
     from --title-prefix/--year/--month so they can't drift apart.
  3. **Verify each HTML structurally** (verify_output.py): right <title>,
     the exact day-cell count the grid must hold, closing </html>.
  4. For PNGs: **CJK font preflight before the browser launches**, then one
     screenshot.js pass over `.tmp/`, then verify each PNG (real header,
     plausible size, not blank).
  5. **Atomically place** everything and **hash it into manifest.json** —
     each artifact carrying a stable id (`month-html`, `week-1-html`, …,
     `month-png`, …), real path, size, sha256 and verify result. Downstream
     steps refer to outputs via `job.py path …`, never a reconstructed path.

The exit code is the honest answer to "did it work": 0 only if every
requested artifact was produced and verified. `--json` additionally prints a
machine-readable summary to stdout for an agent to read back instead of
guessing from prose.
"""
import argparse
import datetime
import json
import os
import subprocess
import sys
from pathlib import Path

_HERE = os.path.dirname(os.path.abspath(__file__))
for p in (_HERE, os.path.join(_HERE, "icloud")):
    if p not in sys.path:
        sys.path.insert(0, p)

import job as J  # noqa: E402
import verify_output as V  # noqa: E402
import generate_calendar as G  # noqa: E402
import validate_events as VE  # noqa: E402

ALL_FORMATS = ("html", "png")


def _log(msg):
    print(msg, file=sys.stderr)


def _die(msg, code=2):
    _log(msg)
    sys.exit(code)


def derive_names(title_prefix, year, month):
    """Title and filename stem from one prefix, so they can't disagree:
    (「範例 2026 年 8 月行事曆」, 「26年8月」)."""
    title = f"{title_prefix} {year} 年 {month} 月行事曆"
    name_prefix = f"{str(year)[2:]}年{month}月"
    return title, name_prefix


def month_day_cell_count(year, month):
    """Lead empties + days + trail empties — what the month grid must hold."""
    first = datetime.date(year, month, 1)
    next_first = (datetime.date(year + 1, 1, 1) if month == 12
                  else datetime.date(year, month + 1, 1))
    days = (next_first - first).days
    lead = (first.weekday() + 1) % 7
    total = lead + days
    return total + (7 - (total % 7)) % 7


def fetch_icloud_events(calendar_name, year, month):
    """Entry point「iCloud 一行搞定」: compute the exact range and fetch it
    over CalDAV in-process, emitting the same Google-REST shape as
    icloud/list_events.py --json."""
    from _common import get_calendar, parse_local, format_local  # noqa: PLC0415
    from list_events import to_json_shape  # noqa: PLC0415
    lo, hi = G.fetch_range_for_month(year, month)
    cal = get_calendar(calendar_name)
    start = parse_local(f"{lo} 00:00")
    end = parse_local(f"{hi} 23:59")
    events = []
    for ev in cal.search(start=start, end=end, event=True, expand=False):
        comp = ev.icalendar_component
        events.append(to_json_shape(
            str(comp.get("uid")),
            str(comp.get("summary", "")),
            str(comp.get("location", "") or ""),
            format_local(comp.get("dtstart").dt),
            format_local(comp.get("dtend").dt),
        ))
    return events, (str(lo), str(hi))


def build(events, job_dir, year, month, title_prefix, formats,
          skip_weeks=False, allow_missing_font=False, source=""):
    title, name_prefix = derive_names(title_prefix, year, month)

    # 1. Job dir + manifest + events provenance copy.
    manifest = J.Manifest.create(
        job_dir,
        {"title": title, "year": year, "month": month, "title_prefix": title_prefix},
        source=source,
    )
    tmp_dir = os.path.join(manifest.job_dir, J.TMP_DIRNAME)
    events_copy = os.path.join(manifest.job_dir, "events.json")
    J.atomic_write_text(events_copy,
                        json.dumps(events, ensure_ascii=False, indent=2) + "\n")
    manifest.record("events-json", events_copy, "json",
                    verify={"ok": True, "checks": [], "detail": f"{len(events)} 筆事件的來源副本"})

    events_by_ymd = G.parse_events(events)
    cls_map = G.assign_loc_classes(events_by_ymd)
    results = {}

    # 2. Render every view into .tmp, with its verify expectations.
    #    plans: artifact_id -> (tmp_path, final_name, expect_title, expect_cells)
    plans = {}
    month_events = {d: v for (y, m, d), v in events_by_ymd.items()
                    if y == year and m == month}
    month_tmp = Path(tmp_dir) / f"{name_prefix}.html"
    G.build_month(year, month, title, month_events, month_tmp, cls_map)
    plans["month-html"] = (str(month_tmp), f"{name_prefix}.html",
                           title, month_day_cell_count(year, month))

    if not skip_weeks:
        for i, start in enumerate(G.week_starts_for_month(year, month), start=1):
            label = G.week_label(i)
            week_tmp = Path(tmp_dir) / f"{name_prefix}-{label}.html"
            G.build_week(label, start, events_by_ymd, week_tmp, title_prefix, cls_map)
            plans[f"week-{i}-html"] = (str(week_tmp), f"{name_prefix}-{label}.html",
                                       f"{title_prefix} {label}行事曆", 7)

    # 3. Verify each HTML while it's still staged.
    verdicts = {}
    for aid, (tmp_path, _final, expect_title, cells) in plans.items():
        verdicts[aid] = V.verify_html(tmp_path, expect_title=expect_title,
                                      expect_day_cells=cells)

    # 4. PNG: font preflight, one screenshot pass over .tmp, verify each.
    png_requested = "png" in formats
    font = None
    if png_requested:
        font = V.cjk_font_check()
        if not font["ok"] and not allow_missing_font:
            _die(
                f"\n❌ CJK 字型預檢失敗：{font['detail']}\n"
                "PNG 內的中文會變成空心方框。裝好字型後重跑，"
                "或加 --allow-missing-font 明知風險仍要產出（產出會標記為未通過驗證）。",
                code=3,
            )
        script = os.path.join(_HERE, "screenshot.js")
        proc = subprocess.run(["node", script, tmp_dir],
                              capture_output=True, text=True)
        if proc.returncode != 0:
            _log(proc.stderr.strip() or proc.stdout.strip())

    # 5. Place + record. HTML is always placed (its verify result is recorded
    #    either way); a PNG is placed even when font-flagged so it can be
    #    inspected, but marked unverified.
    for aid, (tmp_path, final_name, _t, _c) in plans.items():
        hv = verdicts[aid]
        final = os.path.join(manifest.job_dir, final_name)
        if "html" in formats or png_requested:
            J.atomic_move(tmp_path, final)
            manifest.record(aid, final, "html", verify=hv)
        results[aid] = {"ok": hv["ok"], "detail": hv["detail"]}

        if png_requested:
            png_aid = aid[:-len("-html")] + "-png"
            tmp_png = tmp_path[:-len(".html")] + ".png"
            if not os.path.exists(tmp_png):
                results[png_aid] = {"ok": False,
                                    "detail": "screenshot.js 未產出（Chrome 未安裝？見 README）"}
                continue
            pv = V.verify_png(tmp_png)
            if font and not font["ok"]:
                pv["ok"] = False
                pv["checks"].append({"name": "cjk_font", "ok": False, "detail": font["detail"]})
                pv["detail"] += "｜字型預檢未過，中文可能是方框"
            elif font and not font.get("skipped"):
                pv["checks"].append({"name": "cjk_font", "ok": True, "detail": font["detail"]})
            final_png = os.path.join(manifest.job_dir, final_name[:-len(".html")] + ".png")
            J.atomic_move(tmp_png, final_png)
            manifest.record(png_aid, final_png, "png", verify=pv)
            results[png_aid] = {"ok": pv["ok"], "detail": pv["detail"]}

    manifest.save()
    return manifest, results


def _print_human(manifest, results):
    _log("")
    _log(f"job_dir : {manifest.job_dir}")
    _log(f"manifest: {manifest.path}")
    for aid, r in results.items():
        mark = "✓" if r["ok"] else "✗"
        path = manifest.data["artifacts"].get(aid, {}).get("path", "(未寫入)")
        _log(f"  {mark} {aid:<13} {r['detail']}")
        _log(f"      {path}")
    all_ok = all(r["ok"] for r in results.values())
    _log("")
    _log("全部產出並通過驗證。" if all_ok
         else "有 artifact 未通過驗證 —— 見上方 ✗ 與 manifest.verify。")


def main():
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("events_json", nargs="?",
                    help="events.json（Google REST 形狀的事件陣列）；用 --from-icloud 時免給")
    ap.add_argument("--from-icloud", metavar="行事曆名",
                    help="直接從 iCloud 抓需要的區間（區間由週次規則精確算出）")
    ap.add_argument("--year", type=int, required=True)
    ap.add_argument("--month", type=int, required=True)
    ap.add_argument("--title-prefix",
                    help='頁面標題與週曆標題共用的前綴，例如「範例」→「範例 2026 年 8 月行事曆」')
    ap.add_argument("--print-range", action="store_true",
                    help="只印出該月視圖需要抓的日期區間（給 Google 等外部 list_events 用），不產檔")
    ap.add_argument("--job-dir",
                    help="輸出資料夾（預設：~/mein-agent-storage/cal-out/<目標年月>/<時間戳>-<前綴>）")
    ap.add_argument("--formats", default="html",
                    help="逗號分隔，可選 html,png（預設 html；png 需要 Node/Chrome）")
    ap.add_argument("--skip-weeks", action="store_true", help="只產月曆，不產週曆")
    ap.add_argument("--allow-missing-font", action="store_true",
                    help="Linux 無 CJK 字型時仍產 PNG（會標記為未通過驗證）")
    ap.add_argument("--json", action="store_true", help="在 stdout 輸出機器可讀的結果摘要")
    args = ap.parse_args()

    formats = [x.strip() for x in args.formats.split(",") if x.strip()]
    bad = [x for x in formats if x not in ALL_FORMATS]
    if bad:
        _die(f"未知格式：{', '.join(bad)}（可選：{', '.join(ALL_FORMATS)}）")
    if not (1 <= args.month <= 12):
        _die(f"month 必須是 1–12，收到 {args.month}")

    if args.print_range:
        lo, hi = G.fetch_range_for_month(args.year, args.month)
        if args.json:
            print(json.dumps({"schema": "calendar-manager-py/range@1",
                              "start": str(lo), "end": str(hi)}))
        else:
            print(f"{lo} {hi}")
            _log(f"ℹ️  用你的 list events 工具抓 {lo} 00:00 到 {hi} 23:59（含），"
                 "存成 events.json 後再跑 build.py")
        sys.exit(0)
    if not args.title_prefix:
        _die("缺 --title-prefix（只有 --print-range 可以不給）")

    if args.from_icloud:
        events, (lo, hi) = fetch_icloud_events(args.from_icloud, args.year, args.month)
        source = f"icloud:{args.from_icloud} {lo}..{hi}"
        _log(f"ℹ️  已從 iCloud「{args.from_icloud}」抓取 {lo}..{hi}，共 {len(events)} 筆事件")
    elif args.events_json:
        with open(args.events_json, encoding="utf-8") as f:
            events = json.load(f)
        source = os.path.abspath(args.events_json)
    else:
        _die("請給 events.json，或用 --from-icloud 直接抓")

    # 進場契約（assets/events.schema.json）：壞事件在這裡被點名，
    # 而不是渲染到一半 KeyError 或默默畫錯。
    ev_errors = VE.validate(events)
    if ev_errors:
        for e in ev_errors:
            _log(f"❌ {e}")
        _die(f"\nevents 驗證失敗（{len(ev_errors)} 項），未產生任何檔案。")

    job_dir = args.job_dir
    if not job_dir:
        target = f"{args.year}{args.month:02d}"
        job_dir = os.path.expanduser(os.path.join(
            "~", "mein-agent-storage", "cal-out", target,
            f"{J.now_stamp()}-{J.slugify(args.title_prefix)}"))

    manifest, results = build(events, job_dir, args.year, args.month,
                              args.title_prefix, formats,
                              skip_weeks=args.skip_weeks,
                              allow_missing_font=args.allow_missing_font,
                              source=source)

    all_ok = all(r["ok"] for r in results.values())
    if args.json:
        print(json.dumps({
            "schema": "calendar-manager-py/build-result@1",
            "ok": all_ok,
            "job_dir": manifest.job_dir,
            "manifest": manifest.path,
            "artifacts": {aid: {
                "ok": r["ok"],
                "detail": r["detail"],
                "path": manifest.data["artifacts"].get(aid, {}).get("path"),
            } for aid, r in results.items()},
        }, ensure_ascii=False, indent=2))
    _print_human(manifest, results)
    sys.exit(0 if all_ok else 1)


if __name__ == "__main__":
    main()
