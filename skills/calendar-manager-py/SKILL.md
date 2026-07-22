---
name: calendar-manager-py
description: Manage an executive/team calendar (backed by either Google Calendar or iCloud) and publish it as styled month/week HTML pages and PNG images. This is the Python-orchestrated variant of calendar-manager - entries go in via a validated plan.json that scripts/apply_plan.py executes and reads back from the server, and views come out via one command (scripts/build.py) that renders, verifies, atomically writes, and records every output in an Artifact Manifest. Use whenever the user gives calendar entries as "時間、地點、事項" to add, asks to (re)generate a 月曆/週曆 HTML/PNG, or mentions 行事曆 for a specific person's schedule (e.g. "OO董行事曆").
compatibility: Agent-agnostic Agent Skills package (agentskills.io format). Needs a calendar backend - iCloud (plain Python/CalDAV via scripts/icloud/, pip install -r scripts/icloud/requirements.txt) or Google Calendar (an MCP server/connector per agent) - plus Python 3 for the scripts (jsonschema optional but recommended, Pillow optional for the PNG blank-check) and Node.js + Chrome only for PNG output. Install steps in README.md.
metadata:
  built-for: "a company chairman's schedule (anonymized in this public package)"
  origin: "Claude Code"
  variant: "python-orchestrated (plan.json + build.py + Artifact Manifest)"
---

# Calendar Manager（Python 編排版）

Runs an executive/team calendar on **either Google Calendar or iCloud** as
the single source of truth, and renders it into shareable HTML + PNG month
and week pages. Same deliverables as the parent `calendar-manager` skill;
the difference is that the middle of both workflows — write entries and
prove they persisted; render views and prove they're intact — is
deterministic Python instead of prose the model has to remember. The design
principle, from the training deck this skill was built alongside:

> **策略保持柔性，執行保持剛性。** LLM 做軟的認知判斷，Python 做硬的執行與
> 驗證，交界處讓 LLM 產生、Python 驗證。

| 分工 | 誰負責 | 落點 |
|---|---|---|
| 判讀「時間、地點、事項」、缺欄位要問人、消歧 | **LLM（柔性）** | 讀本檔執行 |
| 寫入、讀回覆核、typo 偵測、產檔、驗證、Manifest | **Python（剛性）** | `apply_plan.py` / `build.py` |
| 交界：把使用者的話變成 `plan.json` | **LLM 產出＋Python 驗證** | 契約在 `assets/plan.schema.json` |

Full rationale and the manifest/artifact-id reference:
`references/orchestration.md`.

## The commands

```bash
# 寫入：LLM 填 plan.json → 驗證、執行、逐筆讀回覆核（iCloud）
python3 scripts/apply_plan.py apply plan.json [--dry-run]

# 覆核：任何後端 —— 用讀回的 events.json 比對 plan 是否真的都寫進去了
python3 scripts/apply_plan.py check plan.json events.json

# 產出：events → 月曆＋週曆 HTML（＋PNG），驗證、原子寫入、記進 manifest
python3 scripts/build.py events.json --year 2026 --month 8 --title-prefix 範例
python3 scripts/build.py --from-icloud "行事曆名" --year 2026 --month 8 --title-prefix 範例

# 查詢：產出後讀真實狀態，不要憑記憶回報路徑
python3 scripts/job.py list <job_dir>
python3 scripts/job.py path <job_dir> month-png
```

`build.py` exits non-zero if anything failed verification; add `--json` for
a machine-readable summary. Artifact ids are stable: `events-json`,
`month-html`, `week-1-html`…, `month-png`, `week-1-png`…. Refer to outputs
by id, not by a path you reconstructed.

## Choosing a backend: Google Calendar or iCloud

Both expose the four operations this skill needs (list calendars, list
events, create, update); pick whichever the calendar owner's colleagues
already use day-to-day. Nothing in entry mapping or rendering differs by
backend.

- **iCloud** (the fully-orchestrated path): `scripts/icloud/` is plain
  Python/CalDAV — no MCP server, works from any machine. Setup (Apple
  App-Specific Password, one-time `pip install`) in
  `references/apple-calendar-setup.md`. `apply_plan.py apply` and
  `build.py --from-icloud` drive it in-process.
- **Google Calendar**: needs an MCP server/connector per agent (Claude
  Code: the claude.ai Google Calendar connector; Hermes: see
  `references/hermes-setup.md` and `assets/hermes-mcp-config.example.yaml`).
  The agent executes the plan's operations with its own calendar tools,
  then **still runs the hard verification**: fetch the affected range back
  to an events.json and run `apply_plan.py check`.

