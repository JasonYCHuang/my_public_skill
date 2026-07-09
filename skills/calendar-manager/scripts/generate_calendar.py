#!/usr/bin/env python3
"""
Render a month view + Monday-start week views from calendar event data,
using the 模板_月曆.html / 模板_週曆.html templates in ../assets/. Backend
agnostic -- works the same whether the events came from Google Calendar or
iCloud (see SKILL.md "Choosing a backend").

Input: a JSON file containing an `events` array shaped like Google
Calendar's REST API (list of objects with summary/location/start/end
fields, start/end as {"dateTime": "..."} or {"date": "..."} for all-day).
Google's `list_events` tool already returns this shape directly; for
iCloud, `scripts/icloud/list_events.py --json` produces the same shape.
Save that array to a file and point this script at it -- no transformation
needed first.

Usage:
    python3 generate_calendar.py \
        --events events.json \
        --year 2026 --month 8 \
        --title "範例 2026 年 8 月行事曆" \
        --out-dir /path/to/output

Output: <out-dir>/<YY年M月>.html plus one <YY年M月-第N週>.html per
Monday-Sunday week needed to cover the month (see WEEK NUMBERING below).
"""
import argparse
import datetime
import json
import re
from html import escape
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parent.parent
MONTH_TEMPLATE = SKILL_DIR / "assets" / "模板_月曆.html"
WEEK_TEMPLATE = SKILL_DIR / "assets" / "模板_週曆.html"

# Extend this if your team uses more site/office names. Colors are already
# defined as CSS custom properties (--loc-a / --loc-b / --loc-c / --loc-d)
# in the templates -- add a matching --loc-xx pair there before adding a
# location here, otherwise it'll fall back to an unstyled badge. The shipped
# "地點A/B/C/D" keys are placeholders -- rename them to your team's real
# site/office names (and update the matching CSS + labels in the templates).
LOC_CLASS = {"地點A": "a", "地點B": "b", "地點C": "c", "地點D": "d"}
LOC_ORDER = list(LOC_CLASS.keys())

TIME_RANGE_RE = re.compile(r"^(\d{2}:\d{2}-\d{2}:\d{2})\s+(.*)$")
ALLDAY_RE = re.compile(r"^\[全天\]\s*(.*)$")


# ---------- Step 1: raw Google Calendar events -> {(year,month,day): (location, [event_line, ...])} ----------

def parse_events(raw_events):
    by_date = {}
    for ev in raw_events:
        summary = ev.get("summary", "(無標題)")
        location = ev.get("location") or None
        start = ev["start"]
        if "date" in start:  # all-day event
            y, m, d = (int(x) for x in start["date"].split("-"))
            line = f"[全天] {summary}"
        else:
            date_str = start["dateTime"][:10]
            time_str = start["dateTime"][11:16]
            y, m, d = (int(x) for x in date_str.split("-"))
            end_time = ev["end"]["dateTime"][11:16]
            line = f"{time_str}-{end_time} {summary}"
        key = (y, m, d)
        loc, lines = by_date.get(key, (None, []))
        loc = loc or location
        lines.append(line)
        by_date[key] = (loc, lines)
    # sort each day's lines: all-day first, then chronological
    for key, (loc, lines) in by_date.items():
        lines.sort(key=lambda l: ("0" if l.startswith("[全天]") else "1" + l[:5]))
    return by_date


# ---------- Step 2: rendering helpers (shared by month + week views) ----------

def render_location_badge(loc):
    if not loc:
        return ""
    cls = LOC_CLASS.get(loc, "other")
    return f'<span class="loc loc--{cls}">{escape(loc)}</span>'


def render_event(line):
    m = TIME_RANGE_RE.match(line)
    if m:
        return (f'<li class="ev"><span class="ev__time">{escape(m.group(1))}</span>'
                f'<span class="ev__desc">{escape(m.group(2))}</span></li>')
    m = ALLDAY_RE.match(line)
    if m:
        return (f'<li class="ev ev--allday"><span class="ev__time ev__time--tag">全天</span>'
                f'<span class="ev__desc">{escape(m.group(1))}</span></li>')
    return f'<li class="ev ev--note">{escape(line)}</li>'


