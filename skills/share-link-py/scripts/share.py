#!/usr/bin/env python3
"""share.py — 把檔案發佈成「微信可點的 URL」。

為什麼存在：微信傳 html 附件無法直接開、傳圖常遇 CDN upload HTTP 500。
與其跟附件通道搏鬥，不如把檔案放上自架 web 目錄，傳一條 URL，
對方點開（或複製到手機 Chrome）就能看。

用法：
    python3 scripts/share.py <檔案|vpb_job_dir> [更多檔案...] \
        [--ttl 7d] [--base-url https://share.example.com] [--root DIR] [--json]

行為（剛性）：
  1. 產生不可猜 token（secrets.token_urlsafe(16)，~128-bit）
  2. 檔案複製進 <root>/pub/<token>/，檔名轉成 ASCII 安全名
     （html → index.html，於是 URL 就是 <base>/<token>/；png → card.png）
  3. 過期資訊寫進 <root>/meta/<token>.json（webroot 之外，永不被 serve）
  4. 印出每個檔案的 URL；--json 給機器可讀摘要
  5. 首次使用時在 pub/ 寫 robots.txt（全站 Disallow）

輸入若是含 manifest.json 的資料夾（visitor-profile-builder-py 的 job dir），
自動改抓其中已驗證的 card-html / card-png。

過期由 cleanup.py（systemd timer 每小時）實際刪檔；本腳本只記錄期限。
"""
import argparse
import hashlib
import json
import os
import re
import secrets
import shutil
import sys
import time
import unicodedata

DEFAULT_ROOT = os.path.expanduser("~/mein-agent-storage/share-link")
DEFAULT_TTL = "7d"
CONFIG_PATH = os.path.expanduser("~/.config/share-link/config.json")
ROBOTS_TXT = "User-agent: *\nDisallow: /\n"

# vpb manifest 裡我們願意分享的 artifact（profile.json 是原始資料，不分享）
VPB_SHAREABLE = ("card-html", "card-png")


def _die(msg):
    print(f"share.py: {msg}", file=sys.stderr)
    sys.exit(2)


