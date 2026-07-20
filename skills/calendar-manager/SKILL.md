---
name: calendar-manager
description: Manage an executive/team calendar (backed by either Google Calendar or iCloud, your choice) and publish it as styled month/week HTML pages and PNG images for sharing. Use this whenever the user gives you calendar entries as "時間、地點、事項" (time/location/item) to add to the calendar, asks to (re)generate a 月曆 (month calendar) or 週曆 (week calendar) HTML/PNG, or mentions 行事曆 in the context of a specific person's schedule (e.g. "OO董行事曆", "XX 執行長行事曆"). Also use this when the user wants to adopt this same calendar workflow for a new person or team, or asks you to convert calendar HTML files to PNG images.
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

### Saving context across sessions (per-team calendar setup)

Each team / person this calendar manages accumulates a handful of one-time
configuration answers that should NOT be re-asked every session. The
recipe:

- **Calendar identifier** (Google `calendarId` OR exact iCloud calendar
  display name, case-sensitive) — put in `user` or `memory` store under
  the team name. E.g. `user: jason-calendar = test-ceo-calendar (iCloud)`.
- **Timezone** — for iCloud, edit `TZ` in `scripts/icloud/_common.py`
  once. For Google, pass the calendar's `timeZone` from the API.
- **Default event duration** — usually 1 hour, but confirm once and
  remember.
- **Skill routing preference** — if the user has ruled a sibling skill
  out (e.g. "絕不使用 icloud-calendar"), record that as a `user` memory
  entry **before the first iCloud write of any future session** so the
  agent doesn't fall back to the default route.
- **LOC_CLASS starter config** (the per-team location-to-color mapping)
  — Jason哥's `templates/loc-class-jason.md` is one example; equivalent
  files for other teams belong alongside it. Single-line edit to
  `scripts/generate_calendar.py` adopts them.

Failure mode if you skip this: every new session asks "which calendar?"
"which timezone?" "duration = 1h OK?" — small individually, but they
add up and the user will eventually answer with "the same as last time"
to the same questions that were answered two days ago.

## Adding entries: 時間、地點、事項 → the calendar

The user will give you entries as time, location, item — sometimes several
at once, sometimes tersely ("2026.08.02 09:00部門月會"). Map directly:

| User gives | Google Calendar API | iCloud (`scripts/icloud/*.py`) |
|---|---|---|
| 事項 (item) | `summary` | `<summary>` arg |
| 地點 (location) | `location` | `<location>` arg |
| 時間 (time) | `startTime` / `endTime`, `timeZone` | `<start>` / `<end>` args, `"YYYY-MM-DD HH:MM"` |
| "全天" | `allDay: true`, start/end as midnight-to-midnight | represent as `00:00`–`23:59` same day (see `references/apple-calendar-setup.md`) |

**Default duration when the user only gives a start time:** 1 hour unless
explicitly told otherwise. The first time you onboard a new calendar,
confirm the default duration once and remember it for the rest of the
session (and ideally across sessions — see "Saving context" below).

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

### After creating each event: verify it persisted, then send back to the user

Once a `create_event.py` (or backend equivalent) call returns a UID,
**run a `list_events.py` check** to confirm the event is there with the
fields the user asked for. This is non-negotiable for the two fields that
historically fail to persist:

