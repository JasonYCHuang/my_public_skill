#!/usr/bin/env python3
"""
Render a profile.json (see assets/profile.schema.json) into the standalone
card-style HTML profile used throughout this skill.

Usage:
    python3 profile_json_to_html.py <profile.json> -o <output.html>

Photos: each entry in profile["photos"] must have a local "path" that
exists on disk (download it first, e.g. with curl -A "<browser UA>" -e
"<referer>" -- many .edu.tw / institutional sites 403 a bare curl without
a browser User-Agent and Referer header). This script inlines each photo
as a base64 data: URI, so the output HTML is a single self-contained file.
"""
import argparse
import base64
import html as html_escape
import json
import mimetypes
import os

from validate_profile import validate_or_exit

CSS = """
:root{
  --page-bg:#eef1f5;
  --card-bg:#ffffff;
  --ink:#1c2530;
  --ink-soft:#5b6572;
  --ink-faint:#8993a1;
  --accent:#2f4a6b;
  --accent-soft:#eef2f7;
  --border:#e3e7ed;
  --table-head:#f4f6f9;
  --table-alt:#fafbfc;
}
*{box-sizing:border-box;}
body{
  margin:0;
  /* "Noto Sans CJK TC" is the family name Debian/Ubuntu's fonts-noto-cjk
     package actually registers — "Noto Sans TC" is the webfont/variable
     name and does NOT match it. Without this entry, a headless Linux box
     falls through to sans-serif, which fontconfig resolves to DejaVu Sans,
     which has no CJK glyphs: every Chinese character bakes into the PNG as
     a tofu box. Silent, and only visible by looking at the image. */
  font-family:"PingFang TC","Microsoft JhengHei","Noto Sans CJK TC","Noto Sans TC",-apple-system,system-ui,sans-serif;
  background:var(--page-bg);
  color:var(--ink);
  padding:20px 14px;
}
.page{max-width:760px;margin:0 auto;}
.card{
  background:var(--card-bg);
  border-radius:16px;
  box-shadow:0 1px 3px rgba(20,30,45,0.06),0 12px 32px -16px rgba(20,30,45,0.18);
  overflow:hidden;
}
.card-header{
  display:flex;
  align-items:stretch;
  justify-content:space-between;
  gap:20px;
  padding:16px 28px 14px;
  border-bottom:1px solid var(--border);
}
.identity{flex:1 1 auto;min-width:0;}
/* 現任職位 sits in the header so the photo has the height of the identity
   block AND the position list to fill. */
.header-positions{margin-top:12px;}
.header-positions .section-title{margin-bottom:6px;}
/* Timestamp sits in the same right-hand column as the photo. It used to be
   absolutely positioned, which silently overlapped the photo box once the
   header padding was tightened. */
.header-right{
  flex:0 0 auto;
  display:flex;flex-direction:column;align-items:flex-end;gap:5px;
  align-self:stretch;
}
.updated-tag{
  font-size:0.7rem;
  color:var(--ink-faint);
  white-space:nowrap;
}
.identity h1{
  margin:0 0 2px;
  font-size:1.45rem;
  font-weight:700;
  letter-spacing:0.04em;
}
.identity .eng-name{
  margin:0 0 4px;
  font-size:0.8rem;
  color:var(--ink-faint);
  font-weight:500;
}
.badge-row{display:flex;flex-wrap:wrap;gap:6px;}
.badge{
  display:inline-flex;align-items:center;gap:4px;
  background:var(--accent-soft);color:var(--accent);
  border-radius:999px;padding:3px 10px;font-size:0.78rem;font-weight:600;white-space:nowrap;
}
.badge .k{color:var(--ink-faint);font-weight:500;}
/* Now that 現任職位 shares the header, the photo column is tall enough for a
   much bigger photo — 145px wide instead of the old 88px, reaching well
   into the position list.
   It is NOT stretched to the column's full height: object-fit:cover on a
   ~1:2.4 box crops a face down to a strip. 3:4 is the ratio dossier photos
   actually come in, so the box keeps it and simply tops out. */
.photo-placeholder,.photo-card img{aspect-ratio:3/4;}
.photo-placeholder{
  flex:0 0 auto;width:145px;border-radius:10px;
  border:1.5px dashed #c7cedb;background:#f8f9fb;
  display:flex;flex-direction:column;align-items:center;justify-content:center;gap:6px;
  color:var(--ink-faint);
}
.photo-placeholder svg{width:34px;height:34px;opacity:0.55;}
.photo-placeholder span{font-size:0.7rem;text-align:center;line-height:1.3;}
.photo-gallery{flex:0 0 auto;display:flex;gap:8px;}
.photo-card{width:145px;display:flex;flex-direction:column;gap:4px;}
.photo-card img{
  width:145px;object-fit:cover;border-radius:10px;
  border:1px solid var(--border);background:#f8f9fb;box-shadow:0 1px 2px rgba(20,30,45,0.08);
}
.photo-card span{font-size:0.62rem;color:var(--ink-faint);text-align:center;line-height:1.3;}

.section{padding:13px 28px;}
.section + .section{border-top:1px solid var(--border);}
.section-title{margin:0 0 8px;font-size:0.9rem;font-weight:700;color:var(--ink);display:flex;align-items:center;gap:8px;}
.section-title::before{content:"";width:4px;height:13px;border-radius:2px;background:var(--accent);display:inline-block;}

ul.position-list{margin:0;padding:0;list-style:none;display:flex;flex-direction:column;gap:5px;}
ul.position-list li{position:relative;padding-left:15px;font-size:0.88rem;line-height:1.45;}
ul.position-list li::before{content:"";position:absolute;left:0;top:0.5em;width:5px;height:5px;border-radius:50%;background:var(--accent);}
ul.position-list li:first-child{font-weight:700;}

table.data-table{width:100%;border-collapse:collapse;font-size:0.84rem;}
table.data-table th{background:var(--table-head);color:var(--ink-soft);font-weight:600;text-align:left;padding:5px 10px;border-bottom:1px solid var(--border);white-space:nowrap;}
table.data-table td{padding:5px 10px;border-bottom:1px solid var(--border);vertical-align:top;word-break:break-word;line-height:1.4;}
table.data-table tbody tr:nth-child(even){background:var(--table-alt);}
table.data-table tbody tr:last-child td{border-bottom:none;}
td.col-date{white-space:nowrap;color:var(--ink-soft);width:100px;}
/* 專業/學歷/學位 are short values; letting them shrink-to-fit stops the
   school column from hogging width and wrapping every row onto two lines. */
th.col-narrow,td.col-narrow{white-space:nowrap;width:1%;}


.card-footer{padding:11px 28px;border-top:1px solid var(--border);background:var(--table-head);font-size:0.72rem;color:var(--ink-faint);}
.card-footer .src-title{font-weight:600;color:var(--ink-soft);margin-bottom:4px;}
.card-footer ol{margin:0;padding-left:18px;line-height:1.55;}
.card-footer a{color:var(--accent);text-decoration:none;word-break:break-all;}
.card-footer a:hover{text-decoration:underline;}

/* ---- Phone layout ----------------------------------------------------
   The usual way this document is read is as a PNG in a chat app, on a
   phone. html_to_png.js therefore renders at a phone-width viewport, which
   trips this query; opening the .html on a desktop still gets the wide
   layout above. Two things matter at this width:

   1. Type must be big enough to read without pinch-zoom. The PNG is pixels,
      so a reader cannot reflow it — whatever size we bake in is final.
   2. Multi-column tables do not survive. Each row becomes a stacked block
      with its column name as a small label, so no cell is squeezed to a
      two-character column.                                              */
@media (max-width:560px){
  html{font-size:18px;}
  body{padding:0;background:var(--card-bg);}
  .card{border-radius:0;box-shadow:none;}
  .card-header{gap:14px;padding:14px 18px;}
  /* "資料彙整時間：" is wider than the date it labels; at this width the
     label costs a line for no information the reader lacks. */
  .ts-label{display:none;}
  /* Narrower than the desktop 145px — at 430px total, the identity column
     still needs room for the position list beside it. Height follows from
     the 3:4 aspect-ratio above. */
  .photo-placeholder,.photo-card,.photo-card img{width:123px;}
  .photo-placeholder svg{width:28px;height:28px;}
  .identity h1{font-size:1.5rem;}

  /* One photo sits beside the name fine. Two eat half the width and squeeze
     the name column to a shred, so stack them under the identity block
     instead. :has() lets the layout react to the photo count without the
     generator having to emit a different class per case. */
  .card-header:has(.photo-card + .photo-card){flex-direction:column;align-items:stretch;}
  .card-header:has(.photo-card + .photo-card) .header-right{
    flex-direction:column;align-items:stretch;width:100%;gap:8px;
  }
  .card-header:has(.photo-card + .photo-card) .photo-gallery{justify-content:flex-start;}
  .card-header:has(.photo-card + .photo-card) .photo-card,
  .card-header:has(.photo-card + .photo-card) .photo-card img{width:154px;}
  .badge-row{gap:5px;}
  /* Long values (an email) may wrap inside the pill, but the label must not
     — "聯繫方式" split across two lines reads as two separate words. */
  .badge{font-size:0.8rem;padding:4px 11px;white-space:normal;align-items:flex-start;}
  .badge .k{white-space:nowrap;}
  .section{padding:14px 18px;}
  .card-footer{padding:14px 18px;font-size:0.76rem;}

  /* Stacked rows: the <thead> labels move onto each cell via data-label. */
  table.data-table thead{display:none;}
  table.data-table,table.data-table tbody,table.data-table tr,table.data-table td{display:block;width:auto;}
  table.data-table tr{
    padding:9px 0;border-bottom:1px solid var(--border);
    display:flex;flex-direction:column;
  }
  table.data-table tbody tr:nth-child(even){background:transparent;}
  table.data-table tbody tr:last-child{border-bottom:none;padding-bottom:0;}
  table.data-table td{
    padding:1px 0;border:none;white-space:normal;width:auto;
    font-size:0.88rem;line-height:1.45;
    display:flex;gap:8px;align-items:baseline;
  }
  table.data-table td::before{
    content:attr(data-label);
    flex:0 0 4.2em;
    font-size:0.76rem;color:var(--ink-faint);
  }
  /* The row's headline value — school / employer — reads as a title
     instead of another labelled line, and is pulled to the top of the row
     even where it isn't the first column (主要履歷 leads with the date). */
  table.data-table td.cell-lead{display:block;order:-1;font-weight:700;font-size:0.95rem;margin-bottom:3px;}
  table.data-table td.cell-lead::before{content:none;}
  table.data-table td.col-date{color:var(--ink-soft);}
}
"""