def load_config():
    """~/.config/share-link/config.json → dict（沒有就空 dict）。"""
    try:
        with open(CONFIG_PATH, encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return {}
    except (json.JSONDecodeError, OSError) as e:
        _die(f"設定檔壞了（{CONFIG_PATH}）：{e}")


def parse_ttl(text):
    """'7d'/'24h'/'30m' → 秒；'never'/'0' → None（不過期）。"""
    t = str(text).strip().lower()
    if t in ("never", "0", "none"):
        return None
    m = re.fullmatch(r"(\d+)([dhm])", t)
    if not m:
        raise ValueError(f"看不懂的 ttl：{text!r}（可用 7d / 24h / 30m / never）")
    n = int(m.group(1))
    return n * {"d": 86400, "h": 3600, "m": 60}[m.group(2)]


def ascii_slug(name, fallback):
    """檔名 → ASCII 安全名（微信聊天視窗裡的 URL 不能斷在非 ASCII 上）。"""
    stem, ext = os.path.splitext(name)
    s = unicodedata.normalize("NFKD", stem).encode("ascii", "ignore").decode()
    s = re.sub(r"[^A-Za-z0-9._-]+", "-", s).strip("-").lower()
    return (s or fallback) + ext.lower()


def resolve_inputs(paths):
    """展開輸入：vpb job dir → 其 manifest 裡已驗證的 card-html/card-png。"""
    files = []
    for p in paths:
        p = os.path.abspath(os.path.expanduser(p))
        manifest = os.path.join(p, "manifest.json")
        if os.path.isdir(p):
            if not os.path.isfile(manifest):
                _die(f"{p} 是資料夾但沒有 manifest.json —— 請直接指定檔案")
            with open(manifest, encoding="utf-8") as f:
                arts = json.load(f).get("artifacts", {})
            picked = []
            for aid in VPB_SHAREABLE:
                a = arts.get(aid)
                if not a or not a.get("path"):
                    continue
                if a.get("verified") is False:
                    continue  # 未通過驗證的產物不上網
                fp = a["path"]
                if not os.path.isabs(fp):
                    fp = os.path.join(p, fp)
                if os.path.isfile(fp):
                    picked.append(fp)
            if not picked:
                _die(f"{p} 的 manifest 裡沒有可分享的已驗證 artifact"
                     f"（找了 {', '.join(VPB_SHAREABLE)}）")
            files.extend(picked)
        elif os.path.isfile(p):
            files.append(p)
        else:
            _die(f"找不到：{p}")
    return files


def plan_names(files):
    """來源檔 → 分享目錄內的 ASCII 檔名。

    第一個 html 命名為 index.html（URL 變成 <base>/<token>/，最短最好點）；
    第一個 png 命名為 card.png；重名自動加 -2、-3。
    """
    names, used = [], set()
    html_done = png_done = False
    for i, fp in enumerate(files):
        base = os.path.basename(fp)
        ext = os.path.splitext(base)[1].lower()
        if ext in (".html", ".htm") and not html_done:
            name, html_done = "index.html", True
        elif ext == ".png" and not png_done:
            name, png_done = "card.png", True
        else:
            name = ascii_slug(base, f"file-{i + 1}")
        stem, e2 = os.path.splitext(name)
        k = 2
        while name in used:
            name = f"{stem}-{k}{e2}"
            k += 1
        used.add(name)
        names.append(name)
    return names


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def share(files, root, base_url, ttl_seconds):
    pub = os.path.join(root, "pub")
    meta_dir = os.path.join(root, "meta")
    tmp = os.path.join(root, ".tmp")
    for d in (pub, meta_dir, tmp):
        os.makedirs(d, exist_ok=True)

    robots = os.path.join(pub, "robots.txt")
    if not os.path.exists(robots):
        with open(robots, "w", encoding="utf-8") as f:
            f.write(ROBOTS_TXT)

    token = secrets.token_urlsafe(16)
    names = plan_names(files)

    # 先在 .tmp 组好，再整包 rename 進 pub —— 對方永遠看不到半成品
    stage = os.path.join(tmp, token)
    os.makedirs(stage)
    entries = []
    for fp, name in zip(files, names):
        dst = os.path.join(stage, name)
        shutil.copyfile(fp, dst)
        entries.append({
            "name": name,
            "original": os.path.basename(fp),
            "sha256": sha256(dst),
            "bytes": os.path.getsize(dst),
        })
    os.rename(stage, os.path.join(pub, token))

    now = int(time.time())
    meta = {
        "token": token,
        "created_at": now,
        "created_iso": time.strftime("%Y-%m-%dT%H:%M:%S%z", time.localtime(now)),
        "expires_at": (now + ttl_seconds) if ttl_seconds else None,
        "files": entries,
    }
    meta_tmp = os.path.join(meta_dir, f".{token}.tmp")
    with open(meta_tmp, "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)
    os.rename(meta_tmp, os.path.join(meta_dir, f"{token}.json"))

    base = base_url.rstrip("/")
    urls = []
    for e in entries:
        u = f"{base}/{token}/" if e["name"] == "index.html" \
            else f"{base}/{token}/{e['name']}"
        urls.append({"name": e["name"], "original": e["original"], "url": u})
    return meta, urls


def main():
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("paths", nargs="+", metavar="檔案|vpb_job_dir",
                    help="要分享的檔案；或 vpb job dir（自動抓已驗證 html/png）")
    ap.add_argument("--ttl", default=None,
                    help=f"多久後過期（7d/24h/30m/never；預設 {DEFAULT_TTL}）")
    ap.add_argument("--base-url", default=None,
                    help="對外網址，如 https://share.example.com"
                         "（也可設在 ~/.config/share-link/config.json 的 base_url）")
    ap.add_argument("--root", default=None,
                    help=f"儲存根目錄（預設 {DEFAULT_ROOT}；pub/ 是 webroot）")
    ap.add_argument("--json", action="store_true", help="stdout 輸出機器可讀摘要")
    args = ap.parse_args()

    cfg = load_config()
    base_url = args.base_url or cfg.get("base_url") or os.environ.get("SHARE_LINK_BASE_URL")
    if not base_url:
        _die("沒有 base_url —— 用 --base-url、或寫進 ~/.config/share-link/config.json、"
             "或設環境變數 SHARE_LINK_BASE_URL。沒有對外網址，分享出去的連結沒人打得開。")
    root = os.path.abspath(os.path.expanduser(args.root or cfg.get("root") or DEFAULT_ROOT))
    try:
        ttl_seconds = parse_ttl(args.ttl or cfg.get("ttl") or DEFAULT_TTL)
    except ValueError as e:
        _die(str(e))

    files = resolve_inputs(args.paths)
    meta, urls = share(files, root, base_url, ttl_seconds)

    if args.json:
        print(json.dumps({"ok": True, "token": meta["token"],
                          "expires_at": meta["expires_at"], "urls": urls},
                         ensure_ascii=False))
    else:
        exp = ("永不過期（僅靠隨機網址保護）" if meta["expires_at"] is None else
               time.strftime("%Y-%m-%d %H:%M", time.localtime(meta["expires_at"])) + " 過期")
        print(f"已發佈（{exp}）：")
        for u in urls:
            print(f"  {u['original']}  →  {u['url']}")


if __name__ == "__main__":
    main()