def render_day_cell(day_num, is_weekend, loc, events):
    classes = "day" + (" day--weekend" if is_weekend else "")
    badge = render_location_badge(loc)
    head = (f'<div class="day__head">\n        <span class="day__num">{day_num}</span>\n        {badge}\n      </div>'
            if badge else
            f'<div class="day__head">\n        <span class="day__num">{day_num}</span>\n      </div>')
    ev_html = "".join(render_event(e) for e in events)
    body = f'<ul class="day__events">{ev_html}</ul>' if events else '<p class="day__free">—</p>'
    return f'''<div class="{classes}">
      {head}
      {body}
    </div>'''


def used_locations(entries):
    seen = []
    for loc, _ in entries:
        if loc and loc not in seen:
            seen.append(loc)
    seen.sort(key=lambda l: LOC_ORDER.index(l) if l in LOC_ORDER else 99)
    return seen


def legend_html_for(locs):
    parts = []
    for l in locs:
        cls = LOC_CLASS.get(l)
        style = f' style="background:var(--loc-{cls})"' if cls else ""
        parts.append(f'<span class="legend__item"><span class="legend__swatch"{style}></span>{l}</span>')
    return "\n    ".join(parts)


# ---------- Step 3: month view ----------

def build_month(year, month, title, events_by_day, out_path):
    """events_by_day: {day_num: (location_or_None, [event_line, ...])} -- day numbers for THIS month only."""
    first = datetime.date(year, month, 1)
    next_first = datetime.date(year + 1, 1, 1) if month == 12 else datetime.date(year, month + 1, 1)
    days_in_month = (next_first - first).days
    lead = (first.weekday() + 1) % 7  # 0 = Sunday
    total = lead + days_in_month
    trail = (7 - (total % 7)) % 7

    cells = ['<div class="day day--empty" aria-hidden="true"></div>' for _ in range(lead)]
    for d in range(1, days_in_month + 1):
        wd = (lead + d - 1) % 7
        loc, ev = events_by_day.get(d, (None, []))
        cells.append(render_day_cell(d, wd in (0, 6), loc, ev))
    cells += ['<div class="day day--empty" aria-hidden="true"></div>' for _ in range(trail)]
    grid_cells_html = "\n    ".join(cells)

    locs = used_locations(events_by_day.values())

    tpl = MONTH_TEMPLATE.read_text(encoding="utf-8")
    tpl = tpl.replace("<title>範例 2026 年 4 月行事曆</title>", f"<title>{escape(title)}</title>")
    tpl = tpl.replace(
        '<h1 class="masthead__title">範例 2026 年 4 月行事曆<sup>V2</sup></h1>',
        f'<h1 class="masthead__title">{escape(title)}</h1>'
    )
    if locs:
        tpl = re.sub(r'<div class="legend">.*?</div>\n',
                      f'<div class="legend">\n    {legend_html_for(locs)}\n  </div>\n',
                      tpl, count=1, flags=re.DOTALL)
    else:
        tpl = re.sub(r'\n  <div class="legend">.*?</div>\n', '\n', tpl, count=1, flags=re.DOTALL)

    grid_pattern = re.compile(r'(<div class="grid__weekday">週六</div>\n)(.*?)(\n    </div>\n  </div>)', re.DOTALL)
    tpl = grid_pattern.sub(lambda m: m.group(1) + "      " + grid_cells_html + m.group(3), tpl, count=1)
    tpl = re.sub(r'\n  <p class="footnote">.*?</p>\n', '\n', tpl, count=1, flags=re.DOTALL)

    out_path.write_text(tpl, encoding="utf-8")
    print("wrote", out_path)


# ---------- Step 4: week view ----------

WEEKDAY_LABELS = ["一", "二", "三", "四", "五", "六", "日"]  # Mon..Sun


def derive_title_prefix(title):
    """Pull the name/label portion off the front of a month title, e.g.
    "範例 2026 年 8 月行事曆" -> "範例", so week views (which don't take
    their own --title) can stay in sync with whatever --title was passed."""
    m = re.match(r'^(.*?)\s*\d{4}\s*年', title)
    if m and m.group(1).strip():
        return m.group(1).strip()
    return title.replace("行事曆", "").strip() or title


