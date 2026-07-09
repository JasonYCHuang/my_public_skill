#!/usr/bin/env python3
"""刪除指定 iCloud 行事曆中某 uid 的事件
Usage: delete_event.py "<calendar name>" "<uid>"
"""
import sys
from _common import get_calendar, find_event_by_uid


def main():
    calendar_name, uid = sys.argv[1:3]
    cal = get_calendar(calendar_name)
    ev = find_event_by_uid(cal, uid)
    ev.delete()


if __name__ == "__main__":
    main()