- **Known API quirk on Claude Code's Google Calendar connector — verify this
  before trusting it on other agents/connectors, behavior may differ or
  change:** in testing, **create event**'s `location` parameter did not
  persist (a follow-up **get event** showed no location afterward), but a
  follow-up **update event** call with the same `location` did stick.
  Workaround: after every **create event** call, call **update event** on
  the same event ID passing `location` again. The first time you use this
  skill against a new calendar, connector, or agent, do one **get event**
  check after creating a test event to see whether this bug is present before
  assuming it is (or isn't). **The iCloud backend does not have this bug** —
  location persists correctly on creation, confirmed in testing.
- **iCloud `update_event.py` is full-field overwrite.** Unlike the Google
  connector's PATCH-style update, iCloud's `update_event.py` rewrites
  summary + location + start + end all at once (see
  `scripts/icloud/update_event.py`). If you ever use it to change just
  one field (e.g. move the time from 19:30 to 09:30), you **must** pass
  the unchanged fields too or they get blanked. Same goes for the "rename
  this event" use case.
- **iCloud on Linux 6.8.x kernels** — every CalDAV call may fail with
  `niquests.exceptions.ConnectionError: ('Connection aborted.', OSError(5,
  'Input/output error'))` even though `curl` to the same URL works. Root
  cause and the in-repo monkey-patch fix are documented in
  `references/apple-calendar-setup.md` under "Known quirks" — do NOT
  attempt to "simplify" or remove the `_install_gso_safe_requests()` /
  `HfaceBackend._new_conn` patches in `scripts/icloud/_common.py`.
- **Don't conflate this skill's `scripts/icloud/*.py` with the sibling
  `icloud-calendar` skill** (`~/.hermes/skills/productivity/icloud-calendar/`).
  They both write to iCloud CalDAV but the CLI shapes are different and
  mixing them up silently writes the wrong format:
  - **this skill** — `create_event.py "<calendar>" "<summary>" "<location>" "<start YYYY-MM-DD HH:MM>" "<end YYYY-MM-DD HH:MM>"`,
    positional args, takes a `.credentials` file in `ICLOUD_USERNAME` /
    `ICLOUD_APP_PASSWORD` format (env-style). Used here because it
    matches the per-team calendar workflow.
  - **`icloud-calendar` skill** — `add_event.py --summary ... --start 2026-07-10T22:00:00 --hours 1 --location ...`,
    flag-based, takes a `~/.hermes/icloud_creds.json` JSON file with
    `apple_id` / `app_password` keys. Designed for one-shot "add an
    event" tasks, not multi-event workflow.
  Same backend, different surfaces. If the user (or a memory entry) has
  ruled the `icloud-calendar` skill out, do not import from it or copy
  its scripts — stay inside `calendar-manager/scripts/icloud/`.
- **Skill-routing preference (user-configurable).** Some users explicitly
  forbid the sibling `icloud-calendar` skill
  (`~/.hermes/skills/productivity/icloud-calendar/`) and want *every*
  行事曆 request routed through this `calendar-manager` skill, including
  the one-shot "加到 iCloud" / "新增到行事曆" cases that
  `icloud-calendar` would otherwise handle. Default behavior: use this
  skill unless the user names `icloud-calendar` in their request. If
  in doubt, check the `user` memory store for an explicit ruling.

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

**Two-tier location model** (implemented in `generate_calendar.py`):

1. **`LOC_CLASS` — user-defined mapping.** A dict of `{real_location_name:
   color_letter}` for the locations the calendar owner uses day-to-day and
   has **color habits for** (e.g. `{"淮安": "a", "深圳": "b", "台灣": "c",
   "在家": "d"}`). These locations keep their assigned color **forever** —
   adding new entries to `LOC_CLASS` is the only time colors shift, and
   they only shift for the locations explicitly renamed.
2. **`SPARE_LETTERS` — auto-assigned for new locations.** Any location
   encountered in events that isn't in `LOC_CLASS` gets the next free
   letter from `SPARE_LETTERS` (default `["e", "f", "g", "h"]`),
   **first-seen order** within the current view. This means "first time
   you see 北京 it gets pink, second new place gets yellow, etc." — and
   the assignment is stable across reruns because it's keyed off
   `LOC_CLASS` first.

**Why this shape:** the calendar owner explicitly said "顏色會讓我習慣"
(colors build habits), so unmapped locations getting a *new* color rather
than stealing an existing one is the whole point. The default 4 spare
colors are 粉/黃/紫/紅 (pink/yellow/purple/red, the "鮮明" / vivid palette
the owner picked) — defined as `--loc-e..--loc-h` in
`assets/模板_月曆.html` / `模板_週曆.html` `:root` blocks. If you need
more than 8 total locations, add both a new `--loc-i` CSS variable there
and a new letter to `SPARE_LETTERS` here.

The legend on each generated HTML is auto-built from the locations
actually present in that view, in order: `LOC_CLASS` keys first (in their
declared order), then any auto-assigned ones (in first-seen order).

**To onboard a new team/person:** edit `LOC_CLASS` in
`scripts/generate_calendar.py` to list their real site/office names → the
matching color letters are pre-defined in the templates, no CSS work
needed.

**User-specific LOC_CLASS starter configs** (e.g. Jason哥's
`{"淮安": "a", "深圳": "b", "台灣": "c", "在家": "d"}` with vivid
SPARE_LETTERS palette) live in `templates/loc-class-jason.md`. The
template's CSS variables `--loc-a..--loc-d` already match these four
labels, so adopting the file's mapping is a single-line replace in
`generate_calendar.py`.

**`parse_events` and multi-location days (fixed in this repo):** an
earlier version of `parse_events` collapsed multiple events on the same
day down to **one** location (it took the first non-`None` location
encountered and silently overwrote later ones), so a day with 3 events
at 淮安 and 1 event at 台灣 would show only 淮安 in the cell badge and
台灣 would not appear in the legend at all. The fix (also recorded in
"Bugs already found and fixed" below) makes `parse_events` collect the
**set** of distinct locations per day in first-seen order, and
`render_day_cell` renders one badge for single-location days and a
chained `A → B` badge using the template's existing `.loc--move` class
for multi-location days. If a future refactor reintroduces the
first-wins-only behavior, the symptom will be a day cell showing only
one location while the events JSON for that day lists several — same
shape as the original bug, easy to spot in the rendered PNG.

## Converting HTML to PNG

Only needed when the user explicitly wants image files (e.g. to paste into
a chat or slide deck) — HTML is the primary deliverable, PNG is secondary.

```bash
cd scripts && npm install   # once
node screenshot.js /path/to/output/202608
```

Screenshots every `*.html` in that directory to a same-named `.png` next to
it, full page, at 2x scale for crisp text. The script tries the system
Chrome (puppeteer's `channel: 'chrome'`) first, and if that fails (e.g.
no Chrome/Chromium on the system, no root to `apt install`), falls
through to the Chrome Puppeteer itself downloaded via
`npx puppeteer browsers install chrome` (cache under
`~/.cache/puppeteer/chrome/`). The fallback passes `--no-sandbox` for
container environments. Full pattern + recovery recipe in
`references/screenshot-without-system-chrome.md`.

After generating, open or read one output PNG back yourself to visually
confirm nothing is clipped or overlapping before telling the user it's
done — screenshot generation is exactly the kind of step that fails
silently (see the clipping bug below).

### After PNG verification: send it inline in the chat, not just the path

When the user asks for a 月曆 / 週曆 image, the natural end of the
workflow is *showing them the image*, not just writing it to disk. On
platforms that support it (Hermes' WeChat surface, Telegram, Discord
with image attachments, etc.), embedding `MEDIA:<absolute path>` on
its own line in the response renders the file as a native chat
attachment. Always send at least one `MEDIA:` line for the month view,
and if the user also wants week views, one per week. A first attempt
that fails to render does NOT mean the platform is incapable — see
"Common pitfalls" below for the failure-mode list and retry strategy.

## Common pitfalls — workflow-level mistakes that look like skill bugs

These are not code bugs but workflow-level traps that any agent (or human)
using this skill is likely to fall into. Each one was hit at least once
in real use. New ones should be appended below; do not silently rewrite
past entries.

- **"Never conclude 'I can't send the file to the chat' on first
  failure."** When you generate a PNG and the user can't see it inline,
  the right move is to retry the inline `MEDIA:` send as a single
  standalone message, then as a smaller resized version, then by
  regenerating with a different aspect — not to immediately recommend
  scp / GitHub / iCloud / a server download. The platform often DOES
  support inline rendering, and a small variation on the original send
  usually lands. If after 2-3 variations the user still can't see it,
  *then* ask if their client is the same one that's successfully
  received other media from this agent before falling back to "here's
  the path." The same pitfall recurs for any skill that produces a PNG
  (calendar-manager, visitor-profile-builder, architecture-diagram,
  etc.) — the rule is skill-agnostic.
- **The `icloud-calendar` skill and this skill are not interchangeable.**
  They both write to iCloud CalDAV but the CLI shapes are different and
  mixing them up silently writes the wrong format. This is also the
  single most common source of "it half-worked" reports on iCloud:
  - **this skill** — `create_event.py "<calendar>" "<summary>" "<location>" "<start YYYY-MM-DD HH:MM>" "<end YYYY-MM-DD HH:MM>"`, positional args.
  - **`icloud-calendar` skill** — `add_event.py --summary ... --start 2026-07-10T22:00:00 --hours 1 --location ...`, flag-based.
  If the user (or a memory entry) has ruled the `icloud-calendar` skill
  out for the current project, **do not import from it, do not call its
  scripts, do not copy its flags** — stay strictly inside this skill's
  `scripts/icloud/` and use the positional-arg `create_event.py`
  exactly. Confirm by reading this skill's `references/apple-calendar-setup.md`
  if you are unsure which one is in scope.
- **Re-confirm event details for multi-day / same-summary patterns.**
  When the user adds the same kind of event 2-3 days in a row (e.g. an
  evening reading session where the chapter number is in the summary),
  there's a real risk of cross-day typos — `chap 04` on day 1, `chap 05`
  on day 2, but `chap 05` again on day 3 was actually meant to be
  `chap 04` because the user only read it once. After a batch of
  similar-sounding events, do a quick `list_events.py` and call out any
  rows that look suspiciously identical / out-of-order, **before**
  confirming to the user that all writes succeeded. This is faster to
  detect now than to chase down later as "why does my 日誌 show the same
  chapter twice?"
- **Treat the skill-routing preference as load-bearing, not advisory.**
  A user who explicitly says "絕不使用 icloud-calendar, 除非我要求" is
  saying: do not let any tool-routing fallback (e.g. a default Hermes
  skill-priority that prefers the flag-based `icloud-calendar` for one-shot
  add tasks) override that. Before the first iCloud write of a session,
  confirm the active skill is `calendar-manager` (e.g. by reading the
  user's `user` memory store for the ruling, or by running
  `scripts/icloud/list_calendars.py` to confirm positional-arg shape is
  what the user expects). If the user has a memory ruling against
  `icloud-calendar` and the routing default would prefer it, the memory
  wins.

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
  gracefully via `.get(loc, "other")`, the legend just hadn't been kept
  in sync. Fixed to degrade the same way (renders without a color rather
  than crashing). If you touch `LOC_CLASS` or either render function, re-test
  with at least one location deliberately left out of the map.
- `scripts/screenshot.js` used to launch puppeteer with
  `channel: 'chrome'`, which only works when the OS has Chrome/Chromium
  installed (macOS, or a Linux box where `apt install chromium` was
  possible). On a headless/container Linux install without root, every
  call failed with an opaque `Could not find Chromium` error and the user
  had to figure out a workaround themselves. **Fixed**: the script now
  falls through to Puppeteer's own downloaded Chrome at
  `~/.cache/puppeteer/chrome/linux-<rev>/chrome-linux64/chrome`. The
  one-liner that puts a Chrome there is
  `npx puppeteer browsers install chrome` — no root needed. If the system
  Chrome is present, it's still preferred (faster, and the system one
  tracks browser updates); the cache copy is only the fallback. The
  fallback also passes `--no-sandbox` because container environments
  often lack the setuid sandbox setup that puppeteer expects. Don't
  remove the fallback even if you only ever test on macOS — the
  container-Linux case is exactly the one that fails silently.