PHOTO_ICON = (
    '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">'
    '<circle cx="12" cy="8" r="3.4"/><path d="M4.5 20c1.6-4 4.2-6 7.5-6s5.9 2 7.5 6"/></svg>'
)

# The one sanctioned "no data" marker; validate_profile.py rejects every
# other spelling, so anything falsy here can only be a missing key.
EMPTY = "-"

def esc(v):
    return html_escape.escape("" if v is None else str(v)).replace("\n", "<br>")


def _placeholder_block():
    return f"""
      <div class="photo-placeholder">
        {PHOTO_ICON}
        <span>無官方照片</span>
      </div>"""


def build_photo_block(photos):
    if not photos:
        return _placeholder_block()
    cards = []
    for p in photos:
        # Match profile_json_to_xlsx.py: a photo path that no longer exists
        # warns and is skipped, rather than aborting the whole render. The two
        # generators run back-to-back on one profile.json, so diverging here
        # meant the xlsx built fine and the html died on the same input.
        if not os.path.exists(p["path"]):
            print(f'警告：找不到照片檔案 {p["path"]}，略過')
            continue
        with open(p["path"], "rb") as f:
            b64 = base64.b64encode(f.read()).decode()
        mime = mimetypes.guess_type(p["path"])[0] or "image/jpeg"
        cards.append(
            f'<div class="photo-card"><img src="data:{mime};base64,{b64}" '
            f'alt="{esc(p["caption"])}"><span>{esc(p["caption"])}</span></div>'
        )
    if not cards:
        return _placeholder_block()
    return f'\n      <div class="photo-gallery">{"".join(cards)}</div>'


