# Writing the `note` field, and why xlsx/HTML fields diverge

## The `note` field is not decoration

`note` renders as a highlighted callout box in the HTML and a footer row in
the xlsx. It's the one place you tell the reader how much to trust the rest
of the document. Cover, in roughly this order:

1. **What the profile was compiled from** — categories of source, not just
   "the internet" (e.g. "系所官網、實驗室網站與 Google Scholar 等公開資訊").
2. **What's inferred vs. confirmed.** If you derived a fact (a promotion
   year, a job-title transition) from a news article's incidental mention or
   a talk transcript rather than an authoritative record, say so plainly —
   don't let an inference read like a verified fact. Phrasing pattern (fill
   in the specifics for the actual profile):
   > 部分經歷（如各職級確切晉升年份）為依新聞報導與公開演講內容推估，未逐一取得官方人事紀錄佐證，如需精確年份建議逕向{單位}查證。
3. **Photo caveats**, if any photos are attached — non-official source,
   low resolution, not endorsed by the subject or their institution. See
   `photo-sourcing.md`.

Don't write a vague "資料僅供參考" and stop there — that tells the reader
nothing they can act on. The bar: could someone who only reads `note` know
which specific fields to double-check before relying on this document?

## Why the xlsx template is narrower than the HTML card

`profile_json_to_xlsx.py` only fills the fields that exist in the original
"個人信息登記表" layout (name, gender, birth, zodiac, contact, hometown,
education, positions, career, note, photos). `profile_json_to_html.py`
additionally renders `research_areas`, `achievements`, `publications`, and
`metrics` if present in the JSON.

This is intentional, not a gap to "fix" by cramming more sections into the
xlsx. The xlsx format's whole value is that it matches a template the
recipient already recognizes and may re-file/print/forward in a specific
way (e.g. alongside other dossiers in the same format). Academic-style
extras like a publication list or citation counts don't have an obvious
home in that template and would either break its layout or look like an
ad-hoc addition inconsistent with every other dossier using the same
template. The HTML card has no such constraint — it's generated fresh each
time — so richer profiles (e.g. an academic with a Google Scholar record)
can carry more without compromising the xlsx's consistency with its
siblings.

If a future case needs one of these extra fields *in the xlsx too*, that's
a real template change (new labeled section, more rows) — make it
deliberately in `profile_json_to_xlsx.py`, and update
`references/xlsx-source-format.md` to match, rather than silently bolting
data onto an unrelated cell.

## Placeholder discipline

Never write a guessed value into a field you can't verify. Use
`"不詳（未公開）"` for text fields or `null` in the JSON (both scripts
render `null`/missing the same way: `不詳（未公開）` in the xlsx, and the
field is simply omitted from HTML badges/rows rather than shown as
"unknown"). This mirrors how the two original seed dossiers handled gaps —
literal `-` placeholders, never a fabricated guess — and is the same
principle as "state your assumptions explicitly" from general coding
guidelines, applied to biographical data instead of code.
