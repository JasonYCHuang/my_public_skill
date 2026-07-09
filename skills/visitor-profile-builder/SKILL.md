---
name: visitor-profile-builder
description: Build a "個人信息登記表" (personal info dossier) as a styled, self-contained HTML profile card, a matching xlsx template, and/or a PNG image of the card, either from an existing source xlsx or from scratch via public web research on a named person (e.g. a visitor, a professor, an official). Use this whenever the user gives you a xlsx in this format and asks to convert/optimize it into HTML, or names a person and asks you to look them up and build a "個人檔案" / "個人信息表", or asks for the html/xlsx/png version(s) of the same profile.
compatibility: Agent-agnostic Agent Skills package (agentskills.io format). Requires the agent to have web search + web page fetch (for the from-scratch research workflow), a shell to run Python 3 scripts (openpyxl required; Pillow required only for embedding photos in the xlsx), Node.js + a system Chrome/Chromium install only if PNG output is needed, and ideally an AskUserQuestion-style tool to let the user pick between photo candidates.
metadata:
  built-for: "002_訪客人員背景調查"
  origin: "Claude Code"
---

# Visitor Profile Builder

Turns facts about a person — either already sitting in a source xlsx, or
found via web research — into two consistent deliverables:

1. A **styled HTML profile card** (self-contained single file, card layout,
   light theme, badges/tables/pills) — the primary, easy-to-read deliverable.
2. A **"個人信息登記表" xlsx** matching the original template's merged-cell
   layout — for when the recipient specifically wants the spreadsheet format
   back, or wants to keep printing/filing it the old way.

3. A **PNG image** of the HTML card (a full-page screenshot) — only when the
   user wants an image file to paste into a chat or slide deck; the HTML is
   the source of truth and the PNG is derived from it, not generated
   independently.

All three are generated from one shared intermediate format, `profile.json`
(see `assets/profile.schema.json`, worked example in
`assets/profile.example.json`), so the outputs never drift apart — you never
hand-edit HTML or xlsx directly, you edit the JSON and regenerate (and the
PNG is a screenshot of the regenerated HTML, so it never drifts either).

## Handling personal data responsibly

This skill's *code* (scripts, templates, schema) is safe to publish and
share — it contains no one's personal data. The *output* it produces is a
different matter, and needs the same care regardless of which agent or
installation is running it:

