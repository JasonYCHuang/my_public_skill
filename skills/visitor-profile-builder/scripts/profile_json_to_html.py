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
  --note-bg:#fdf6e8;
  --note-border:#e8c874;
}
*{box-sizing:border-box;}
body{
  margin:0;
  font-family:"PingFang TC","Microsoft JhengHei","Noto Sans TC",-apple-system,system-ui,sans-serif;
  background:var(--page-bg);
  color:var(--ink);
  padding:40px 16px;
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
  align-items:flex-start;
  justify-content:space-between;
  gap:24px;
  padding:32px 36px 24px;
  border-bottom:1px solid var(--border);
  position:relative;
}
.updated-tag{
  position:absolute;
  top:14px;
  right:20px;
  font-size:0.72rem;
  color:var(--ink-faint);
}
.identity h1{
  margin:0 0 4px;
  font-size:1.7rem;
  font-weight:700;
  letter-spacing:0.04em;
}
.identity .eng-name{
  margin:0 0 6px;
  font-size:0.85rem;
  color:var(--ink-faint);
  font-weight:500;
}
.identity .subtitle{
  margin:0 0 14px;
  font-size:0.95rem;
  color:var(--accent);
  font-weight:600;
  line-height:1.5;
}
.badge-row{display:flex;flex-wrap:wrap;gap:8px;}
.badge{
  display:inline-flex;align-items:center;gap:4px;
  background:var(--accent-soft);color:var(--accent);
  border-radius:999px;padding:4px 12px;font-size:0.8rem;font-weight:600;white-space:nowrap;
}
.badge .k{color:var(--ink-faint);font-weight:500;}
.photo-placeholder{
  flex:0 0 auto;width:104px;height:132px;border-radius:10px;
  border:1.5px dashed #c7cedb;background:#f8f9fb;
  display:flex;flex-direction:column;align-items:center;justify-content:center;gap:6px;
  color:var(--ink-faint);
}
.photo-placeholder svg{width:34px;height:34px;opacity:0.55;}
.photo-placeholder span{font-size:0.68rem;text-align:center;line-height:1.3;}
.photo-gallery{flex:0 0 auto;display:flex;gap:10px;}
.photo-card{width:96px;display:flex;flex-direction:column;align-items:center;gap:5px;}
.photo-card img{
  width:96px;height:120px;object-fit:cover;border-radius:10px;
  border:1px solid var(--border);background:#f8f9fb;box-shadow:0 1px 2px rgba(20,30,45,0.08);
}
.photo-card span{font-size:0.62rem;color:var(--ink-faint);text-align:center;line-height:1.3;}

.section{padding:22px 36px;}
.section + .section{border-top:1px solid var(--border);}
.section-title{margin:0 0 14px;font-size:0.95rem;font-weight:700;color:var(--ink);display:flex;align-items:center;gap:8px;}
.section-title::before{content:"";width:4px;height:14px;border-radius:2px;background:var(--accent);display:inline-block;}

dl.info-grid{margin:0;display:grid;grid-template-columns:repeat(2,1fr);gap:14px 24px;}
.info-item dt{font-size:0.75rem;color:var(--ink-faint);margin-bottom:2px;}
.info-item dd{margin:0;font-size:0.95rem;font-weight:600;}

ul.position-list{margin:0;padding:0;list-style:none;display:flex;flex-direction:column;gap:8px;}
ul.position-list li{position:relative;padding-left:16px;font-size:0.92rem;line-height:1.5;}
ul.position-list li::before{content:"";position:absolute;left:0;top:0.55em;width:6px;height:6px;border-radius:50%;background:var(--accent);}
ul.position-list li:first-child{font-weight:700;}

table.data-table{width:100%;border-collapse:collapse;font-size:0.88rem;}
table.data-table th{background:var(--table-head);color:var(--ink-soft);font-weight:600;text-align:left;padding:9px 12px;border-bottom:1px solid var(--border);white-space:nowrap;}
table.data-table td{padding:9px 12px;border-bottom:1px solid var(--border);vertical-align:top;word-break:break-word;}
table.data-table tbody tr:nth-child(even){background:var(--table-alt);}
table.data-table tbody tr:last-child td{border-bottom:none;}
td.col-date{white-space:nowrap;color:var(--ink-soft);width:110px;}
td.col-num{white-space:nowrap;color:var(--ink-soft);text-align:right;width:90px;}
td.empty-row{text-align:center;color:var(--ink-faint);font-style:italic;padding:16px;}

