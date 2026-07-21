# Maintaining this skill

Notes for anyone *editing* the skill package itself. Nothing here is needed
to build a profile — if you're just generating a card, stay in `SKILL.md`.

## Before committing changes under `assets/`

Confirm `profile.example.json` is still fully fictional, still covers every
field (including the `"-"` ones, as a teaching example), and that any sample
photos are labeled stock/placeholder.

`assets/profile.example.html` is **generated, not written.** If you change
the example JSON or the HTML template, regenerate it in the same commit — a
stale sample is worse than none, because it teaches the wrong layout:

```bash
python3 scripts/profile_json_to_html.py assets/profile.example.json -o assets/profile.example.html
```

It is the one HTML file allowed to live in this package, and only because
every value in it is fictional. Real profiles still never go here.

## Don't widen the PNG viewport

The PNG is rendered phone-shaped on purpose (430 CSS px wide, 3x), and the
HTML has a `@media (max-width:560px)` block that stacks the two tables into
per-row cards. The reason: these PNGs are read in a chat app on a phone,
where the image is scaled to screen width — a desktop-width render arrives
as unreadably small text, and a PNG can't be reflowed by the reader.
Widening the viewport in `html_to_png.js` silently undoes this. Opening the
`.html` in a desktop browser still gets the wide table layout.

## Keep the Chrome fallback in `html_to_png.js`

The script needs Chrome/Chromium. On headless/container Linux without one it
falls back to Puppeteer's own downloaded Chrome
(`npx puppeteer browsers install chrome`, no root) with `--no-sandbox`.
**Keep this fallback when editing the script** — it fails silently if
removed. The same fix lives in `calendar-manager/scripts/screenshot.js`;
mirror changes to both.

## Changing the field contract

Edit `assets/profile.schema.json` — don't hardcode rules in Python. An 11th
field is a deliberate change to the schema plus both generators plus
`references/xlsx-source-format.md`. See `field-contract.md`.
