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
`scripts/` (pulls in `puppeteer-core`). `scripts/html_to_png.js` tries the
system Chrome (puppeteer's `channel: 'chrome'`) first, and if that fails
(e.g. no Chrome/Chromium installed and no root to `apt install`), falls
through to the Chrome Puppeteer itself downloaded via
`npx puppeteer browsers install chrome` (cache under
`~/.cache/puppeteer/chrome/`). So on most setups no manual browser install
is needed beyond running that one `npx` line.

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

   **After PNG verification, send it inline in the chat as a `MEDIA:` line
   on its own** — don't just announce that a file was written. The user
   asked for an image, and the whole point is they can see it without
   ssh-ing into the server. If the first send doesn't render, retry as a
   single-line standalone message, then a smaller resized version, then
   regenerate — see the "Generated PNGs can be shown inline" bug note
   below for the full failure-mode list before giving up.

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

## Common pitfalls — workflow-level mistakes that look like skill bugs

These are not code bugs but workflow-level traps any agent using this
skill is likely to fall into. Each one was hit at least once in real
use. New ones should be appended below; do not silently rewrite past
entries.

- **The "找不到照片" fallback is "純文字版", not "AI generate a face".**
  When the user asks you to source a photo and web search / Bing image
  search returns nothing but stock photos, other people's portraits, or
  university stock imagery that doesn't match the subject, the right
  move is to fall back to the "no photo" placeholder rendered by the
  HTML template (the dashed-border card with the SVG person icon) —
  **NOT** to call `image_generate` with a prompt like "generate a
  realistic portrait of [name], age 50, male, professor" and paste the
  result into the HTML as if it were real. The first one is honest;
  the second one is a fabricated photo of a real person and is the
  exact failure mode this skill's privacy section is built to prevent.
  If `image_generate` is used at all for this skill, it's for design
  mockups of the layout — never for the subject's face. Same rule
  applies when the subject is a public figure; visibility does not
  lower the bar for "verified photo only."
- **60-minute silent = default choice, not "ask again later".** If the
  user doesn't reply within ~60 minutes to an `AskUserQuestion`-style
  choice (e.g. photo candidates, xlsx vs HTML), do NOT block. Pick the
  safer default (usually: no photo, both formats anyway), keep working,
  and tell the user clearly which default you picked so they can
  override later. This matters especially for cron / scheduled tasks
  but applies in interactive sessions too — the user's "I'll reply
  later" is a real signal, not a stalling action.
- **Tag every uncertain field with the exact phrasing this skill ships,
  not your own variant.** A user agent (or a downstream compliance
  reviewer) reading the generated profile should be able to grep for
  `"不詳（未公開）"` / `"null"` / etc. and find every unverified cell in
  one pass. Don't paraphrase to "未知" or "—" or "TBD" or "未提供" —
  pick the canonical phrasing the skill's `assets/profile.example.json`
  uses and stick to it. The phrasing is part of the skill's API
  contract, not a style preference.
- **Never run the user's personal calendar / iCloud tooling from inside
  this skill.** This skill produces HTML + xlsx + PNG only. If the user
  says "and also add this to my iCloud," that's a sibling skill
  (`calendar-manager` for `test-ceo-calendar`-style backends,
  `icloud-calendar` otherwise) — `delegate_task` to it, don't try to
  combine iCloud writes into `scripts/html_to_png.js` or the HTML
  generator. Mixing the two skills in one pipeline silently writes
  the wrong format (see `calendar-manager` SKILL.md "Common pitfalls"
  for the iCloud-CLI-shape mismatch — same trap on the way back).
- **`profile.example.json` must stay fictional.** Before checking in
  any change to `assets/`, confirm that:
  - `profile.example.json` still uses a fully fictional name and no
    real person's facts. A copy-paste of a real dossier into the
    example file is exactly the kind of bug that travels with every
    future redistribution of this skill.
  - The worked example covers every field (so new users see what a
    "fully filled" profile looks like, including the unverified fields
    filled with `"不詳（未公開）"` — this is *teaching* them the
    phrasing convention).
  - The reference photos in `assets/` (if any) are clearly labeled as
    stock / placeholder, never real.

## Bugs found and fixed — watch for their class

- `scripts/html_to_png.js` used to launch puppeteer with
  `channel: 'chrome'`, which only works when the OS has Chrome/Chromium
  installed (macOS, or a Linux box where `apt install chromium` was
  possible). On a headless / container Linux install without root, every
  call failed with an opaque `Could not find Chrome` error and the user
  had to figure out a workaround themselves. **Fixed**: the script now
  falls through to Puppeteer's own downloaded Chrome at
  `~/.cache/puppeteer/chrome/linux-<rev>/chrome-linux64/chrome`. The
  one-liner that puts a Chrome there is
  `npx puppeteer browsers install chrome` — no root needed. The
  fallback also passes `--no-sandbox` because container environments
  often lack the setuid sandbox setup that puppeteer expects. This is
  the same fix that lives in the sibling `calendar-manager` skill's
  `scripts/screenshot.js` — if you ever refactor one, mirror the change
  to the other; they're the same code shape with different default
  viewports. Don't remove the fallback even if you only ever test on
  macOS — the container-Linux case is exactly the one that fails
  silently.
- **Generated PNGs can be shown inline in the chat with `MEDIA:` markup
  — don't assume they're unreadable.** When the user asks for a PNG,
  the natural end of the workflow is *showing them the image*, not just
  writing it to disk. On platforms that support it (Hermes' WeChat
  surface, Telegram, Discord with image attachments, etc.), embedding
  `MEDIA:<absolute path>` on its own line in the response renders the
  file as a native chat attachment. A first attempt at this that fails
  to render does NOT mean the platform is incapable — it often just
  means the agent assumed the wrong root cause (e.g. "the PNG is too
  big," "the platform doesn't support images," "I have no upload tool")
  and stopped trying. The right move on a first miss is to retry as a
  short standalone message with the `MEDIA:` line and *nothing else* —
  long surrounding prose / tables / multiple `MEDIA:` blocks in one
  message have been observed to suppress the inline render on some
  surfaces, even when a single `MEDIA:` line on its own would have
  worked. If it still doesn't render after that, ask the user to
  confirm their client is the same one that's successfully received
  other media (e.g. calendar PNGs) before declaring the path broken.
  Don't fall back to "I can't upload to chat" — that's almost never
  true, and it strands the user with a file path they can't act on.
- **The first failure is rarely the real cause.** When an inline
  attachment fails to render, the failure mode that *did* work in the
  end is usually some small variation of the original send (different
  size, single line, fewer surrounding tokens), not a wholly new
  delivery mechanism. Before recommending the user switch clients,
  install a server, or scp the file themselves, try at least 2-3 cheap
  variations on the original delivery: (a) single line, no surrounding
  text, (b) the smaller resized version, (c) a regenerated PNG with a
  different aspect ratio. One of those almost always lands.
