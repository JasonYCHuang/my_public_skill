---
name: visitor-profile-builder-py
description: Build a "個人信息登記表" (personal dossier) as a styled HTML profile card, a matching xlsx, and a PNG of the card — from an existing source xlsx or from public web research on a named person. This is the Python-orchestrated variant of visitor-profile-builder: one command (scripts/build.py) validates, generates, verifies, atomically writes, and records every output in an Artifact Manifest, so an output can't be reported as done unless it exists and passed verification. Use when the user hands you a xlsx in this format, or names a person (visitor, professor, official) and asks for a "個人檔案" / "個人信息表", or asks for the html/xlsx/png version of one.
compatibility: Agent-agnostic Agent Skills package (agentskills.io format). Needs web search + page fetch (for the research workflow), a shell running Python 3 with openpyxl + jsonschema (Pillow for xlsx photo embedding and the PNG blank-check), Node.js + Chrome for the PNG card render (a default output), and ideally an AskUserQuestion-style tool for photo choices. Install steps are in README.md.
metadata:
  built-for: "002_訪客人員背景調查"
  origin: "Claude Code"
  variant: "python-orchestrated (build.py + Artifact Manifest)"
---

# Visitor Profile Builder（Python 編排版）

Turns facts about a person — either already sitting in a source xlsx, or
found via web research — into three deliverables (a styled **HTML
card**, a **"個人信息登記表" xlsx**, and a **PNG** of the card).

This variant produces the **same files** as `visitor-profile-builder`, but
the middle of the workflow — generate, verify, place, record — is one
deterministic Python command instead of steps you follow by hand. The design
principle, from the training deck this skill was built alongside:

> **策略保持柔性，執行保持剛性。** LLM 做軟的認知判斷，Python 做硬的執行與
> 驗證，交界處讓 LLM 產生、Python 驗證。

**Your job (the soft half):** understand the request, research and verify the
person, and fill in `profile.json`. **`scripts/build.py`'s job (the hard
half):** validate that JSON, render every format, verify each output is real
and not silently broken, write it atomically, and record it in a manifest —
so you never have to *claim* a file exists, you can read that it does. Full
rationale and the manifest/artifact-id reference: `references/orchestration.md`.

All outputs come from one shared `profile.json` (schema in
`assets/profile.schema.json`, worked example in `assets/profile.example.json`,
rendered to `assets/profile.example.html`). **Never hand-edit the HTML or
xlsx** — edit the JSON and re-run `build.py`.

## Handling personal data responsibly

The *code* here is safe to publish; the *output* is not.

- **Never save a real `profile.json`/HTML/xlsx/PNG inside this skill folder.**
  This package gets copied and redistributed as a unit. `build.py` writes into
  a **job directory you point it at** (default
  `~/mein-agent-storage/vpb-out/<年月>/<時間戳>-<姓名>`), never inside the skill. `assets/profile.example.json` must stay
  fictional.
- **Aggregation is itself privacy-relevant**, even when every individual fact
  is public. Keep the discipline (verified facts only, explicit "-" for gaps,
  sources listed, non-official photos labeled) even for public figures.
- **This skill profiles people in their public/professional capacity.** If a
  request looks like a dossier on a private individual, check the purpose with
  the user first.
- Don't share generated output more widely than the requester intended.

If Python can't find its packages on a system Python, make a one-off venv
rather than fighting `pip`:
```bash
python3 -m venv /tmp/vpb-venv && /tmp/vpb-venv/bin/pip install openpyxl Pillow jsonschema
```
then call scripts as `/tmp/vpb-venv/bin/python3 scripts/....py`.

## The one command

```bash
python3 scripts/build.py <profile.json> [--job-dir <dir>] [--formats html,xlsx,png]
```

It runs, in order: **validate → (create job dir) → render → verify → atomic
write → hash into manifest**, for every requested format, and exits non-zero
if anything failed. `--formats` defaults to `html,xlsx,png` — all three are
standard deliverables. The png render needs Node + Chrome; only drop it
(`--formats html,xlsx`) when the environment can't provide them and the user
agrees to go without the image. Add `--json` to get a
machine-readable result summary on stdout.

After it runs, **read the result — don't re-announce paths from memory.** The
manifest is the source of truth for what exists:
```bash
python3 scripts/job.py list  <job_dir>            # every artifact + whether it verified
python3 scripts/job.py path  <job_dir> card-png   # the real absolute path of one artifact
```
Artifact ids are stable: `profile-json`, `card-html`, `registry-xlsx`,
`card-png`. Refer to outputs by id, not by a path you reconstructed.

## Two entry points

### A. You already have a source xlsx

The user hands you a file already in the "個人信息登記表" layout (see
`references/xlsx-source-format.md` for the full cell/merge spec). `build.py`
takes the xlsx directly — extraction happens in-process, so it's one command:

```bash
python3 scripts/build.py "來源.xlsx"
```

The extracted `sources` holds a `原始來源檔案` placeholder with an empty url
(dropped from the footer automatically); if you can add the real source URLs,
extract to an editable JSON first with
`python3 scripts/xlsx_to_profile_json.py "來源.xlsx" -o profile.json`, edit,
then `build.py profile.json`.

