---
name: visitor-profile-builder
description: Build a "個人信息登記表" (personal dossier) as a styled HTML profile card, a matching xlsx, and/or a PNG of the card — either from an existing source xlsx or from public web research on a named person. Use when the user hands you a xlsx in this format, or names a person (visitor, professor, official) and asks for a "個人檔案" / "個人信息表", or asks for the html/xlsx/png version of one.
compatibility: Agent-agnostic Agent Skills package (agentskills.io format). Needs web search + page fetch (for the research workflow), a shell running Python 3 with openpyxl + jsonschema (Pillow only for xlsx photo embedding), Node.js + Chrome only for PNG output, and ideally an AskUserQuestion-style tool for photo choices. Install steps are in README.md.
metadata:
  built-for: "002_訪客人員背景調查"
  origin: "Claude Code"
---

# Visitor Profile Builder

Turns facts about a person — either already sitting in a source xlsx, or
found via web research — into up to three deliverables:

1. A **styled HTML profile card** (self-contained single file) — the
   primary, easy-to-read deliverable.
2. A **"個人信息登記表" xlsx** matching the original template's merged-cell
   layout — when the recipient wants the spreadsheet format back.
3. A **PNG** of the card (full-page screenshot) — only when the user wants
   an image to paste into a chat or slide deck.

All three come from one shared intermediate format, `profile.json` (schema
in `assets/profile.schema.json`, worked example in
`assets/profile.example.json`). **Never hand-edit the HTML or xlsx** — edit
the JSON and regenerate, so the outputs can't drift apart.

## Handling personal data responsibly

The *code* here is safe to publish; the *output* is not.

- **Never save a real `profile.json`/HTML/xlsx/PNG inside this skill
  folder.** This package gets copied and redistributed as a unit — anything
  real placed inside travels with every future copy. Generated output goes
  in the consuming project's own working folders.
  `assets/profile.example.json` must stay fictional.
- **Aggregation is itself privacy-relevant**, even when every individual
  fact is public. Keep the discipline the skill was built with (verified
  facts only, explicit "not disclosed" for gaps, sources listed, non-official
  photos labeled) even for public figures.
- **This skill profiles people in their public/professional capacity** — a
  visitor, official, or academic. If a request looks like a dossier on a
  private individual, check the purpose with the user first.
- Don't share generated output more widely than the requester intended (no
  public URLs, no public issues/chats).

If a Python script fails on an externally-managed system Python, make a
one-off venv rather than fighting `pip`:
```bash
python3 -m venv /tmp/vpb-venv && /tmp/vpb-venv/bin/pip install openpyxl Pillow jsonschema
```
then call scripts as `/tmp/vpb-venv/bin/python3 scripts/....py`.

## Two entry points

### A. You already have a source xlsx

The user hands you a file already in the "個人信息登記表" layout — see
`references/xlsx-source-format.md` for the full cell/merge spec if you need
to adapt the scripts to a layout variant.

```bash
python3 scripts/xlsx_to_profile_json.py "來源.xlsx" -o profile.json
python3 scripts/profile_json_to_html.py profile.json -o "模板_html/姓名 個人檔案.html"
```

`xlsx_to_profile_json.py` fills `sources` with a `原始來源檔案` placeholder —
replace it with something meaningful, or leave it (an empty `url` is dropped
from the rendered source list automatically).

### B. Only a name (+ maybe org/dept) — build from public web research

The more common case. Steps:

1. **Search to confirm identity first** — the person plus their
   organization/title. Common names collide, and nothing downstream should
   trust an identity you haven't pinned down.
