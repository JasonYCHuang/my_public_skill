# Sourcing a non-official photo

**Default to trying** — for this skill's normal use case (a visitor,
official, or academic dossier), a photo is expected and useful for visual
identification, so attempt to find and attach one for every profile without
waiting to be asked. Fall back to the placeholder icon ("無官方照片") only
when a reasonable search (see §1) turns up nothing you can confidently
identify as the actual person — don't attach a low-confidence or
possibly-wrong photo just to avoid the placeholder. If the user asked you
*not* to include a photo, respect that instead.

## 1. Find candidates

Search for the person's name + their institution/department page, lab page,
Google Scholar profile, conference presenter page, or news coverage. Faculty
directory pages and Google Scholar profile photos tend to be the most
reliably "them" (as opposed to a random news photo where identification is
harder to confirm) — prefer those when available.

## 2. Fetch the actual image file — use `scripts/fetch_image.py`

The download and its checks are mechanical, so they're a script rather than a
recipe you assemble:

```bash
python3 scripts/fetch_image.py <直接圖片URL> -o photo.jpg --referer <你找到圖的頁面>
```

What it handles for you:

- **The 403 workaround.** Many institutional sites (`.edu.tw` in particular)
  block a bare download with a 403 bot-challenge page (an Imperva `TS0...`
  cookie challenge) even though the page loads fine in a browser. The script
  always sends a browser User-Agent, and `--referer` adds the Referer header
  that gets past it. Pass `--referer` pointing at the page you found the image
  on; try without it first if you like, add it on a 403 or empty body.
- **"Is it actually an image?"** A 403/redirect saves an HTML error page under
  a `.jpg` name — the script sniffs the real magic bytes and fails loudly if
  what came back isn't a PNG/JPEG/GIF/WebP, instead of letting a broken image
  surface later in the card.
- **Truncation + size.** With Pillow present it decodes the file (catching a
  partial download) and prints the pixel dimensions, flagging a low-res image.

Google Scholar profile photos follow a predictable direct URL once you have
the profile's `user=` ID from its citations page — feed it to the same script:
```
https://scholar.googleusercontent.com/citations?view_op=view_photo&user=<ID>&citpid=1
```

The script confirms you got a real, whole image. **You still look at it** (the
Read tool renders images) to confirm it's a recognizable photo of the *right
person*, not a blank avatar or unrelated graphic — that judgment stays yours.

## 3. Expect low resolution

Faculty directory thumbnails are frequently tiny (in one real case: 65×84px,
a 2011-era casual outdoor snapshot). Google Scholar photos are usually
better (in the same case: 100×128px, a proper studio-style headshot) but
still far from print quality. This is normal for "not official" sourcing —
say so explicitly in the profile's `note` field and in each photo's
`caption`; don't let a low-res image pass as if it were a proper ID photo.

## 4. Ask the user before finalizing — don't pick alone

If you found more than one plausible candidate, or the only candidate looks
informal/low-quality, **ask the user which to use** (or whether to use both)
rather than silently choosing. Photo formality/appropriateness is a judgment
call the user may weigh differently than you would — in the session this
skill was extracted from, the user's actual answer was "use both," which
this skill's scripts support directly (`profile.json`'s `photos` array takes
0–2 entries, both render side by side).

## 5. Wire it into profile.json

```json
"photos": [
  {
    "path": "/tmp/scholar_photo.jpg",
    "caption": "Google Scholar\n個人頁面",
    "source_url": "https://scholar.googleusercontent.com/citations?view_op=view_photo&user=XXXX&citpid=1"
  }
]
```
`caption` is short text shown under the thumbnail in the HTML card (a `\n`
line break is fine). `source_url` should also be duplicated into the
top-level `sources` array so it shows up in the footer's source list, e.g.:
```json
{"title": "照片來源：Google Scholar 個人頁面大頭照", "url": "https://scholar.googleusercontent.com/..."}
```
Then mention in `note` that photos are non-official / low-resolution — see
`note-writing-guide.md`.
