# Using this skill with iCloud Calendar instead of Google Calendar

Read this first: **iCloud Calendar access works differently from Google
Calendar access, but not in the way you might expect.** There are two very
different ways to reach an Apple/iCloud calendar, and only one of them is
recommended here:

- **AppleScript / EventKit** (talking to the Calendar.app process itself):
  only works *locally*, on the specific Mac where that app is running and
  signed into the right iCloud account. An agent deployed on a remote
  server has no path to it at all.
- **CalDAV** (talking directly to Apple's iCloud servers over HTTPS): works
  from *anywhere* -- the same as Google Calendar's REST API. This is what
  `scripts/icloud/` in this skill uses, and it's the recommended approach
  regardless of where your agent runs.

In other words: unlike an AppleScript-based integration, **this does not
require the agent to run on any particular Mac.** A remote/cloud-hosted
Hermes bot can use this exactly the same way Claude Code running locally
can -- both just make CalDAV HTTPS calls.

This was built and tested end-to-end against a live iCloud account (create,
list, update, delete all confirmed working, including confirming that
changes made this way show up in Calendar.app on a Mac signed into the same
account, and vice versa).

## What this uses

Plain CalDAV via the Python [`caldav`](https://pypi.org/project/caldav/)
and [`icalendar`](https://pypi.org/project/icalendar/) libraries -- no MCP
server, no third-party service. The scripts in `scripts/icloud/` are
self-contained; your agent just needs to be able to run Python.

## 1. Generate an App-Specific Password

CalDAV can't use your normal Apple ID password once two-factor
authentication is on (which it almost certainly is). Generate a dedicated
one:

1. Go to [appleid.apple.com](https://appleid.apple.com) and sign in.
2. Under **Sign-In and Security → App-Specific Passwords**, generate one
   (name it something like "calendar-manager" so you recognize it later).
3. Copy the `xxxx-xxxx-xxxx-xxxx` password shown -- Apple only shows it once.

## 2. Set up the Python environment

```bash
cd scripts/icloud
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

## 3. Configure credentials

```bash
cp .credentials.example .credentials
```

Edit `.credentials` and fill in:

```
ICLOUD_USERNAME=you@icloud.com
ICLOUD_APP_PASSWORD=xxxx-xxxx-xxxx-xxxx
```

`.credentials` is gitignored -- never commit it. If your agent runs on a
remote server, that server needs its own copy of this file (or the
equivalent `ICLOUD_USERNAME` / `ICLOUD_APP_PASSWORD` environment
variables, which `_common.py` also accepts).

## 4. Make sure the target calendar is actually on iCloud

CalDAV only sees calendars that live on Apple's iCloud servers -- a "On My
Mac" local-only calendar in Calendar.app is invisible to it. Create the
calendar under the iCloud account: in Calendar.app, File → New Calendar →
choose the iCloud account (not "On My Mac") as the location; or create it
directly at [icloud.com/calendar](https://www.icloud.com/calendar/).

If this skill is managing someone else's calendar (e.g. an assistant
managing an executive's schedule), that calendar needs to be shared to the
assistant's Apple ID first: on the owner's side, Calendar app → right-click
the calendar → **Share Calendar…** → add the assistant's Apple ID with
edit permission.

## 5. The four operations, and how they map onto this skill

`scripts/icloud/` exposes the same four operations as the Google Calendar
tools, as plain Python scripts (not MCP tools) -- run them with the venv's
interpreter:

- **list calendars**: `list_calendars.py` → prints every calendar name
  visible on the account, one per line. Run this first when setting up a
  new calendar/account to confirm the exact (case-sensitive) name to pass
  to the other scripts.
- **create event**: `create_event.py "<calendar name>" "<summary>" "<location>" "<start YYYY-MM-DD HH:MM>" "<end YYYY-MM-DD HH:MM>"` → prints the new event's uid.
- **list events**: `list_events.py "<calendar name>" "<range start>" "<range end>" [--json]` → tab-separated by default (`uid, summary, location, start, end`); pass `--json` to get the same shape `generate_calendar.py --events` expects directly, no conversion step needed.
- **update event**: `update_event.py "<calendar name>" "<uid>" "<summary>" "<location>" "<start>" "<end>"` — full-field overwrite.
- **delete event**: `delete_event.py "<calendar name>" "<uid>"`

All-day events: there's no dedicated all-day representation here -- by
convention, represent an all-day event as `00:00`–`23:59` on the same day.
`list_events.py --json` converts that pattern back into a proper all-day
entry (`{"date": "..."}` instead of `{"dateTime": "..."}`) automatically.

Timezone is a constant (`TZ` in `_common.py`, defaults to `Asia/Taipei`) --
edit it for your team, same idea as `LOC_CLASS` in `generate_calendar.py`.

## Known quirks (confirmed against a live account)

- **iCloud's CalDAV server rejects server-side uid-filtered queries** with
  `412 Precondition Failed`. `caldav`'s built-in `event_by_uid()` hits this.
  `_common.py`'s `find_event_by_uid()` works around it by scanning a wide
  date range and matching the uid client-side -- don't "simplify" this back
  to `event_by_uid()`, it will break.
- Unlike the Claude Code + Google Calendar connector (see `SKILL.md`),
  **location does not silently fail to persist here** -- it's set correctly
  on creation, no follow-up update needed.

## Choosing between Google Calendar and iCloud

Both back ends expose the same four operations and both work with any
agent, local or remote -- there's no longer a "only iCloud is local-only"
tradeoff (that was true for AppleScript, not for this CalDAV approach). The
real differences:

- **Google Calendar**: needs an MCP server or connector per agent (see
  `references/hermes-setup.md`); OAuth consent flow once per install.
- **iCloud**: needs an App-Specific Password (simpler, no OAuth app
  registration) but the calendar must be reachable from wherever the agent
  runs, and whoever owns the schedule needs an Apple ID.

Pick whichever the calendar owner and the colleagues editing it alongside
the agent already use day-to-day -- both are equally capable as an agent
back end.
