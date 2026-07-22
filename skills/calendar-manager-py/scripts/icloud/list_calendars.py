#!/usr/bin/env python3
"""列出這個 iCloud 帳號底下所有看得到的行事曆名稱（用來確認 calendar name 拼字正確）
Usage: list_calendars.py
輸出：每行一個行事曆名稱。
"""
from _common import get_principal


def main():
    principal = get_principal()
    for cal in principal.calendars():
        print(cal.get_display_name())


if __name__ == "__main__":
    main()
