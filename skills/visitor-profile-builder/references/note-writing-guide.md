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

## The xlsx and the HTML now carry the same fields

Both formats render the same closed set of 10 fields — see
`field-contract.md`. The HTML card used to carry extra academic sections
(research areas, publications, citation metrics); those were removed in
2026-07 when the record was standardised, and `profile_json_to_html.py` no
longer has code for them.

So there is no longer a "which format drops what" question to reason about.
If a future case genuinely needs an 11th field, that's a deliberate change
to `assets/profile.schema.json` plus both generators plus
`references/xlsx-source-format.md` — not something to bolt onto an
unrelated cell.

## Placeholder discipline

Never write a guessed value into a field you can't verify. Write a literal
half-width `-` instead, which is the one sanctioned "no data" marker — the
same convention the original seed dossiers used. `validate_profile.py`
rejects every other spelling (`不詳（未公開）`, `未知`, `—`, `N/A`, blank,
`null`), because the value of the convention is that anyone can grep a
profile and count exactly how many fields came up empty.

This is the same principle as "state your assumptions explicitly" from
general coding guidelines, applied to biographical data instead of code: an
explicit blank beats a plausible-looking fabrication.