One-time setup per person/team: create a **dedicated calendar** (never the
person's primary one; for iCloud not an "On My Mac" local calendar —
CalDAV can't see those), confirm its exact identifier
(`scripts/icloud/list_calendars.py`, or the Google calendarId), confirm the
timezone (`TZ` in `scripts/icloud/_common.py`) and the default event
duration (usually 1 hour — `default_duration_minutes` in each plan). Save
these answers as project memory; don't re-ask every session.

## Adding entries: 時間、地點、事項 → plan.json → the calendar

The user gives entries as time, location, item — sometimes several at once,
sometimes tersely ("2026.08.02 09:00部門月會"; parsing rules for the terse
forms: `references/event-input-formats.md`). **Your job (the soft half):**

1. **If time, location, or item is missing or ambiguous, ask before
   writing — don't guess or silently reuse a neighboring entry's
   location.** This was explicitly requested by the calendar owner after an
   early mistake; treat it as a hard rule. The one standing exception: the
   user explicitly says to reuse a value going forward ("these are all
   地點D unless I say otherwise") — apply it without re-asking, but still
   confirm before extrapolating to a *different* value.
2. Fill the entries into a `plan.json` (contract:
   `assets/plan.schema.json`):

   ```json
   {
     "calendar": "測試行事曆",
     "backend": "icloud",
     "default_duration_minutes": 60,
     "operations": [
       {"op": "create", "summary": "部門月會", "location": "地點A", "start": "2026-08-02 09:00"},
       {"op": "create", "summary": "全天工作坊", "location": "地點B", "start": "2026-08-05", "all_day": true},
       {"op": "update", "uid": "<uid>", "start": "2026-08-03 09:30", "end": "2026-08-03 10:30"}
     ]
   }
   ```

   You do **not** compute end times (missing `end` = start +
   `default_duration_minutes`, filled by normalize) and an `update` lists
   **only the fields to change** — the iCloud full-field-overwrite trap is
   handled by code, which reads the event's current fields and merges.
3. **Run it** — `python3 scripts/apply_plan.py apply plan.json`. The hard
   half takes over: schema/time validation, duplicate and cross-day-typo
   detection (the "chap 05 two days running" pattern is flagged *before*
   anything is written), then per-operation execute + **server read-back**
   comparing every field, and an `apply-report.json` you can read instead
   of trusting prose. **Relay any ⚠️ warnings to the user** — they don't
   block, but they exist precisely because this class of typo was hit in
   real use.
4. **Google/other backends:** `apply` refuses to run (it can't drive your
   agent's tools); execute the plan's operations with your calendar tools,
   fetch the affected date range back to an `events.json`, and run
   `apply_plan.py check plan.json events.json`. A known Google-connector
   quirk — `location` not persisting on create — shows up here as a ✗ with
   instructions (fix: one **update event** call re-passing `location`,
   then re-fetch and re-check).

## Generating month/week views

- **iCloud — one command.** `build.py --from-icloud "行事曆名" --year 2026
  --month 8 --title-prefix 範例` computes the exact date range the views
  need (the month plus its Monday-start weeks' spill into neighbours — no
  "fetch a bit wider" guesswork), fetches it over CalDAV, renders, verifies,
  and records everything in the manifest.
- **Google/other** — two steps: fetch that range with your **list events**
  tool into an events.json (the raw `events` array, same shape the tool
  returns), then `build.py events.json --year … --month … --title-prefix …`.
  If the shape isn't Google-REST-like, write a small conversion pass (the
  way `icloud/list_events.py --json` does); don't modify the renderer.
- Add `--formats html,png` when the user wants images (needs Node + Chrome;
  `npm install` once inside `scripts/`). `build.py` runs the CJK-font
  preflight before launching the browser and structurally verifies every
  PNG — but still **look at one output PNG yourself** (the Read tool
  renders images) as a final human check for clipping/overlap the
  structural checks can't see.
- All output reuses the CSS from `assets/模板_月曆.html` /
  `assets/模板_週曆.html` byte-for-byte. **Never hand-edit generated
  HTML** — edit the template and re-run `build.py`, so every month stays
  visually consistent.

### After PNG verification: send it inline, not just the path

On platforms that support it (Hermes' WeChat surface, Telegram, Discord),
embed `MEDIA:<absolute path>` on its own line — one for the month view, one
per week view if asked. Get the path from `job.py path <job_dir> month-png`.
If the first send doesn't render, retry as a standalone message with only
the `MEDIA:` line, then a smaller resized PNG, then a regenerated one —
**never conclude "I can't send the file" on first failure**; only after 2-3
variations ask whether the user's client has received media from this agent
before, then fall back to the path.

### Week numbering

Weeks are Monday–Sunday. 第一週 is the first week whose Monday falls within
the target month (a short leading stub — e.g. Aug 1–2 when the 1st is a
Saturday — gets no file of its own; it's visible in the month grid and was
already covered by the previous month's final week). The final week may
spill into the next month the same way, so two adjacent months' folders
share one boundary week file by design — expected, not a bug.

### Locations and colors

Two-tier model, implemented in `generate_calendar.py`:

1. **`LOC_CLASS`** — the calendar owner's habitual locations, mapped to
   color letters a–d (edit the dict to your team's real site names; the
   matching `--loc-a..d` colors are already in the templates). These keep
   their colors **forever** — "顏色會讓我習慣".
2. **`SPARE_LETTERS`** — any location not in `LOC_CLASS` gets the next free
   letter e–h (粉/黃/紫/紅, the vivid palette, defined in both templates'
   `:root`) in first-seen order. More than 8 locations total: add a
   `--loc-i` CSS pair in both templates and the letter here.

A day whose events sit at more than one location renders a chained `A → B`
badge (the templates' `.loc--move` class) — all locations show, none is
silently dropped, and the legend lists every location present in the view.

## Job directory & manifest

```
<job_dir>/                 -- 預設 ~/mein-agent-storage/cal-out/<目標年月>/<時間戳>-<前綴>
  manifest.json            -- the record: every artifact's id, path, sha256, verify result
  events.json              -- copy of the exact events the views were built from
  26年8月.html              -- month view
  26年8月-第一週.html … 
  26年8月.png …             -- only if png was requested
  .tmp/                    -- scratch for atomic writes; safe to delete
```

One job = one rendered month = one folder. `apply-report.json` (the write
path's record) lands next to its plan.json, wherever you put that.

## Common pitfalls

- **`build.py`/`apply_plan.py` exited non-zero or an artifact/op shows
  ✗.** That's the point — something didn't verify. Read the `verify` block
  in `manifest.json` / the op's line in `apply-report.json`, fix, re-run.
  Do **not** report the job as done.
- **CJK font preflight failed (Linux).** `build.py --formats html,png`
  refuses to launch the browser when `fc-list :lang=zh` is empty — the
  PNG's Chinese would bake into tofu boxes silently. `sudo apt install -y
  fonts-noto-cjk` and re-run, or `--allow-missing-font` to force (the PNGs
  are then marked unverified).
- **Don't conflate `scripts/icloud/` with the sibling `icloud-calendar`
  skill.** Same CalDAV backend, different CLI shapes (this skill:
  positional args + `.credentials` env-style file; that skill: flag-based +
  JSON creds). If the user or a memory entry has ruled `icloud-calendar`
  out, do not import from it or copy its flags — stay inside this skill's
  `scripts/`. Treat that routing ruling as load-bearing: default to this
  skill for every 行事曆 request unless the user names `icloud-calendar`.
- **iCloud on some Linux kernels** may fail CalDAV calls with connection
  errors even though `curl` works — see "Known quirks" in
  `references/apple-calendar-setup.md` before debugging blind.
- **No reply within ~60 min to a format choice → pick the safer default**
  (HTML only, no PNG) and keep going, saying which default you picked.

## Files in this skill

```
calendar-manager-py/
├── SKILL.md
├── README.md               -- plain-language guide for the human calendar owner
├── assets/
│   ├── 模板_月曆.html       -- month view template (edit this, not generated output)
│   ├── 模板_週曆.html       -- week view template
│   ├── plan.schema.json    -- the LLM→Python write-path contract
│   └── hermes-mcp-config.example.yaml
├── references/
│   ├── orchestration.md    -- why the middle is Python; manifest/artifact-id reference
│   ├── apple-calendar-setup.md
│   ├── hermes-setup.md
│   └── event-input-formats.md
├── scripts/
│   ├── build.py            -- events → verified month/week HTML(+PNG) + manifest
│   ├── apply_plan.py       -- plan.json → execute + read-back verify (apply/check)
│   ├── validate_plan.py    -- normalize + validate a plan.json
│   ├── generate_calendar.py -- the renderer (multi-location days, spare colors)
│   ├── verify_output.py    -- structural checks: HTML grid/title, PNG header/blank, CJK preflight
│   ├── job.py              -- job dir, atomic writes, Artifact Manifest (list/path/verify CLI)
│   ├── screenshot.js       -- HTML → PNG (system Chrome, falls back to puppeteer cache)
│   ├── package.json
│   └── icloud/             -- iCloud CalDAV backend (plain Python)
│       ├── _common.py          -- shared helpers; TZ constant lives here
│       ├── list_calendars.py / list_events.py / create_event.py / update_event.py / delete_event.py
│       ├── requirements.txt
│       └── .credentials.example -- copy to .credentials and fill in (gitignored)
└── tests/                  -- pytest; run before changing anything under scripts/ or assets/
```

## Editing this skill

If you're changing the package itself — templates, renderer, orchestration —
read `references/orchestration.md` first and run `python3 -m pytest tests/
-q`. The write-path field rules live in `assets/plan.schema.json`; don't
hardcode them elsewhere. The parent skill's docs once drifted from its code
(documented behaviors that were never shipped); `tests/test_docs_consistency.py`
exists so that class of drift fails loudly here.