.pill-wrap{display:flex;flex-wrap:wrap;gap:8px;}
.pill{background:var(--table-head);border:1px solid var(--border);color:var(--ink-soft);border-radius:999px;padding:5px 14px;font-size:0.85rem;}

.stat-grid{display:grid;grid-template-columns:repeat(3,1fr);gap:12px;}
.stat-tile{background:var(--table-head);border-radius:10px;padding:14px 8px;text-align:center;}
.stat-tile .num{font-size:1.4rem;font-weight:700;color:var(--accent);}
.stat-tile .lbl{font-size:0.72rem;color:var(--ink-faint);margin-top:2px;}

.note-callout{margin:0 36px 24px;background:var(--note-bg);border-left:3px solid var(--note-border);border-radius:6px;padding:12px 16px;font-size:0.85rem;color:#6b5a25;line-height:1.6;}

.card-footer{padding:16px 36px;border-top:1px solid var(--border);background:var(--table-head);font-size:0.75rem;color:var(--ink-faint);}
.card-footer .src-title{font-weight:600;color:var(--ink-soft);margin-bottom:6px;}
.card-footer ol{margin:0;padding-left:18px;line-height:1.8;}
.card-footer a{color:var(--accent);text-decoration:none;word-break:break-all;}
.card-footer a:hover{text-decoration:underline;}
"""

PHOTO_ICON = (
    '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">'
    '<circle cx="12" cy="8" r="3.4"/><path d="M4.5 20c1.6-4 4.2-6 7.5-6s5.9 2 7.5 6"/></svg>'
)

PLACEHOLDER_VALUES = {None, "", "-", "－", "—"}


def esc(v):
    return html_escape.escape("" if v is None else str(v)).replace("\n", "<br>")


def is_placeholder(v):
    return v is None or str(v).strip() in PLACEHOLDER_VALUES


def build_photo_block(photos):
    if not photos:
        return f"""
      <div class="photo-placeholder">
        {PHOTO_ICON}
        <span>無官方照片</span>
      </div>"""
    cards = []
    for p in photos:
        with open(p["path"], "rb") as f:
            b64 = base64.b64encode(f.read()).decode()
        mime = mimetypes.guess_type(p["path"])[0] or "image/jpeg"
        cards.append(
            f'<div class="photo-card"><img src="data:{mime};base64,{b64}" '
            f'alt="{esc(p["caption"])}"><span>{esc(p["caption"])}</span></div>'
        )
    return f'\n      <div class="photo-gallery">{"".join(cards)}</div>'


def render(data):
    badges = []
    for key, label in (("gender", "性別"), ("birth", "出生年月"), ("zodiac", "生肖"), ("hometown", "籍貫"), ("contact", "聯繫方式")):
        v = data.get(key)
        if not is_placeholder(v):
            badges.append(f'<span class="badge"><span class="k">{label}</span>{esc(v)}</span>')

    positions = data.get("positions") or []
    subtitle_text = data.get("subtitle") or (positions[0] if positions else "")
    subtitle = f'<p class="subtitle">{esc(subtitle_text)}</p>' if subtitle_text else ""
    eng_name = f'<p class="eng-name">{esc(data["name_en"])}</p>' if data.get("name_en") else ""

    sections = []

    if positions:
        items = "".join(f"<li>{esc(p)}</li>" for p in positions)
        sections.append(f'\n    <div class="section">\n      <h2 class="section-title">現任職位</h2>\n      <ul class="position-list">{items}</ul>\n    </div>')

    edu_rows = data.get("education") or []
    if edu_rows:
        edu_body = "".join(
            f'<tr><td>{esc(e.get("school"))}</td><td>{esc(e.get("major"))}</td>'
            f'<td>{esc(e.get("degree_level"))}</td><td>{esc(e.get("degree"))}</td></tr>'
            for e in edu_rows
        )
    else:
        edu_body = '<tr><td class="empty-row" colspan="4">尚無官方公開資料</td></tr>'
    sections.append(f'''
    <div class="section">
      <h2 class="section-title">教育經歷</h2>
      <table class="data-table">
        <thead><tr><th>畢業院校</th><th>專業</th><th>學歷</th><th>學位</th></tr></thead>
        <tbody>{edu_body}</tbody>
      </table>
    </div>''')

    career_rows = data.get("career") or []
    if career_rows:
        career_body = "".join(
            f'<tr><td class="col-date">{esc(c.get("date"))}</td><td>{esc(c.get("org"))}</td><td>{esc(c.get("role"))}</td></tr>'
            for c in career_rows
        )
    else:
        career_body = '<tr><td class="empty-row" colspan="3">尚無官方公開資料</td></tr>'
    sections.append(f'''
    <div class="section">
      <h2 class="section-title">主要履歷</h2>
      <table class="data-table">
        <thead><tr><th>起止年月</th><th>工作單位</th><th>職位</th></tr></thead>
        <tbody>{career_body}</tbody>
      </table>
    </div>''')

    if data.get("research_areas"):
        pills = "".join(f'<span class="pill">{esc(a)}</span>' for a in data["research_areas"])
        sections.append(f'\n    <div class="section">\n      <h2 class="section-title">研究領域</h2>\n      <div class="pill-wrap">{pills}</div>\n    </div>')

    if data.get("metrics"):
        tiles = "".join(f'<div class="stat-tile"><div class="num">{esc(m.get("num"))}</div><div class="lbl">{esc(m.get("label"))}</div></div>' for m in data["metrics"])
        sections.append(f'\n    <div class="section">\n      <h2 class="section-title">學術／量化指標</h2>\n      <div class="stat-grid">{tiles}</div>\n    </div>')

    if data.get("publications"):
        pub_body = "".join(
            f'<tr><td class="col-date">{esc(p.get("year"))}</td><td>{esc(p.get("title"))}</td><td class="col-num">{esc(p.get("citations"))}</td></tr>'
            for p in data["publications"]
        )
        sections.append(f'''
    <div class="section">
      <h2 class="section-title">代表著作／案例</h2>
      <table class="data-table">
        <thead><tr><th>年份</th><th>標題</th><th>備註</th></tr></thead>
        <tbody>{pub_body}</tbody>
      </table>
    </div>''')

    if data.get("achievements"):
        items = "".join(f"<li>{esc(a)}</li>" for a in data["achievements"])
        sections.append(f'\n    <div class="section">\n      <h2 class="section-title">榮譽獎項與成就</h2>\n      <ul class="position-list">{items}</ul>\n    </div>')

    note_html = f'<div class="note-callout">※ {esc(data["note"])}</div>' if data.get("note") else ""

    sources = data.get("sources") or []
    src_items = "".join(
        f'<li><a href="{html_escape.escape(s["url"])}" target="_blank" rel="noopener">{esc(s["title"])}</a></li>'
        for s in sources if s.get("url")
    )
    src_block = f'<div class="src-title">資料來源</div>\n      <ol>{src_items}</ol>' if src_items else ""

    photo_block = build_photo_block(data.get("photos") or [])
    timestamp = data.get("timestamp") or ""

    return f"""<title>{esc(data.get("name", ""))}　個人檔案</title>
<style>
{CSS}
</style>
<div class="page">
  <div class="card">
    <div class="card-header">
      <span class="updated-tag">資料彙整時間：{esc(timestamp)}</span>
      <div class="identity">
        <h1>{esc(data.get("name", ""))}</h1>
        {eng_name}
        {subtitle}
        <div class="badge-row">{"".join(badges)}</div>
      </div>{photo_block}
    </div>
{"".join(sections)}
    {note_html}
    <div class="card-footer">
      {src_block}
    </div>
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

    html_out = render(data)
    os.makedirs(os.path.dirname(os.path.abspath(args.output)), exist_ok=True)
    with open(args.output, "w", encoding="utf-8") as f:
        f.write(html_out)
    print(f"wrote {args.output}")


if __name__ == "__main__":
    main()
