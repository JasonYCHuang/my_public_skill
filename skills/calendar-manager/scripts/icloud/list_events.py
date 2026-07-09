#!/usr/bin/env python3
"""列出指定 iCloud 行事曆在區間內的事件
Usage: list_events.py "<calendar name>" "<range start: YYYY-MM-DD HH:MM>" "<range end: YYYY-MM-DD HH:MM>" [--json]

預設輸出：每行一筆事件，Tab 分隔：uid, summary, location, start(YYYY-MM-DD HH:MM), end(YYYY-MM-DD HH:MM)

--json：改輸出一個 JSON 陣列，欄位形狀跟 Google Calendar REST API 一致
(summary/location/start.dateTime|date/end.dateTime|date) -- 這就是
generate_calendar.py --events 直接吃的格式，兩種後端可以共用同一支
renderer。一筆事件若剛好是同一天 00:00-23:59（我們對「全天事件」的慣例
表示法），會轉成全天事件（start/end 用 date 而非 dateTime）。
"""
import json
import sys
from _common import get_calendar, parse_local, format_local

TZ_OFFSET = "+08:00"  # keep in sync with _common.TZ's offset


def to_json_shape(uid, summary, location, start_s, end_s):
    start_date, start_time = start_s.split(" ")
    end_date, end_time = end_s.split(" ")
    if start_date == end_date and start_time == "00:00" and end_time == "23:59":
        return {
            "summary": summary,
            "location": location or None,
            "start": {"date": start_date},
            "end": {"date": start_date},
        }
    return {
        "summary": summary,
        "location": location or None,
        "start": {"dateTime": f"{start_date}T{start_time}:00{TZ_OFFSET}"},
        "end": {"dateTime": f"{end_date}T{end_time}:00{TZ_OFFSET}"},
    }


def main():
    calendar_name, start_s, end_s = sys.argv[1:4]
    as_json = "--json" in sys.argv[4:]
    start = parse_local(start_s)
    end = parse_local(end_s)
    cal = get_calendar(calendar_name)
    results = cal.search(start=start, end=end, event=True, expand=False)

    rows = []
    for ev in results:
        comp = ev.icalendar_component
        uid = str(comp.get("uid"))
        summary = str(comp.get("summary", ""))
        location = str(comp.get("location", "") or "")
        dtstart = comp.get("dtstart").dt
        dtend = comp.get("dtend").dt
        rows.append((uid, summary, location, format_local(dtstart), format_local(dtend)))

    if as_json:
        events = [to_json_shape(*row) for row in rows]
        json.dump(events, sys.stdout, ensure_ascii=False, indent=2)
    else:
        for uid, summary, location, start_fmt, end_fmt in rows:
            print(f"{uid}\t{summary}\t{location}\t{start_fmt}\t{end_fmt}")


if __name__ == "__main__":
    main()
