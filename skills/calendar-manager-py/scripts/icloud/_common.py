"""Shared helpers for the iCloud CalDAV CRUD scripts. Not run directly.

Requires the `caldav` and `icalendar` packages -- see requirements.txt in
this folder (`pip install -r requirements.txt`, ideally in a venv). Those
imports are deliberately *lazy* (inside the functions that need them): TZ is
the team-timezone constant that dependency-free scripts (parse_entries.py)
must be able to import even where caldav isn't installed.
"""
import os
import pathlib
import uuid
from datetime import datetime
from zoneinfo import ZoneInfo

# Edit this for your team's timezone (same idea as loc-class.json -- one
# constant to change, not a CLI flag).
TZ = ZoneInfo("Asia/Taipei")

CREDS_PATH = pathlib.Path(__file__).parent / ".credentials"


def load_creds():
    """Reads ICLOUD_USERNAME / ICLOUD_APP_PASSWORD from a `.credentials`
    file next to this script (see .credentials.example), falling back to
    environment variables of the same name if the file doesn't exist.
    The app password is an Apple ID "App-Specific Password" generated at
    appleid.apple.com -- NOT the normal Apple ID password, which CalDAV
    can't use once two-factor auth is on."""
    username = password = None
    if CREDS_PATH.exists():
        env = {}
        for line in CREDS_PATH.read_text().splitlines():
            if "=" in line:
                k, v = line.split("=", 1)
                env[k.strip()] = v.strip()
        username = env.get("ICLOUD_USERNAME")
        password = env.get("ICLOUD_APP_PASSWORD")
    username = username or os.environ.get("ICLOUD_USERNAME")
    password = password or os.environ.get("ICLOUD_APP_PASSWORD")
    if not username or not password:
        raise SystemExit(
            "Missing iCloud credentials. Copy .credentials.example to "
            ".credentials next to this script and fill in ICLOUD_USERNAME / "
            "ICLOUD_APP_PASSWORD, or set them as environment variables."
        )
    return username, password


def get_principal():
    import caldav  # lazy: see module docstring
    username, password = load_creds()
    client = caldav.DAVClient(url="https://caldav.icloud.com/", username=username, password=password)
    return client.principal()


def get_calendar(calendar_name):
    """calendar_name must exactly match (case-sensitive) the calendar's
    display name as shown in Calendar.app / icloud.com -- and it must
    actually be an iCloud calendar (not a local-only "On My Mac" one),
    since only iCloud calendars are reachable over CalDAV."""
    principal = get_principal()
    for cal in principal.calendars():
        if cal.get_display_name() == calendar_name:
            return cal
    raise SystemExit(
        f"calendar not found: {calendar_name!r}. Check the name is exact, "
        "and that it's an iCloud calendar (create it under the iCloud "
        "account in Calendar.app or at icloud.com/calendar, not under "
        "\"On My Mac\")."
    )


def find_event_by_uid(cal, uid):
    """iCloud's CalDAV server rejects server-side uid-filtered REPORT
    queries with a 412 Precondition Failed (confirmed against a live
    account) -- caldav's built-in event_by_uid() doesn't work here. Scan a
    wide date range and match uid client-side instead."""
    wide_start = datetime(2000, 1, 1, tzinfo=TZ)
    wide_end = datetime(2100, 1, 1, tzinfo=TZ)
    for ev in cal.search(start=wide_start, end=wide_end, event=True, expand=False):
        if str(ev.icalendar_component.get("uid")) == uid:
            return ev
    raise SystemExit(f"event not found: {uid}")


def parse_local(s):
    """'YYYY-MM-DD HH:MM' -> aware datetime in TZ."""
    return datetime.strptime(s, "%Y-%m-%d %H:%M").replace(tzinfo=TZ)


def format_local(dt):
    return dt.astimezone(TZ).strftime("%Y-%m-%d %H:%M")


def build_vevent(summary, location, start, end, uid=None):
    from icalendar import Calendar as ICalendar, Event as ICalEvent  # lazy: see module docstring
    uid = uid or str(uuid.uuid4())
    cal = ICalendar()
    cal.add("prodid", "-//calendar-manager//icloud-caldav//")
    cal.add("version", "2.0")
    ev = ICalEvent()
    ev.add("uid", uid)
    ev.add("summary", summary)
    if location:
        ev.add("location", location)
    ev.add("dtstart", start)
    ev.add("dtend", end)
    ev.add("dtstamp", datetime.now(TZ))
    cal.add_component(ev)
    return uid, cal.to_ical().decode()
