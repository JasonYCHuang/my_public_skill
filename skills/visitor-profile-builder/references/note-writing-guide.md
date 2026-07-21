# Writing the `note` field

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

## Placeholder discipline

An explicit blank beats a plausible-looking fabrication — the same principle
as "state your assumptions explicitly", applied to biographical data instead
of code. Never write a guessed value into a field you can't verify; the `-`
convention and what the validator rejects are in `field-contract.md`.
