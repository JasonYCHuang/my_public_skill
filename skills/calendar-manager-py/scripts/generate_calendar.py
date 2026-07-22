#!/usr/bin/env python3
"""
Render a month view + Monday-start week views from calendar event data,
using the 模板_月曆.html / 模板_週曆.html templates in ../assets/. Backend
agnostic -- works the same whether the events came from Google Calendar or
iCloud (see SKILL.md "Choosing a backend").

Input: a JSON file whose *top level is the events array itself* -- not an
object wrapping it, so `[{...}, {...}]` and not `{"events": [...]}`. Each
entry is shaped like Google Calendar's REST API (summary/location/start/end
fields, start/end as {"dateTime": "..."} or {"date": "..."} for all-day):

    [
      {"summary": "部門週會", "location": "台北",
       "start": {"dateTime": "2026-08-03T09:00:00+08:00"},
       "end":   {"dateTime": "2026-08-03T10:00:00+08:00"}},
      {"summary": "教育訓練", "location": "台中",
       "start": {"date": "2026-08-12"}, "end": {"date": "2026-08-13"}}
    ]

Google's `list_events` tool already returns this shape directly; for
iCloud, `scripts/icloud/list_events.py --json` produces the same shape.

Normally you don't run this directly -- `build.py` calls it and adds the
verify / atomic-write / manifest steps around it. The CLI is kept for
spot-checks and template work:

    python3 generate_calendar.py \
        --events events.json \
        --year 2026 --month 8 \
        --title "範例 2026 年 8 月行事曆" \
        --name-prefix "26年8月" \
        --out-dir /path/to/output

Differences from the parent skill's copy of this script (both were already
documented as the intended behavior in the parent SKILL.md, but its shipped
code had drifted -- reimplemented here and locked in by tests/):

- **Multi-location days.** A day whose events sit at more than one location
  renders a chained `A → B` badge (the templates' `.loc--move` class) instead
  of silently keeping only the first location seen.
- **SPARE_LETTERS auto-assignment.** Locations not in LOC_CLASS get the next
  free letter e/f/g/h (vivid palette, defined in the templates' `:root`) in
  first-seen order, instead of falling back to one unstyled badge for all of
  them. LOC_CLASS keys keep their letters forever -- "顏色會讓我習慣".
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

# The locations the calendar owner has color habits for. These keep their
# letters forever; only edit this dict deliberately. The shipped 地點A/B/C/D
# keys are placeholders -- rename them to your team's real site/office names
# (the matching --loc-a..d colors are already in the templates).
LOC_CLASS = {"地點A": "a", "地點B": "b", "地點C": "c", "地點D": "d"}
LOC_ORDER = list(LOC_CLASS.keys())

# Letters handed to locations *not* in LOC_CLASS, in first-seen order within
# the current events set. --loc-e..h (粉/黃/紫/紅) exist in both templates'
# :root blocks -- to allow more than 8 total locations, add a --loc-i pair
# there and the letter here.
SPARE_LETTERS = ["e", "f", "g", "h"]

TIME_RANGE_RE = re.compile(r"^(\d{2}:\d{2}-\d{2}:\d{2})\s+(.*)$")
ALLDAY_RE = re.compile(r"^\[全天\]\s*(.*)$")


# ---------- Step 1: raw events -> {(year,month,day): ([locations], [event_line, ...])} ----------

def parse_events(raw_events):
    """Collects the *set* of distinct locations per day, in first-seen order
    -- not just the first one. A day with 3 events at 淮安 and 1 at 台灣 must
    show both, or the second location silently vanishes from badge + legend
    (the parent skill's original first-wins bug)."""
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
        locs, lines = by_date.get(key, ([], []))
        if location and location not in locs:
            locs.append(location)
        lines.append(line)
        by_date[key] = (locs, lines)
    # sort each day's lines: all-day first, then chronological
    for key, (locs, lines) in by_date.items():
        lines.sort(key=lambda l: ("0" if l.startswith("[全天]") else "1" + l[:5]))
    return by_date


def assign_loc_classes(events_by_ymd):
    """One color-letter map for the whole events set: LOC_CLASS entries keep
    their letters, unmapped locations get SPARE_LETTERS in first-seen order
    (dates scanned chronologically, so the assignment is deterministic for a
    given events file). Locations past the spare supply map to None and
    render as the unstyled `other` badge."""
    cls_map = dict(LOC_CLASS)
    spares = list(SPARE_LETTERS)
    for key in sorted(events_by_ymd):
        for loc in events_by_ymd[key][0]:
            if loc not in cls_map:
                cls_map[loc] = spares.pop(0) if spares else None
    return cls_map


# ---------- Step 2: rendering helpers (shared by month + week views) ----------

def render_location_badge(locs, cls_map):
    """One location -> normal badge; several -> chained A → B badge via the
    templates' .loc--move class."""
    if not locs:
        return ""
    if len(locs) == 1:
        loc = locs[0]
        cls = cls_map.get(loc) or "other"
        return f'<span class="loc loc--{cls}">{escape(loc)}</span>'
    arrow = '<span class="loc__arrow" aria-hidden="true">→</span>'
    inner = arrow.join(escape(l) for l in locs)
    return f'<span class="loc loc--move">{inner}</span>'


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


def render_day_cell(day_num, is_weekend, locs, events, cls_map):
    classes = "day" + (" day--weekend" if is_weekend else "")
    badge = render_location_badge(locs, cls_map)
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
    """entries: iterable of ([locations], [lines]). Order: LOC_CLASS keys in
    declared order first, then the rest in first-seen order."""
    seen = []
    for locs, _ in entries:
        for loc in locs:
            if loc not in seen:
                seen.append(loc)
    seen.sort(key=lambda l: LOC_ORDER.index(l) if l in LOC_ORDER else 99)
    return seen


def legend_html_for(locs, cls_map):
    parts = []
    for l in locs:
        cls = cls_map.get(l)
        style = f' style="background:var(--loc-{cls})"' if cls else ""
        parts.append(f'<span class="legend__item"><span class="legend__swatch"{style}></span>{escape(l)}</span>')
    return "\n    ".join(parts)


# ---------- Step 3: month view ----------

def build_month(year, month, title, events_by_day, out_path, cls_map=None):
    """events_by_day: {day_num: ([locations], [event_line, ...])} -- day
    numbers for THIS month only."""
    if cls_map is None:
        cls_map = assign_loc_classes({(year, month, d): v for d, v in events_by_day.items()})
    first = datetime.date(year, month, 1)
    next_first = datetime.date(year + 1, 1, 1) if month == 12 else datetime.date(year, month + 1, 1)
    days_in_month = (next_first - first).days
    lead = (first.weekday() + 1) % 7  # 0 = Sunday
    total = lead + days_in_month
    trail = (7 - (total % 7)) % 7

    cells = ['<div class="day day--empty" aria-hidden="true"></div>' for _ in range(lead)]
    for d in range(1, days_in_month + 1):
        wd = (lead + d - 1) % 7
        locs, ev = events_by_day.get(d, ([], []))
        cells.append(render_day_cell(d, wd in (0, 6), locs, ev, cls_map))
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
                      f'<div class="legend">\n    {legend_html_for(locs, cls_map)}\n  </div>\n',
                      tpl, count=1, flags=re.DOTALL)
    else:
        tpl = re.sub(r'\n  <div class="legend">.*?</div>\n', '\n', tpl, count=1, flags=re.DOTALL)

    grid_pattern = re.compile(r'(<div class="grid__weekday">週六</div>\n)(.*?)(\n    </div>\n  </div>)', re.DOTALL)
    tpl = grid_pattern.sub(lambda m: m.group(1) + "      " + grid_cells_html + m.group(3), tpl, count=1)
    tpl = re.sub(r'\n  <p class="footnote">.*?</p>\n', '\n', tpl, count=1, flags=re.DOTALL)

    out_path.write_text(tpl, encoding="utf-8")
    return out_path


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