2. **Compile facts into `profile.json` by hand** (there's no scraper — read
   `assets/profile.schema.json` for the field list). Rules that matter:
   - **Any field you can't verify: a literal half-width `-`, never a
     guess.** Every other spelling — `不詳（未公開）`, `未知`, `—`, `N/A`,
     blank, `null` — is rejected by the validator, because the point is that
     empty cells stay greppable.
   - If a fact is *inferred* from a news article or talk transcript rather
     than stated outright, say so in `note` — see
     `references/note-writing-guide.md` for phrasing patterns.
   - **`sources` is not optional.** List every URL you actually pulled a
     fact from; a reviewer may need to verify any single line.
   - **The record is a closed set of 10 fields** — 姓名／性別／出生年月／
     生肖／聯繫方式／籍貫／教育經歷／現任職位（≤3）／主要經歷（≤10）／照片
     （≤2）. All ten are required, and any key outside the schema is an
     error. `timestamp`/`note`/`sources` are header/footer metadata, not
     fields. Full table and rationale: `references/field-contract.md`.
   - Both generators validate before writing anything and abort on error,
     so read their output. To check a JSON without generating:
     ```bash
     python3 scripts/validate_profile.py profile.json --target xlsx
     ```
3. **Find and attach a photo — by default, not only when asked.** Read
   `references/photo-sourcing.md` before doing this; it covers finding
   candidates, the 403 workaround for institutional sites, and asking the
   user which photo to use. Skip only if the user says not to, or nothing
   confidently-identified turns up.
4. **Generate outputs** — html and xlsx by default; png only if the user
   wants an image file:
   ```bash
   python3 scripts/profile_json_to_html.py profile.json -o "模板_html/姓名 個人檔案.html"
   python3 scripts/profile_json_to_xlsx.py  profile.json -o "模板_xlsx/姓名 個人信息表.xlsx"
   node   scripts/html_to_png.js            "模板_html/姓名 個人檔案.html"   # optional
   ```
   After generating a PNG, **look at it** (the Read tool renders images)
   before saying it's done — screenshots fail silently (clipped section,
   unloaded font, broken image path). Then **send it inline as a `MEDIA:`
   line on its own**, don't just announce that a file was written; see
   Known issues for the retry ladder if it doesn't render.

## Folder conventions used in this project

```
reference/     -- raw source xlsx handed to you (entry point A), untouched
模板_html/     -- generated HTML cards (and PNGs, next to their source html)
模板_xlsx/     -- generated "個人信息登記表" xlsx files
```

Some projects use one dated folder per batch (e.g. `202607/`) instead —
either is fine. Two things hold regardless: keep generated output out of
`reference/`, and keep each PNG next to the HTML it came from.

## Common pitfalls

- **No confidently-matched photo → use the template's built-in "無官方照片"
  placeholder, never `image_generate` a face.** A fabricated portrait of a
  real person is exactly what the privacy section exists to prevent.
  `image_generate` is fine for layout mockups only.
- **No reply within ~60 min to a photo/format choice → pick the safer
  default** (no photo, both formats) and keep going, saying which default
  you picked. Don't block indefinitely.
- **This skill only produces html/xlsx/png — never wire iCloud/calendar
  writes into it.** Route "also add this to my calendar" to the sibling
  `calendar-manager` skill.
- **Before committing changes under `assets/`**, confirm
  `profile.example.json` is still fully fictional, still covers every field
  (including the `"-"` ones, as a teaching example), and that any
  sample photos are labeled stock/placeholder.

## Known issues

- `html_to_png.js` needs Chrome/Chromium. On headless/container Linux
  without one it falls back to Puppeteer's own downloaded Chrome
  (`npx puppeteer browsers install chrome`, no root) with `--no-sandbox`.
  **Keep this fallback when editing the script** — it fails silently if
  removed. The same fix lives in `calendar-manager/scripts/screenshot.js`;
  mirror changes to both.
- A PNG can be shown inline via a `MEDIA:<absolute path>` line on its own
  (Hermes/WeChat, Telegram, Discord, etc.). If it doesn't render first try,
  that's not proof the platform can't do it — retry as a standalone message
  with only the `MEDIA:` line (no surrounding prose/tables), then a smaller
  resized PNG, then a regenerated PNG with a different aspect ratio, before
  concluding the path is broken.