### B. Only a name (+ maybe org/dept) — build from public web research

The more common case, and the part that stays **your** judgment:

1. **Search to confirm identity first** — the person plus their
   organization/title. Common names collide; nothing downstream should trust
   an identity you haven't pinned down.
2. **Compile facts into `profile.json` by hand** (there's no scraper — read
   `assets/profile.schema.json` for the field list). This is the soft,
   cognitive half; the mechanical rules around it are enforced by code, so you
   only have to hold the judgment calls:
   - **Any field you can't verify: a literal half-width `-`, never a guess.**
     (The validator rejects every other spelling; the closed 10-field set,
     required keys, and count limits are all enforced too — see
     `references/field-contract.md`. You don't need to police these by hand.)
   - If a fact is *inferred* rather than stated outright, say so in `note` —
     see `references/note-writing-guide.md`.
   - **List every source URL you pulled a fact from** in `sources`.
   - You do **not** set `timestamp` (build.py defaults it to today) or copy a
     photo's `source_url` into `sources` (build.py merges it). Leave those to
     the tool. To check a JSON without building:
     `python3 scripts/validate_profile.py profile.json` — and read its
     warnings, they flag an empty `note` or unverifiable sources.
3. **Find and attach a photo — by default, not only when asked.** Finding
   candidates and judging they're the right person stays your call (read
   `references/photo-sourcing.md`), but the download-and-check is a script:
   ```bash
   python3 scripts/fetch_image.py <圖片URL> -o photo.jpg --referer <你找到圖的頁面>
   ```
   It sends the browser UA/Referer that gets past `.edu.tw` 403s, then
   verifies the bytes are a real image (not a saved HTML error page), decodes
   it to catch a truncated download, and reports the pixel size. **Look at the
   result to confirm it's the right person**, then fill it into `photos` with
   its `source_url`. Skip only if the user says not to, or nothing
   confidently-identified turns up.
4. **Build** — html, xlsx, and png are all produced by default:
   ```bash
   python3 scripts/build.py profile.json
   ```
   `build.py` runs the CJK-font preflight and the structural verify for you.
   For a PNG, still **look at it** (the Read tool renders images) as a final
   human check, then **send it inline as a `MEDIA:` line on its own** — see
   Known issues for the retry ladder.

## Job directory & manifest

```
<job_dir>/
  manifest.json          -- the record: every artifact's id, path, sha256, verify result
  profile.json           -- copy of the exact profile these outputs were built from
  姓名 個人檔案.html
  姓名 個人信息表.xlsx
  姓名 個人檔案.png       -- unless png was explicitly dropped via --formats
  .tmp/                  -- scratch for atomic writes; safe to delete
```

One job = one person = one folder. Keep this out of the skill folder and out
of any `reference/` folder holding untouched source xlsx.

## Common pitfalls

- **`build.py` exited non-zero / an artifact shows ✗.** That's the point —
  something didn't verify. Read the `verify` block in `manifest.json` (or the
  ✗ line on stderr) for which check failed, fix, re-run. Do **not** report the
  job as done.
- **CJK font preflight failed (Linux).** `build.py` (png is in the default
  formats) refuses to
  render before a browser launch when `fc-list :lang=zh` is empty, because the
  PNG's Chinese would bake into tofu boxes silently. Install the font
  (`sudo apt install -y fonts-noto-cjk`) and re-run, or pass
  `--allow-missing-font` to force it (the png is then marked unverified).
- **No confidently-matched photo → use the template's built-in "無官方照片"
  placeholder, never `image_generate` a face.** A fabricated portrait of a
  real person is exactly what the privacy section exists to prevent.
- **No reply within ~60 min to a photo/format choice → pick the safer
  default** (no photo, all formats) and keep going, saying which default you
  picked.
- **This skill only produces html/xlsx/png — never wire iCloud/calendar writes
  into it.** Route "also add this to my calendar" to the sibling
  `calendar-manager` skill.

## Known issues

- **The PNG is phone-shaped by design** (430 CSS px wide, 3x, tables stacked
  into per-row cards) because it gets read in a chat app on a phone. Opening
  the `.html` in a desktop browser still gets the wide table layout.
- `html_to_png.js` needs Chrome/Chromium. If it can't find one, run
  `npx puppeteer browsers install chrome` (no root) and retry. `build.py`
  reports this as a `card-png` failure rather than pretending success.
- A PNG can be shown inline via a `MEDIA:<absolute path>` line on its own
  (Hermes/WeChat, Telegram, Discord, etc.). If it doesn't render first try,
  retry as a standalone message with only the `MEDIA:` line (no surrounding
  prose/tables), then a smaller resized PNG, then a regenerated PNG, before
  concluding the path is broken. Get the path from
  `python3 scripts/job.py path <job_dir> card-png`.

## Editing this skill

If you're changing the package itself — touching `assets/`, the HTML template,
`html_to_png.js`, or the orchestration in `scripts/build.py` — read
`references/maintaining.md` and `references/orchestration.md` first, and run
`python3 -m pytest tests/ -q`. The field contract lives in
`assets/profile.schema.json`; don't hardcode rules in Python
(`references/field-contract.md`).
