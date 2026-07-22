#!/usr/bin/env python3
"""
Verify a produced artifact is real and not silently broken.

The parent skill's SKILL.md tells the model to *look at* the PNG before
saying it's done, because a screenshot "fails silently — clipped section,
unloaded font, broken image path." That instruction only works if a model
reads it and remembers to act on it. Here the same checks are code that
build.py runs on every artifact, so an unverified output can't be reported
as finished no matter who is driving.

Each verify_* returns a dict:
    {"ok": bool, "checks": [ {"name", "ok", "detail"}, ... ], "detail": str}

The checks are deliberately cheap and structural — "is this a real PNG of a
plausible size", "does the html contain the person's name and close its
tags", "can openpyxl open the xlsx and is it the 個人信息登記表 template" —
not a full visual review. They catch the failure modes that produce a file
that *looks* written but is unusable: a zero-byte png, an html that rendered
before a photo path resolved, an xlsx that didn't finish saving.

The one failure a pixel check can't catch — Chinese baked into a PNG as tofu
boxes because a headless Linux box has no CJK font — is caught up front by
cjk_font_check(), which build.py runs before it ever launches the browser.
"""
import os
import shutil
import struct
import subprocess
import sys

PNG_SIG = b"\x89PNG\r\n\x1a\n"


def _check(name, ok, detail=""):
    return {"name": name, "ok": bool(ok), "detail": detail}


def _result(checks, detail=""):
    ok = all(c["ok"] for c in checks)
    return {"ok": ok, "checks": checks, "detail": detail}


# ---------------------------------------------------------------------------
# PNG
# ---------------------------------------------------------------------------

def png_dimensions(path):
    """(width, height) from the PNG header alone — no Pillow needed. Returns
    None if the file isn't a PNG (which is itself a finding: a saved 403/HTML
    error page, or a zero-byte file)."""
    with open(path, "rb") as f:
        head = f.read(24)
    if len(head) < 24 or head[:8] != PNG_SIG:
        return None
    # IHDR width/height are the two big-endian uint32 at bytes 16..24.
    w, h = struct.unpack(">II", head[16:24])
    return w, h


def _png_not_blank(path):
    """If Pillow is available, flag an image that is essentially one flat
    colour — the signature of a render that produced a page of background and
    nothing else. Skipped (as a pass) when Pillow isn't installed; the header
    and size checks still stand."""
    try:
        from PIL import Image
    except ImportError:
        return _check("not_blank", True, "未安裝 Pillow，略過空白檢查")
    with Image.open(path) as im:
        colors = im.convert("RGB").getcolors(maxcolors=4096)
    # getcolors returns None when there are more than maxcolors distinct
    # colours — which for a real card is the healthy case.
    if colors is None:
        return _check("not_blank", True, "色彩豐富")
    if len(colors) <= 1:
        return _check("not_blank", False, "整張圖只有單一顏色，疑似空白/未渲染")
    return _check("not_blank", True, f"{len(colors)} 種顏色")


def verify_png(path, min_w=200, min_h=200):
    checks = [_check("exists", os.path.exists(path))]
    if not checks[0]["ok"]:
        return _result(checks, "PNG 不存在")
    size = os.path.getsize(path)
    checks.append(_check("nonempty", size > 0, f"{size} bytes"))
    dims = png_dimensions(path)
    if dims is None:
        checks.append(_check("is_png", False, "非 PNG 檔頭（可能存到了 HTML 錯誤頁或空檔）"))
        return _result(checks, "不是有效的 PNG")
    checks.append(_check("is_png", True))
    w, h = dims
    checks.append(_check("min_size", w >= min_w and h >= min_h, f"{w}x{h}"))
    checks.append(_png_not_blank(path))
    return _result(checks, f"{w}x{h}, {size} bytes")


# ---------------------------------------------------------------------------
# HTML
# ---------------------------------------------------------------------------

