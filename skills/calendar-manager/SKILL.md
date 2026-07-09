---
name: calendar-manager
description: Manage an executive/team calendar (backed by either Google Calendar or iCloud, your choice) and publish it as styled month/week HTML pages and PNG images for sharing. Use this whenever the user gives you calendar entries as "時間、地點、事項" (time/location/item) to add to the calendar, asks to (re)generate a 月曆 (month calendar) or 週曆 (week calendar) HTML/PNG, or mentions 行事曆 in the context of a specific person's schedule (e.g. "OO董行事曆", "XX 執行長行事曆"). Also use it when the user wants to adopt this same calendar workflow for a new person or team, or asks you to convert calendar HTML files to PNG images.
compatibility: Agent-agnostic Agent Skills package (agentskills.io format). Requires the agent to have some way to read/write events on whichever backend the user picks — Google Calendar (MCP server or built-in tool, see "Your agent's calendar tools" below) or iCloud (plain Python/CalDAV, no MCP server needed, works from any machine including a remote server) — plus Python 3 for scripts/generate_calendar.py and Node.js/npm for the optional scripts/screenshot.js PNG step.
metadata:
  built-for: "a company chairman's schedule (anonymized in this public package)"
  origin: "Claude Code (claude.ai Google Calendar connector), later extended with a tested iCloud CalDAV backend"
---

# Calendar Manager

