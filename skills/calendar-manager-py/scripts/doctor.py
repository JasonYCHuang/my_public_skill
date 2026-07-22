#!/usr/bin/env python3
"""
Environment preflight — the README's install prose, as checks with fixes.

    python3 doctor.py [--backend icloud|google|none] [--png] [--json]

Instead of a model reading installation instructions and inferring what's
missing, run this: every prerequisite is probed and every ✗ line carries the
exact command that fixes it. Exit 0 = everything the requested workflow
needs is present.

--backend icloud (default) also checks the CalDAV deps and credentials;
--backend google/none skips them (Google access lives in the agent's own
connector, which Python can't probe). --png adds the Node/Chrome/CJK-font
checks needed only for image output.
"""
import argparse
import importlib.util
import json
import os
import shutil
import subprocess
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

from verify_output import cjk_font_check  # noqa: E402


def _probe(name, ok, detail, fix=""):
    return {"name": name, "ok": bool(ok), "detail": detail, "fix": fix}


def _has_module(mod):
    return importlib.util.find_spec(mod) is not None


def _check_python():
    v = sys.version_info
    return _probe("python", v >= (3, 9), f"Python {v.major}.{v.minor}.{v.micro}",
                  "需要 Python 3.9+")


def _check_module(mod, why, required, pip_name=None):
    ok = _has_module(mod)
    return _probe(f"py:{mod}", ok or not required,
                  ("已安裝" if ok else f"未安裝（{why}）") ,
                  "" if ok else f"pip install {pip_name or mod}")


def _check_credentials():
    creds = os.path.join(_HERE, "icloud", ".credentials")
    if os.path.exists(creds):
        return _probe("icloud:credentials", True, f"{creds}")
    if os.environ.get("ICLOUD_USERNAME") and os.environ.get("ICLOUD_APP_PASSWORD"):
        return _probe("icloud:credentials", True, "由環境變數提供")
    return _probe(
        "icloud:credentials", False, "找不到憑證",
        f"cp {os.path.join(_HERE, 'icloud', '.credentials.example')} {creds} "
        "並填入 Apple ID 與 App 專用密碼（appleid.apple.com 產生）")


def _check_node():
    node = shutil.which("node")
    if not node:
        return _probe("node", False, "找不到 node", "安裝 Node.js（PNG 輸出才需要）")
    try:
        v = subprocess.run([node, "--version"], capture_output=True, text=True,
                           timeout=10).stdout.strip()
    except Exception:  # noqa: BLE001
        v = "?"
    return _probe("node", True, f"{v}（{node}）")


def _check_puppeteer():
    ok = os.path.isdir(os.path.join(_HERE, "node_modules", "puppeteer-core"))
    return _probe("puppeteer-core", ok, "已安裝" if ok else "scripts/node_modules 缺 puppeteer-core",
                  "" if ok else f"cd {_HERE} && npm install")


def _check_chrome():
    """Mirror screenshot.js's search order: system Chrome, then the
    puppeteer download cache."""
    system = [
        "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
        shutil.which("google-chrome"), shutil.which("google-chrome-stable"),
        shutil.which("chromium"), shutil.which("chromium-browser"),
    ]
    for p in system:
        if p and os.path.exists(p):
            return _probe("chrome", True, f"系統 Chrome：{p}")
    cache = os.environ.get("PUPPETEER_CACHE_DIR",
                           os.path.expanduser("~/.cache/puppeteer"))
    chrome_dir = os.path.join(cache, "chrome")
    if os.path.isdir(chrome_dir) and os.listdir(chrome_dir):
        return _probe("chrome", True, f"puppeteer 快取：{chrome_dir}")
    return _probe("chrome", False, "找不到系統 Chrome 或 puppeteer 快取",
                  "npx puppeteer browsers install chrome")


def _check_cjk_font():
    res = cjk_font_check()
    return _probe("cjk-font", res["ok"], res["detail"],
                  "" if res["ok"] else "sudo apt install -y fonts-noto-cjk")


def run_checks(backend="icloud", png=False):
    checks = [_check_python(),
              _check_module("jsonschema", "plan 的 schema 驗證會被略過", required=False)]
    if backend == "icloud":
        checks.append(_check_module("caldav", "iCloud 後端無法運作", required=True))
        checks.append(_check_module("icalendar", "iCloud 後端無法運作", required=True))
        checks.append(_check_credentials())
    if png:
        checks.append(_check_module("PIL", "PNG 空白檢查會被略過", required=False,
                                    pip_name="Pillow"))
        checks.append(_check_node())
        checks.append(_check_puppeteer())
        checks.append(_check_chrome())
        checks.append(_check_cjk_font())
    return checks


def main():
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--backend", default="icloud", choices=["icloud", "google", "none"])
    ap.add_argument("--png", action="store_true", help="連 PNG 輸出的需求一起檢查")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    checks = run_checks(backend=args.backend, png=args.png)
    ok = all(c["ok"] for c in checks)
    if args.json:
        print(json.dumps({"schema": "calendar-manager-py/doctor-result@1",
                          "ok": ok, "checks": checks},
                         ensure_ascii=False, indent=2))
    else:
        for c in checks:
            mark = "✓" if c["ok"] else "✗"
            line = f"{mark} {c['name']:<18} {c['detail']}"
            print(line)
            if not c["ok"] and c["fix"]:
                print(f"    修復：{c['fix']}")
        print("環境就緒。" if ok else "有缺項——照上面的修復指令處理後重跑。")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
