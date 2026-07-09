#!/usr/bin/env python3
"""更新指定 iCloud 行事曆中某 uid 的事件（全欄位覆寫）
Usage: update_event.py "<calendar name>" "<uid>" "<summary>" "<location>" "<start: YYYY-MM-DD HH:MM>" "<end: YYYY-MM-DD HH:MM>"
"""
import sys
from _common import get_calendar, parse_local, find_event_by_uid


def main():
    calendar_name, uid, summary, location, start_s, end_s = sys.argv[1:7]
    start = parse_local(start_s)
    end = parse_local(end_s)
    cal = get_calendar(calendar_name)
    ev = find_event_by_uid(cal, uid)
    comp = ev.icalendar_component
    comp.pop("summary", None)
    comp.add("summary", summary)
    comp.pop("location", None)
    if location:
        comp.add("location", location)
    comp.pop("dtstart", None)
    comp.add("dtstart", start)
    comp.pop("dtend", None)
    comp.add("dtend", end)
    ev.save()
    print(uid)


if __name__ == "__main__":
    main()