def build_week(week_label, start_date, events_by_ymd, out_path, title_prefix):
    """events_by_ymd: {(year,month,day): (location_or_None, [event_line, ...])} across ANY month."""
    days = [start_date + datetime.timedelta(days=i) for i in range(7)]

    cells = []
    per_week_entries = []
    for i, d in enumerate(days):
        loc, events = events_by_ymd.get((d.year, d.month, d.day), (None, []))
        per_week_entries.append((loc, events))
        is_weekend = WEEKDAY_LABELS[i] in ("六", "日")
        cells.append(render_day_cell(d.day, is_weekend, loc, events))
    grid_cells_html = "\n    ".join(cells)

    locs = used_locations(per_week_entries)
    title = f"{title_prefix} {week_label}行事曆"
    subtitle = f"{days[0].strftime('%m/%d')}–{days[-1].strftime('%m/%d')}"

    tpl = WEEK_TEMPLATE.read_text(encoding="utf-8")
    tpl = tpl.replace("<title>範例 第四週行事曆</title>", f"<title>{escape(title)}</title>")
    tpl = tpl.replace(
        '<h1 class="masthead__title">範例 第四週行事曆<sup>04/27–05/03</sup></h1>',
        f'<h1 class="masthead__title">{escape(title)}<sup>{escape(subtitle)}</sup></h1>'
    )
    if locs:
        tpl = re.sub(r'<div class="legend">.*?</div>\n',
                      f'<div class="legend">\n    {legend_html_for(locs)}\n  </div>\n',
                      tpl, count=1, flags=re.DOTALL)
    else:
        tpl = re.sub(r'\n  <div class="legend">.*?</div>\n', '\n', tpl, count=1, flags=re.DOTALL)

    grid_pattern = re.compile(r'(<div class="grid__weekday">週日</div>\n)(.*?)(\n    </div>\n  </div>)', re.DOTALL)
    tpl = grid_pattern.sub(lambda m: m.group(1) + "      " + grid_cells_html + m.group(3), tpl, count=1)

    out_path.write_text(tpl, encoding="utf-8")
    print("wrote", out_path)


# ---------- Step 5: decide which weeks to generate ----------
#
# Convention (see SKILL.md "Week numbering" for the reasoning): 第一週 is the
# first Monday-Sunday week whose Monday falls on or before the month's first
# day counted from the closest preceding Monday -- i.e. we don't create a
# separate file for a short leading stub, it's still visible in the month
# view. Weeks then run consecutively until the month's last day is covered;
# the final week may spill into the next month, same as the leading week may
# have spilled from the previous month's last "week N" file.

def week_starts_for_month(year, month):
    first = datetime.date(year, month, 1)
    next_first = datetime.date(year + 1, 1, 1) if month == 12 else datetime.date(year, month + 1, 1)
    last = next_first - datetime.timedelta(days=1)

    first_monday = first - datetime.timedelta(days=first.weekday())
    if first_monday.month != month:
        first_monday += datetime.timedelta(days=7)  # skip the previous month's trailing stub week

    starts = []
    cur = first_monday
    while cur <= last:
        starts.append(cur)
        cur += datetime.timedelta(days=7)
    return starts


CN_NUM = "一二三四五六七八九十"


def week_label(n):
    return f"第{CN_NUM[n-1]}週" if n <= 10 else f"第{n}週"


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--events", required=True, help="JSON file: raw `events` array from list_events")
    ap.add_argument("--year", type=int, required=True)
    ap.add_argument("--month", type=int, required=True)
    ap.add_argument("--title", required=True, help='e.g. "範例 2026 年 8 月行事曆"')
    ap.add_argument("--name-prefix", required=True, help='e.g. "26年8月" -- used to build output filenames')
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--skip-weeks", action="store_true", help="only generate the month view")
    args = ap.parse_args()

    raw_events = json.loads(Path(args.events).read_text(encoding="utf-8"))
    events_by_ymd = parse_events(raw_events)

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    month_events = {d: v for (y, m, d), v in events_by_ymd.items() if y == args.year and m == args.month}
    build_month(args.year, args.month, args.title, month_events, out_dir / f"{args.name_prefix}.html")

    if not args.skip_weeks:
        title_prefix = derive_title_prefix(args.title)
        for i, start in enumerate(week_starts_for_month(args.year, args.month), start=1):
            label = week_label(i)
            build_week(label, start, events_by_ymd, out_dir / f"{args.name_prefix}-{label}.html", title_prefix)


if __name__ == "__main__":
    main()