Runs an executive/team calendar on **either Google Calendar or iCloud** (the
calendar owner's choice — colleagues who prefer one over the other can both
work against the same calendar) as the single source of truth, and renders
it into shareable HTML + PNG calendar pages on request. This skill was built
for a company chairman's schedule but the workflow generalizes to any single
calendar, and to any agent that can read/write the chosen backend and run
shell scripts — this package follows the
[agentskills.io](https://agentskills.io) open standard, not a
Claude-Code-only format. All person/company/location names in this
package's examples and templates are fictional placeholders — the original
real calendar this was built against never left the owner's own calendar
and isn't included here.

## Choosing a backend: Google Calendar or iCloud

Both back ends expose the same four operations this skill needs (list
calendars, list events, create event, update event) and both work fine
whether your agent runs locally or on a remote server — there's no
"local-only" tradeoff either way (an earlier draft of this skill assumed
Apple Calendar meant AppleScript, which *is* local-only; the iCloud CalDAV
approach documented here isn't). Pick based on what the calendar owner and
the colleagues editing it day-to-day already use:

- **Google Calendar**: see "Your agent's calendar tools" below and
  `references/hermes-setup.md`. Needs an MCP server/connector per agent;
  OAuth consent once per install.
- **iCloud**: see `references/apple-calendar-setup.md`. Needs an Apple
  App-Specific Password (simpler than OAuth app registration) and
  `scripts/icloud/` (plain Python, `pip install -r requirements.txt`). Any
  colleague can also just edit the calendar directly in Calendar.app / any
  Apple device / icloud.com — iCloud's own sync keeps that in agreement
  with what the agent sees, no extra sync step needed since it's the same
  underlying calendar, not a copy.

Nothing else in this skill (entry mapping, HTML/PNG generation, week
numbering) differs by backend — `generate_calendar.py` consumes one JSON
shape regardless of where the events came from.

## Your agent's calendar tools

This skill needs four capabilities against the calendar backend: **list
calendars**, **list events** in a date range, **create an event**, and
**update an event**. Every instruction below is written in terms of those
four operations — substitute whatever your agent and backend actually call
them.

- **Claude Code + Google Calendar**: the claude.ai Google Calendar
  connector exposes `mcp__claude_ai_Google_Calendar__list_calendars`,
  `list_events`, `create_event`, `update_event`, `get_event`. If a call
  fails with "requires re-authorization" or similar, the user needs to go
  to claude.ai → Settings → Connectors → Google Calendar → reconnect.
- **Hermes agent + Google Calendar**: doesn't ship a named Google Calendar
  connector, so this is a one-time setup step per Hermes install. See
  `references/hermes-setup.md` for a concrete walkthrough (using
  `@cocal/google-calendar-mcp`) and `assets/hermes-mcp-config.example.yaml`
  for a ready-to-merge config snippet. Once configured, confirm the real
  registered tool names with `hermes tools` before relying on them — the
  exact names weren't verifiable without a live Hermes install to test
  against.
- **Any agent + iCloud** (Claude Code, Hermes local or remote, anything
  that can run Python): use `scripts/icloud/*.py` directly as shell
  commands — no MCP server, no connector. Read
  `references/apple-calendar-setup.md` for the full setup (App-Specific
  Password, one-time `pip install`) and the four operations' exact CLI
  shapes. This was built and tested end-to-end against a live account.
- **Anything else**: same idea — find or configure a calendar integration
  first, confirm the four operations above are available, then proceed
  with the rest of this skill. If its event data isn't shaped like
  Google's REST API (`summary`/`location`/`start.dateTime`), write a small
  conversion pass into that shape before handing data to
  `generate_calendar.py` (the way `scripts/icloud/list_events.py --json`
  does for iCloud) rather than modifying `generate_calendar.py` itself.

## Installing this skill for your agent

The skill *contents* (this file, `assets/`, `scripts/`) don't change between
agents — only where you put the folder does:

- **Claude Code**: copy/symlink this folder to `.claude/skills/calendar-manager/`
  inside the project you're working in.
- **Hermes agent**: copy this folder to `~/.hermes/skills/calendar-manager/`.
- **Other agentskills.io-compatible agents**: check that agent's docs for
  its skill directory convention.

## Why a real calendar, not a spreadsheet or markdown file

Earlier versions of this workflow used an Excel file, then a markdown
"flow log". Both required a human (or the agent) to manually keep a text
file in sync with reality, and drifted. A real calendar (Google or iCloud)
is now the source of truth: adding an event is one tool call or CLI
invocation, and generating the HTML/PNG views is a read of whatever's
currently on the calendar — there's nothing to keep in sync by hand, and
(for iCloud) no separate "sync" process at all since the agent and any
human editing via Calendar.app/icloud.com are working on the exact same
calendar, not two copies.

## One-time setup (per person/team whose calendar this manages)

1. **Confirm calendar access works** for whichever backend you picked (see
   "Your agent's calendar tools" / "Choosing a backend" above) — resolve
   the specific connector/MCP/credentials setup first if it isn't already
   done.
2. **Create a dedicated calendar**, not the person's primary calendar — e.g.
   "XX董行事曆" or "OO Corp Exec Calendar". This matters because generating
   the HTML/PNG views later means listing every event on that calendar for
   a date range; a dedicated calendar means you only ever see relevant
   entries, never personal noise. The user can create it themselves (in the
   Google Calendar UI, or under the iCloud account in Calendar.app /
   icloud.com — **not** as an "On My Mac" local-only calendar if using the
   iCloud backend, CalDAV can't see those), or you can ask them to.
   For Google, resolve its `calendarId` with your **list calendars** tool
   (match on `summary`) — you'll need this ID for every other call. For
   iCloud, run `scripts/icloud/list_calendars.py` to confirm the exact
   display name (case-sensitive) — every other `scripts/icloud/*.py` script
   takes that name as its first argument.
3. **Confirm the timezone** and the default event duration to use when the
   user only gives a start time (this skill defaults to 1 hour unless told
   otherwise — ask once per new calendar/person and remember the answer).
   For iCloud, timezone is a constant (`TZ` in `scripts/icloud/_common.py`)
   — edit it for your team.
4. **`npm install`** inside `scripts/` once, to pull in `puppeteer-core`
   (needed only for the PNG step, skip if the user never asks for images).
   If using iCloud, also `pip install -r scripts/icloud/requirements.txt`
   (ideally in a venv) — see `references/apple-calendar-setup.md`.

Save the calendar identifier (calendarId or exact iCloud calendar name),
timezone, and default-duration answers as project memory or in a README
once confirmed — don't re-ask every session.

## Adding entries: 時間、地點、事項 → the calendar

The user will give you entries as time, location, item — sometimes several
at once, sometimes tersely ("2026.08.02 09:00部門月會"). Map directly:

| User gives | Google Calendar API | iCloud (`scripts/icloud/*.py`) |
|---|---|---|
| 事項 (item) | `summary` | `<summary>` arg |
| 地點 (location) | `location` | `<location>` arg |
| 時間 (time) | `startTime` / `endTime`, `timeZone` | `<start>` / `<end>` args, `"YYYY-MM-DD HH:MM"` |
| "全天" | `allDay: true`, start/end as midnight-to-midnight | represent as `00:00`–`23:59` same day (see `references/apple-calendar-setup.md`) |

**If time, location, or item is missing or ambiguous, ask before creating
the event — don't guess or silently reuse a neighboring entry's location.**
This was explicitly requested by the calendar owner after an early mistake;
treat it as a hard rule, not a suggestion. The one standing exception is
when the user explicitly tells you to reuse a specific value going forward
(e.g. "these are all 地點D unless I say otherwise") — then you can apply it
without re-asking each time, but still confirm before extrapolating to a
*different* value.

When only a start time is given, compute the end time as start + the
confirmed default duration (1 hour unless told otherwise).

**Known API quirk on Claude Code's Google Calendar connector — verify this
before trusting it on other agents/connectors, behavior may differ or
change:** in testing, **create event**'s `location` parameter did not
persist (a follow-up **get event** showed no location afterward), but a
follow-up **update event** call with the same `location` did stick.
Workaround: after every **create event** call, call **update event** on the
same event ID passing `location` again. The first time you use this skill
against a new calendar, connector, or agent, do one **get event** check
after creating a test event to see whether this bug is present before
assuming it is (or isn't). **The iCloud backend does not have this bug** —
location persists correctly on creation, confirmed in testing.

## Generating month/week HTML

1. **Fetch events** for the target month, spanning a slightly wider range
   than just the month (e.g. the month plus a few days on each side, since
   week views can spill into adjacent months — see "Week numbering" below):
   - **Google**: your **list events** tool, passing the calendar's
     `calendarId`, the date range, and the calendar's `timeZone`. Save the
     raw `events` array to a JSON file, same shape the tool returns it — do
     not hand-transform it, `generate_calendar.py` does that.
   - **iCloud**: `scripts/icloud/list_events.py "<calendar name>" "<range start>" "<range end>" --json > events.json` — this already outputs the exact shape `generate_calendar.py --events` expects, no conversion step needed.
   - **Anything else**: write a small conversion pass into the same shape
     (objects with `summary`/`location`/`start`/`end`, `start`/`end` as
     `{"dateTime": "..."}` or `{"date": "..."}` for all-day) before saving
     to the JSON file — check `parse_events()` in `generate_calendar.py` if
     you need to see the exact expected shape, but don't modify that
     function itself, keep the conversion in your own step.
2. If you fetched multiple months at once, just concatenate the arrays into
   one file; the script filters by year/month itself.
3. **Run the generator:**
   ```bash
   python3 scripts/generate_calendar.py \
     --events /path/to/events.json \
     --year 2026 --month 8 \
     --title "範例 2026 年 8 月行事曆" \
     --name-prefix "26年8月" \
     --out-dir /path/to/output/202608
   ```
   The leading word of `--title` (before the year number, e.g. "範例" above)
   is also reused as the week views' title prefix — no separate flag needed.
   This writes `<name-prefix>.html` (month view) plus one
   `<name-prefix>-第N週.html` per week needed to cover the month (pass
   `--skip-weeks` to only generate the month view). All output byte-for-byte
   reuses the CSS from `assets/模板_月曆.html` / `assets/模板_週曆.html` —
   never hand-edit the generated HTML's `<style>` block; edit the template
   and regenerate instead, so every month stays visually consistent.

### Week numbering

Weeks are Monday–Sunday. 第一週 is the first Monday-start week whose Monday
falls within the target month (a short leading stub — e.g. Aug 1–2 when the
1st is a Saturday — is *not* given its own file; it's still visible in the
month grid, and it already got covered by the previous month's final week,
since that same rule lets a month's last week spill forward). Weeks continue
consecutively until the month's last day is covered, and the final week may
spill into the next month the same way. This means two adjacent months'
generated folders share one boundary week file between them by design —
that's expected, not a bug.

### Locations and colors

The templates ship with four placeholder location badge colors via CSS
custom properties: `--loc-a` (地點A), `--loc-b` (地點B), `--loc-c` (地點C),
`--loc-d` (地點D), each with a `-soft` background variant. `LOC_CLASS` in
`generate_calendar.py` maps location names to these. Rename these to your
team's real site/office names before real use — add both the CSS variables
in `assets/模板_月曆.html` / `assets/模板_週曆.html` (`:root` block near the
top) and the corresponding entry in `LOC_CLASS` before generating — an
unmapped location (in a day badge, or in the legend) still renders fine,
just without a color.

## Converting HTML to PNG

Only needed when the user explicitly wants image files (e.g. to paste into
a chat or slide deck) — HTML is the primary deliverable, PNG is secondary.

```bash
cd scripts && npm install   # once
node screenshot.js /path/to/output/202608
```

Screenshots every `*.html` in that directory to a same-named `.png` next to
it, full page, at 2x scale for crisp text. Uses `channel: 'chrome'` in
Puppeteer, which auto-detects the system's installed Chrome — works across
machines without hardcoding a path, as long as Chrome is installed.

After generating, open or read one output PNG back yourself to visually
confirm nothing is clipped or overlapping before telling the user it's
done — screenshot generation is exactly the kind of step that fails
silently (see the clipping bug below).

## Bugs already found and fixed — watch for their class

- The week template originally forced a grid `min-width` slightly wider
  than the page's actual content area, which silently clipped the
  rightmost column's location badge at normal desktop width (not just in
  screenshots — in any browser, since `.page{max-width:1400px}` caps the
  content area regardless of window width). It was invisible until someone
  actually looked at a rendered week view closely. If you ever modify the
  templates' grid or spacing CSS, re-render a week with real multi-word
  location badges in the last column and visually check it — don't just
  trust that the diff "looks reasonable."
- `legend_html_for()` in `generate_calendar.py` used to do a plain
  `LOC_CLASS[l]` dict lookup and crashed with `KeyError` the moment a day
  used a location not yet in `LOC_CLASS` (confirmed by testing with a
  location the map didn't cover) — the per-day badge already degraded
  gracefully via `.get(loc, "other")`, the legend just hadn't been kept in
  sync. Fixed to degrade the same way (renders without a color rather than
  crashing). If you touch `LOC_CLASS` or either render function, re-test
  with at least one location deliberately left out of the map.

## Files in this skill

```
calendar-manager/
├── SKILL.md          -- this file: instructions for the agent
├── README.md          -- plain-language guide for the human calendar owner
├── assets/
│   ├── 模板_月曆.html                  -- month view template (edit this, not generated output)
│   ├── 模板_週曆.html                  -- week view template (edit this, not generated output)
│   └── hermes-mcp-config.example.yaml -- copy-pasteable Hermes + Google Calendar MCP config
├── references/
│   ├── hermes-setup.md          -- walkthrough for wiring up Google Calendar access in Hermes
│   └── apple-calendar-setup.md  -- walkthrough for the iCloud CalDAV backend (App-Specific Password, setup, quirks)
└── scripts/
    ├── generate_calendar.py  -- events JSON -> month/week HTML (backend-agnostic)
    ├── screenshot.js         -- HTML -> PNG (needs `npm install` once)
    ├── package.json
    └── icloud/                -- iCloud CalDAV backend (plain Python, no MCP server)
        ├── _common.py             -- shared connection/date helpers; TZ constant lives here
        ├── list_calendars.py      -- confirm exact calendar names on the account
        ├── create_event.py
        ├── list_events.py         -- add --json for generate_calendar.py-ready output
        ├── update_event.py
        ├── delete_event.py
        ├── requirements.txt       -- caldav, icalendar
        └── .credentials.example   -- copy to .credentials and fill in (gitignored)
```