- **Never commit a real generated `profile.json`, HTML, or xlsx into this
  skill folder itself** (`assets/`, or anywhere under
  `visitor-profile-builder/`). This package gets copied and redistributed
  as a unit — anything real placed inside it travels with every future
  copy. Generated output belongs in the *consuming* project's own working
  folders (e.g. `reference/` / `模板_html/` / `模板_xlsx/`, or a dated
  folder per that project's convention), never inside the skill package.
  `assets/profile.example.json` must stay fictional — see the note at the
  top of that file before changing it.
- **Aggregation is itself a privacy-relevant act**, even when every
  individual fact is already public. A name, an employer, and a photo are
  each unremarkable alone; a single document that combines someone's
  identity, career history, and photo is a dossier, and reads as more
  sensitive than its parts. Don't relax the care this skill was built with
  (verified facts only, explicit "not disclosed" for gaps, sources listed,
  non-official photos labeled as such — see `note-writing-guide.md` and
  `photo-sourcing.md`) just because the subject is a public figure.
- **This skill is for profiling people in their public/professional
  capacity** (a visitor, an official, an academic — the kind of person a
  "個人信息登記表" was already meant to cover), not for compiling dossiers
  on private individuals. If a request looks like the latter, check with
  the user about the purpose before proceeding.
- Treat generated output the same way you'd treat any file with someone's
  personal details in it: don't upload it to a public URL, paste it into a
  public issue/chat, or otherwise share it more widely than the requester
  intended.

## Installing this skill for your agent

- **Claude Code**: copy/symlink this folder to `.claude/skills/visitor-profile-builder/`
  inside the project you're working in.
- **Hermes agent**: copy this folder to `~/.hermes/skills/visitor-profile-builder/`.
- **Other agentskills.io-compatible agents**: check that agent's docs for its
  skill directory convention.

Either way, `scripts/` needs `openpyxl` (`pip install openpyxl`) and, only
if you'll be embedding photos into the xlsx, `Pillow` (`pip install Pillow`).
If your system Python is externally-managed (e.g. Homebrew Python on macOS
refuses a bare `pip install`), make a one-off venv:
```bash
python3 -m venv /tmp/vpb-venv && /tmp/vpb-venv/bin/pip install openpyxl Pillow
```
and call scripts as `/tmp/vpb-venv/bin/python3 scripts/....py`.

Only if you'll be generating **PNG** output: run `npm install` once inside
`scripts/` (pulls in `puppeteer-core`), and make sure a system Chrome or
Chromium is installed — `scripts/html_to_png.js` drives the existing browser
install rather than downloading its own, so no PNG-specific setup is needed
beyond having Chrome present.

## Two entry points

### A. You already have a source xlsx

Use this when the user hands you (or points you at) a file already in the
"個人信息登記表" layout — see `references/xlsx-source-format.md` for the
full reverse-engineered cell/merge spec if you need to adapt the scripts to
a layout variant.

```bash
python3 scripts/xlsx_to_profile_json.py "來源.xlsx" -o profile.json
python3 scripts/profile_json_to_html.py profile.json -o "模板_html/姓名 個人檔案.html"
```
Add a PNG only if asked (see step 4 below for the command).

`xlsx_to_profile_json.py` fills `sources: [{"title": "原始來源檔案", "url": ""}]`
as a placeholder — replace it with something meaningful (or leave it; an
empty `url` is dropped from the rendered HTML's source list automatically)
since there's no web URL for a local file.

### B. Only a name (+ maybe org/dept) — build from public web research

This is the more common case for this project (background research on a
named visitor/official/academic). Steps:

1. **Search the web** for the person + their organization/title to confirm
   identity before pulling any other facts — common names collide, and nothing
   downstream should trust an identity you haven't pinned down first.
2. **Compile facts into a `profile.json`** by hand (there's no scraper —
   read `assets/profile.schema.json` for the field list and
   `assets/profile.example.json` for a fully worked (fictional) example
   covering every field). Rules that matter:
   - **Any field you can't verify: write `"不詳（未公開）"` or `null`, never
     guess.** This mirrors how the two original reference dossiers handled
     missing data — an explicit "not disclosed" beats a plausible-looking
     fabrication.
   - If a fact (e.g. an exact promotion year) is *inferred* from a news
     article or talk transcript rather than stated outright, say so in
     `note` — don't present an inference as a confirmed record. See
     `references/note-writing-guide.md` for phrasing patterns.
   - **`sources` is not optional.** List every URL you actually pulled a
     fact from. This is the same discipline the WebSearch tool enforces on
     its own output — apply it here too since the user (or a compliance
     reviewer) may need to verify any single line in the profile.
   - Extended fields (`research_areas`, `achievements`, `publications`,
     `metrics`) only render in the HTML — the xlsx template has no matching
     section for them, by design (see `references/note-writing-guide.md`
     for why the two formats are allowed to diverge here).
3. **Find and attach a photo — try this by default, not just when asked.**
   See `references/photo-sourcing.md` before doing this. Short version:
   search, download candidates with a browser User-Agent (institutional
   sites often 403 a bare `curl`; when saving to disk, use the project's
   scratchpad directory, not a bare `/tmp` path), then **ask the user which
   photo(s) to use** rather than silently picking one — photo
   quality/formality is a judgment call, not something to decide alone. Only
   skip this step if the user says not to, or no confidently-identified
   candidate turns up.
4. **Generate outputs** — html and xlsx by default; add png only if the user
   wants an image file (see "Handling personal data responsibly" above —
   the same care applies to a PNG as to the html/xlsx it's a screenshot of):
   ```bash
   python3 scripts/profile_json_to_html.py profile.json -o "模板_html/姓名 個人檔案.html"
   python3 scripts/profile_json_to_xlsx.py  profile.json -o "模板_xlsx/姓名 個人信息表.xlsx"
   node   scripts/html_to_png.js            "模板_html/姓名 個人檔案.html"   # optional; writes 姓名 個人檔案.png next to it
   ```
   After generating a PNG, **look at it** (the Read tool renders images)
   before telling the user it's done — screenshot generation is exactly the
   kind of step that can fail silently (a section clipped, a font not
   loaded, an image path broken). Don't just trust that the command exited
   0.

## Folder conventions used in this project

```
reference/     -- raw source xlsx files handed to you (entry point A), untouched
模板_html/     -- generated HTML profile cards (and PNGs, next to their source html)
模板_xlsx/     -- generated "個人信息登記表" xlsx files
```

Some projects instead use one dated folder per batch (e.g. `202607/`) holding
all three formats together rather than splitting by type — either convention
is fine, PNGs just always live next to the HTML they were screenshotted
from.

Keep generated output out of `reference/` — that folder is for inputs you
didn't create. If you're adapting this skill to a project with different
folder names, that's fine; it's a convention, not something the scripts
enforce.

## Files in this skill

```
visitor-profile-builder/
├── SKILL.md                        -- this file: instructions for the agent
├── README.md                       -- plain-language guide for a human colleague
├── assets/
│   ├── profile.schema.json         -- field-by-field spec of profile.json
│   └── profile.example.json        -- fictional worked example covering every field
├── references/
│   ├── xlsx-source-format.md       -- reverse-engineered spec of the source xlsx layout
│   ├── photo-sourcing.md           -- how to find/fetch/vet a non-official photo
│   └── note-writing-guide.md       -- how to phrase caveats, inferences, and the html/xlsx field gap
└── scripts/
    ├── xlsx_to_profile_json.py     -- source xlsx -> profile.json
    ├── profile_json_to_html.py     -- profile.json -> HTML profile card
    ├── profile_json_to_xlsx.py     -- profile.json -> 個人信息登記表 xlsx
    ├── html_to_png.js              -- HTML profile card -> full-page PNG screenshot
    ├── package.json                -- npm install target for html_to_png.js (puppeteer-core)
    └── .gitignore                  -- excludes node_modules/ and generated *.png from git
```
