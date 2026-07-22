#!/usr/bin/env python3
"""在指定的 iCloud 行事曆新增一筆事件
Usage: create_event.py "<calendar name>" "<summary>" "<location>" "<start: YYYY-MM-DD HH:MM>" "<end: YYYY-MM-DD HH:MM>"
輸出新事件的 uid。
"""
import sys
from _common import get_calendar, parse_local, build_vevent


def main():
    calendar_name, summary, location, start_s, end_s = sys.argv[1:6]
    start = parse_local(start_s)
    end = parse_local(end_s)
    uid, ical = build_vevent(summary, location, start, end)
    cal = get_calendar(calendar_name)
    cal.save_event(ical)
    print(uid)


if __name__ == "__main__":
    main()