def build_week(week_label, start_date, events_by_ymd, out_path, title_prefix, cls_map=None):
    """events_by_ymd: {(year,month,day): ([locations], [event_line, ...])} across ANY month."""
    if cls_map is None:
        cls_map = assign_loc_classes(events_by_ymd)
    days = [start_date + datetime.timedelta(days=i) for i in range(7)]

    cells = []
    per_week_entries = []
    for i, d in enumerate(days):
        locs, events = events_by_ymd.get((d.year, d.month, d.day), ([], []))
        per_week_entries.append((locs, events))
        is_weekend = WEEKDAY_LABELS[i] in ("六", "日")
        cells.append(render_day_cell(d.day, is_weekend, locs, events, cls_map))
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
                      f'<div class="legend">\n    {legend_html_for(locs, cls_map)}\n  </div>\n',
                      tpl, count=1, flags=re.DOTALL)
    else:
        tpl = re.sub(r'\n  <div class="legend">.*?</div>\n', '\n', tpl, count=1, flags=re.DOTALL)

    grid_pattern = re.compile(r'(<div class="grid__weekday">週日</div>\n)(.*?)(\n    </div>\n  </div>)', re.DOTALL)
    tpl = grid_pattern.sub(lambda m: m.group(1) + "      " + grid_cells_html + m.group(3), tpl, count=1)

    out_path.write_text(tpl, encoding="utf-8")
    return out_path


# ---------- Step 5: decide which weeks to generate ----------
#
# Convention (see SKILL.md "Week numbering" for the reasoning): 第一週 is the
# first Monday-Sunday week whose Monday falls within the target month -- we
# don't create a separate file for a short leading stub, it's still visible
# in the month view (and it was already covered by the previous month's final
# week file). Weeks then run consecutively until the month's last day is
# covered; the final week may spill into the next month the same way.

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


def fetch_range_for_month(year, month):
    """The exact date range a month's views need: the month itself plus
    whatever its Monday-start weeks spill into the neighbours. Returns
    (first_date, last_date) inclusive. This replaces the parent skill's
    prose instruction to fetch "the month plus a few days on each side"."""
    first = datetime.date(year, month, 1)
    next_first = datetime.date(year + 1, 1, 1) if month == 12 else datetime.date(year, month + 1, 1)
    last = next_first - datetime.timedelta(days=1)
    starts = week_starts_for_month(year, month)
    lo = min([first] + starts)
    hi = max([last] + [s + datetime.timedelta(days=6) for s in starts])
    return lo, hi


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
    cls_map = assign_loc_classes(events_by_ymd)

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    month_events = {d: v for (y, m, d), v in events_by_ymd.items() if y == args.year and m == args.month}
    p = build_month(args.year, args.month, args.title, month_events,
                    out_dir / f"{args.name_prefix}.html", cls_map)
    print("wrote", p)

    if not args.skip_weeks:
        title_prefix = derive_title_prefix(args.title)
        for i, start in enumerate(week_starts_for_month(args.year, args.month), start=1):
            label = week_label(i)
            p = build_week(label, start, events_by_ymd,
                           out_dir / f"{args.name_prefix}-{label}.html", title_prefix, cls_map)
            print("wrote", p)


if __name__ == "__main__":
    main()