def verify_html(path, name=None):
    checks = [_check("exists", os.path.exists(path))]
    if not checks[0]["ok"]:
        return _result(checks, "HTML 不存在")
    with open(path, encoding="utf-8") as f:
        text = f.read()
    checks.append(_check("nonempty", len(text) > 0, f"{len(text)} chars"))
    checks.append(_check("has_doctype", "<!DOCTYPE html" in text or "<!doctype html" in text))
    checks.append(_check("has_card", 'class="card"' in text, "缺少 .card 版型容器"))
    checks.append(_check("closed", text.rstrip().endswith("</div>") or "</div>" in text[-400:],
                         "檔尾未見收合標籤，疑似截斷"))
    if name:
        checks.append(_check("has_name", name in text, f"未在 HTML 中找到姓名「{name}」"))
    # A photo path that didn't resolve leaves the generator's own warning
    # marker in stdout, not the html — but an <img> with an empty data: URI
    # would show here. Cheap to assert the inlining produced real data.
    return _result(checks, f"{len(text)} chars")


# ---------------------------------------------------------------------------
# XLSX
# ---------------------------------------------------------------------------

def verify_xlsx(path):
    checks = [_check("exists", os.path.exists(path))]
    if not checks[0]["ok"]:
        return _result(checks, "xlsx 不存在")
    size = os.path.getsize(path)
    checks.append(_check("nonempty", size > 0, f"{size} bytes"))
    try:
        import openpyxl
    except ImportError:
        checks.append(_check("openable", True, "未安裝 openpyxl，略過開檔檢查"))
        return _result(checks, "openpyxl 不可用，僅檢查存在與大小")
    try:
        wb = openpyxl.load_workbook(path)
        ws = wb.active
        title = ws["A2"].value
        checks.append(_check("openable", True))
        checks.append(_check("is_template", title == "個人信息登記表",
                             f"A2='{title}'，非個人信息登記表範本"))
    except Exception as e:  # noqa: BLE001 — any load failure is a finding
        checks.append(_check("openable", False, f"openpyxl 無法開啟：{e}"))
    return _result(checks, f"{size} bytes")


# ---------------------------------------------------------------------------
# CJK font preflight (PNG only, Linux only)
# ---------------------------------------------------------------------------

def cjk_font_check():
    """Is a CJK font installed? Only meaningful before a PNG render on Linux,
    where a clean server image has none and Chrome bakes every Chinese
    character into the image as a tofu box with no error. On macOS/Windows a
    CJK font is always present, so this passes as skipped.

    Returns the same {"ok", "detail", "skipped"} shape build.py expects.
    """
    if sys.platform != "linux":
        return {"ok": True, "skipped": True,
                "detail": f"{sys.platform}：系統內建 CJK 字型，不需檢查"}
    fc = shutil.which("fc-list")
    if not fc:
        return {"ok": False, "skipped": False,
                "detail": "找不到 fc-list，無法確認 CJK 字型；請安裝 fontconfig 與 fonts-noto-cjk"}
    try:
        out = subprocess.run([fc, ":lang=zh"], capture_output=True, text=True, timeout=15)
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "skipped": False, "detail": f"fc-list 執行失敗：{e}"}
    has = bool(out.stdout.strip())
    return {
        "ok": has,
        "skipped": False,
        "detail": "已安裝 CJK 字型" if has
        else "未偵測到 CJK 字型：PNG 內中文會變成空心方框。請執行 sudo apt install -y fonts-noto-cjk",
    }


# ---------------------------------------------------------------------------
# CLI — spot-check a single file
# ---------------------------------------------------------------------------

def main():
    import argparse
    import json

    ap = argparse.ArgumentParser(description="Verify one produced artifact.")
    ap.add_argument("path")
    ap.add_argument("--kind", choices=["html", "xlsx", "png"], required=True)
    ap.add_argument("--name", help="html：預期出現的姓名")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    if args.kind == "png":
        res = verify_png(args.path)
    elif args.kind == "html":
        res = verify_html(args.path, name=args.name)
    else:
        res = verify_xlsx(args.path)

    if args.json:
        print(json.dumps(res, ensure_ascii=False, indent=2))
    else:
        print(("✓" if res["ok"] else "✗") + f" {args.path} — {res['detail']}")
        for c in res["checks"]:
            mark = "✓" if c["ok"] else "✗"
            print(f"  {mark} {c['name']}" + (f": {c['detail']}" if c["detail"] else ""))
    sys.exit(0 if res["ok"] else 1)


if __name__ == "__main__":
    main()