- `parse_events` in `generate_calendar.py` used to do
  `loc = loc or location` to assign a day's location, which silently
  dropped every location except the first one seen that day. On a busy
  day with e.g. `深圳` for an early meeting followed by `在家` for an
  evening reading session, the cell badge showed `深圳` only, the
  `在家` event was invisible at the badge level, and the legend never
  learned `在家` existed. **Fixed**: `loc` is now a list and the function
  collects every distinct location seen on that day, in first-seen order.
  `render_day_cell` then renders single-location days as a normal badge
  (same as before) and multi-location days as a chained
  `A → B` badge using the template's existing `.loc--move` class. The
  `.loc--move` CSS and template example were already shipped in the
  template (under `<div class="day">` examples at line ~285 of the month
  template) — this fix is just hooking the data pipeline up to it. If
  you ever change how a day's "primary location" is chosen (e.g. to
  weight by event count), keep this in mind: the current behavior is
  "show all locations, don't pick a primary," not "pick the best one."
- **`build_month` / `build_week` variable ordering.** When refactoring
  `parse_events` output into the per-day `mapping` passed to
  `render_day_cell`, declare `locs` + `mapping` *before* the day-cell
  rendering loop, not after. Python doesn't hoist like JS — referencing a
  `mapping` computed later in the function body from inside a loop that
  runs first produces `UnboundLocalError` at runtime, even though the
  source reads top-to-bottom just fine. If you add a "compute mapping
  then render cells" pass, do it as **two passes over the data** (one to
  build `mapping`, one to render), or move the mapping build above the
  render loop. Same goes for the `grid_cells_html` string — it's built
  in the render loop, so it must be built *before* the regex `sub` that
  splices it into the template.

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
│   ├── apple-calendar-setup.md  -- walkthrough for the iCloud CalDAV backend (App-Specific Password, setup, quirks)
│   ├── icloud-credentials-location.md -- where the iCloud .credentials file lives, env fallback, common error symptoms
│   ├── screenshot-without-system-chrome.md -- PNG step on hosts without a system Chrome (use puppeteer cache + executablePath)
│   └── event-input-formats.md   -- terse 「M/D HHMM 城市 事項」 parsing rules + the "same chapter 3 days running" typo pattern
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
└── templates/
    └── loc-class-jason.md   -- Jason哥 自己的 LOC_CLASS 起手式（淮安/深圳/台灣/在家 + 鮮明配色 SPARE_LETTERS）
```
