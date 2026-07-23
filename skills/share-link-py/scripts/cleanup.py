#!/usr/bin/env python3
"""cleanup.py — 刪掉過期的分享（share.py 只記錄期限，這裡真正動手）。

由 systemd user timer 每小時跑一次（install_systemd.py 安裝）。
也可手動：

    python3 scripts/cleanup.py [--root DIR] [--dry-run] [--json]

規則：
  * meta/<token>.json 的 expires_at 已過 → 刪 pub/<token>/ 與 meta 檔
  * expires_at 為 null → 永久保留
  * pub/ 裡沒有對應 meta 的孤兒資料夾，建立超過 1 天 → 刪
    （share.py 中途死掉的殘骸；1 天緩衝避免誤殺正在寫的）
  * robots.txt 永遠不動
"""
import argparse
import json
import os
import shutil
import sys
import time

DEFAULT_ROOT = os.path.expanduser("~/mein-agent-storage/share-link")
ORPHAN_GRACE = 86400  # 孤兒資料夾的緩衝秒數


def cleanup(root, dry_run=False, now=None):
    now = now or time.time()
    pub = os.path.join(root, "pub")
    meta_dir = os.path.join(root, "meta")
    removed, kept, errors = [], [], []

    metas = {}
    if os.path.isdir(meta_dir):
        for fn in os.listdir(meta_dir):
            if not fn.endswith(".json"):
                continue
            path = os.path.join(meta_dir, fn)
            try:
                with open(path, encoding="utf-8") as f:
                    metas[fn[:-5]] = json.load(f)
            except (json.JSONDecodeError, OSError) as e:
                errors.append(f"meta 讀不了 {fn}: {e}")

    def _rm(token, reason):
        d = os.path.join(pub, token)
        m = os.path.join(meta_dir, f"{token}.json")
        if not dry_run:
            shutil.rmtree(d, ignore_errors=True)
            try:
                os.remove(m)
            except FileNotFoundError:
                pass
        removed.append({"token": token, "reason": reason})

    for token, meta in metas.items():
        exp = meta.get("expires_at")
        if exp is not None and exp <= now:
            _rm(token, "expired")
        else:
            kept.append(token)

    if os.path.isdir(pub):
        for fn in os.listdir(pub):
            d = os.path.join(pub, fn)
            if fn == "robots.txt" or not os.path.isdir(d) or fn in metas:
                continue
            try:
                age = now - os.stat(d).st_mtime
            except OSError:
                continue
            if age > ORPHAN_GRACE:
                _rm(fn, "orphan")

    return {"removed": removed, "kept": len(kept), "errors": errors,
            "dry_run": dry_run}


def main():
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--root", default=DEFAULT_ROOT,
                    help=f"儲存根目錄（預設 {DEFAULT_ROOT}）")
    ap.add_argument("--dry-run", action="store_true", help="只列不刪")
    ap.add_argument("--json", action="store_true", help="機器可讀輸出")
    args = ap.parse_args()

    res = cleanup(os.path.abspath(os.path.expanduser(args.root)),
                  dry_run=args.dry_run)
    if args.json:
        print(json.dumps(res, ensure_ascii=False))
    else:
        verb = "將刪除" if args.dry_run else "已刪除"
        for r in res["removed"]:
            print(f"{verb} {r['token']}（{r['reason']}）")
        print(f"{verb} {len(res['removed'])} 個、保留 {res['kept']} 個分享")
        for e in res["errors"]:
            print(f"警告：{e}", file=sys.stderr)
    sys.exit(1 if res["errors"] else 0)


if __name__ == "__main__":
    main()