def render(data):
    # Fields [2]-[6] always render, "-" included: the record is a fixed form,
    # so a reader must be able to see that a field was considered and left
    # blank, not wonder whether it was omitted.
    badges = []
    # Contract order, fields [2]..[6]. 聯繫方式 is last by design: it holds
    # the one value that runs long (an email), so trailing it lets that pill
    # take a line of its own instead of shoving 籍貫 onto the next row.
    # The xlsx keeps the old cell positions on purpose — see
    # references/field-contract.md.
    for key, label in (("gender", "性別"), ("birth", "出生年月"), ("zodiac", "生肖"), ("hometown", "籍貫"), ("contact", "聯繫方式")):
        v = data.get(key) or EMPTY
        badges.append(f'<span class="badge"><span class="k">{label}</span>{esc(v)}</span>')

    eng_name = f'<p class="eng-name">{esc(data["name_en"])}</p>' if data.get("name_en") else ""

    # 現任職位 lives inside the header rather than in its own section, so the
    # photo column has something to stand next to and can be sized to the
    # full height of the two together. It also removes a duplication: the
    # header used to repeat positions[0] as a subtitle directly above this
    # very list.
    positions = data.get("positions") or []
    items = "".join(f"<li>{esc(p)}</li>" for p in positions) or f"<li>{EMPTY}</li>"
    position_block = (
        f'<div class="header-positions">'
        f'<h2 class="section-title">現任職位</h2>'
        f'<ul class="position-list">{items}</ul></div>'
    )

    sections = []

    edu_rows = data.get("education") or []
    if edu_rows:
        edu_body = "".join(
            f'<tr><td class="cell-lead" data-label="畢業院校">{esc(e.get("school"))}</td>'
            f'<td data-label="專業">{esc(e.get("major"))}</td>'
            f'<td class="col-narrow" data-label="學歷">{esc(e.get("degree_level"))}</td>'
            f'<td data-label="學位">{esc(e.get("degree"))}</td></tr>'
            for e in edu_rows
        )
    else:
        edu_body = (
            f'<tr><td class="cell-lead" data-label="畢業院校">{EMPTY}</td><td data-label="專業">{EMPTY}</td>'
            f'<td data-label="學歷">{EMPTY}</td><td data-label="學位">{EMPTY}</td></tr>'
        )
    sections.append(f'''
    <div class="section">
      <h2 class="section-title">教育經歷</h2>
      <table class="data-table">
        <thead><tr><th>畢業院校</th><th>專業</th><th class="col-narrow">學歷</th><th>學位</th></tr></thead>
        <tbody>{edu_body}</tbody>
      </table>
    </div>''')

    career_rows = data.get("career") or []
    if career_rows:
        career_body = "".join(
            f'<tr><td class="col-date" data-label="起止年月">{esc(c.get("date"))}</td>'
            f'<td class="cell-lead" data-label="工作單位">{esc(c.get("org"))}</td>'
            f'<td data-label="職位">{esc(c.get("role"))}</td></tr>'
            for c in career_rows
        )
    else:
        career_body = (
            f'<tr><td class="col-date" data-label="起止年月">{EMPTY}</td>'
            f'<td class="cell-lead" data-label="工作單位">{EMPTY}</td><td data-label="職位">{EMPTY}</td></tr>'
        )
    sections.append(f'''
    <div class="section">
      <h2 class="section-title">主要履歷</h2>
      <table class="data-table">
        <thead><tr><th>起止年月</th><th>工作單位</th><th>職位</th></tr></thead>
        <tbody>{career_body}</tbody>
      </table>
    </div>''')

    sources = data.get("sources") or []
    src_items = "".join(
        f'<li><a href="{html_escape.escape(s["url"])}" target="_blank" rel="noopener">{esc(s["title"])}</a></li>'
        for s in sources if s.get("url")
    )
    # Entry point A seeds sources with {"title": "原始來源檔案", "url": ""},
    # and url-less entries are dropped from the list — which left the footer
    # as an empty grey bar on every xlsx-derived card. Drop the whole footer
    # when nothing survives the filter.
    src_block = f'<div class="src-title">資料來源</div>\n      <ol>{src_items}</ol>' if src_items else ""
    footer_html = f'\n    <div class="card-footer">\n      {src_block}\n    </div>' if src_block else ""

    photo_block = build_photo_block(data.get("photos") or [])
    timestamp = data.get("timestamp") or ""

    # charset: the file is written UTF-8 and is full of Chinese. Opened from
    # file:// (or forwarded as an attachment) with no declaration, a browser
    # falls back to a locale default and can render the whole card as mojibake.
    # viewport: without it a phone browser assumes a ~980px virtual viewport,
    # so the max-width:560px phone layout below never fires and a colleague
    # opening the forwarded .html on their phone gets the squeezed desktop
    # tables. The PNG path is unaffected either way — html_to_png.js sets the
    # viewport explicitly — but the .html is meant to be opened directly too.
    return f"""<!DOCTYPE html>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{esc(data.get("name", ""))}　個人檔案</title>
<style>
{CSS}
</style>
<div class="page">
  <div class="card">
    <div class="card-header">
      <div class="identity">
        <h1>{esc(data.get("name", ""))}</h1>
        {eng_name}
        <div class="badge-row">{"".join(badges)}</div>
        {position_block}
      </div>
      <div class="header-right">
        <span class="updated-tag"><span class="ts-label">資料彙整時間：</span>{esc(timestamp)}</span>{photo_block}
      </div>
    </div>
{"".join(sections)}
    {footer_html}
  </div>
</div>
"""


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("profile_json", help="輸入 profile.json 路徑")
    ap.add_argument("-o", "--output", required=True, help="輸出 html 路徑")
    args = ap.parse_args()

    with open(args.profile_json, "r", encoding="utf-8") as f:
        data = json.load(f)

    validate_or_exit(data, target="html")

    html_out = render(data)
    os.makedirs(os.path.dirname(os.path.abspath(args.output)), exist_ok=True)
    with open(args.output, "w", encoding="utf-8") as f:
        f.write(html_out)
    print(f"wrote {args.output}")


if __name__ == "__main__":
    main()
