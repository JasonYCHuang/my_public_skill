#!/usr/bin/env python3
"""
Verify a produced calendar artifact is real and not silently broken.

The parent skill's SKILL.md tells the model to *look at* the PNG before
saying it's done ("screenshot generation is exactly the kind of step that
fails silently"), and to eyeball the HTML for clipping. Those instructions
only work if a model reads them and remembers to act. Here the same checks
are code that build.py runs on every artifact, so an unverified output can't
be reported as finished no matter who is driving.

Each verify_* returns a dict:
    {"ok": bool, "checks": [ {"name", "ok", "detail"}, ... ], "detail": str}

The checks are deliberately cheap and structural — "is this a real PNG of a
plausible size", "does the html carry the expected title, a full week-grid,
and its closing tags" — not a full visual review. They catch the failure
modes that produce a file that *looks* written but is unusable: a zero-byte
png, an html truncated mid-grid, a screenshot of an empty page.

The one failure a pixel check can't catch — Chinese baked into a PNG as tofu
boxes because a headless Linux box has no CJK font — is caught up front by
cjk_font_check(), which build.py runs before it ever launches the browser.
"""
import os
import re
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
    None if the file isn't a PNG (which is itself a finding: a zero-byte file
    or an error page saved with a .png name)."""
    with open(path, "rb") as f:
        head = f.read(24)
    if len(head) < 24 or head[:8] != PNG_SIG:
        return None
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
    if colors is None:
        return _check("not_blank", True, "色彩豐富")
    if len(colors) <= 1:
        return _check("not_blank", False, "整張圖只有單一顏色，疑似空白/未渲染")
    return _check("not_blank", True, f"{len(colors)} 種顏色")


def verify_png(path, min_w=600, min_h=400):
    """A calendar page is landscape and wide — the 2x screenshot of even a
    week view is well past 600px. Anything smaller means the page didn't lay
    out (e.g. Chrome rendered before the CSS loaded)."""
    checks = [_check("exists", os.path.exists(path))]
    if not checks[0]["ok"]:
        return _result(checks, "PNG 不存在")
    size = os.path.getsize(path)
    checks.append(_check("nonempty", size > 0, f"{size} bytes"))
    dims = png_dimensions(path)
    if dims is None:
        checks.append(_check("is_png", False, "非 PNG 檔頭（可能是空檔或錯誤頁）"))
        return _result(checks, "不是有效的 PNG")
    checks.append(_check("is_png", True))
    w, h = dims
    checks.append(_check("min_size", w >= min_w and h >= min_h, f"{w}x{h}"))
    checks.append(_png_not_blank(path))
    return _result(checks, f"{w}x{h}, {size} bytes")


# ---------------------------------------------------------------------------
# HTML (generated month / week view)
# ---------------------------------------------------------------------------

_DAY_CELL_RE = re.compile(r'<div class="day[" ]')


def verify_html(path, expect_title=None, expect_day_cells=None):
    """Structural checks on a generated view:

    - expect_title: text that must appear in <title> (e.g. the month title) —
      catches the template's placeholder title surviving a failed substitution.
    - expect_day_cells: exact number of day cells (incl. empty leading/trailing
      cells) the grid must hold — 7 for a week view, a multiple of 7 (28–42)
      for a month view. Catches a truncated grid or a regex splice that
      silently matched nothing.
    """
    checks = [_check("exists", os.path.exists(path))]
    if not checks[0]["ok"]:
        return _result(checks, "HTML 不存在")
    with open(path, encoding="utf-8") as f:
        text = f.read()
    checks.append(_check("nonempty", len(text) > 0, f"{len(text)} chars"))
    checks.append(_check("has_doctype",
                         "<!DOCTYPE html" in text or "<!doctype html" in text))
    checks.append(_check("has_grid", 'class="grid"' in text, "缺少 .grid 版型容器"))
    checks.append(_check("closed", text.rstrip().endswith("</html>"),
                         "檔尾不是 </html>，疑似截斷"))
    if expect_title:
        m = re.search(r"<title>(.*?)</title>", text, re.DOTALL)
        got = (m.group(1) if m else "").strip()
        checks.append(_check("title", expect_title in got,
                             f"<title> 為「{got}」，未包含預期的「{expect_title}」"))
    if expect_day_cells is not None:
        n = len(_DAY_CELL_RE.findall(text))
        checks.append(_check("day_cells", n == expect_day_cells,
                             f"格線有 {n} 個日格，預期 {expect_day_cells}"))
    return _result(checks, f"{len(text)} chars")


# ---------------------------------------------------------------------------
# CJK font preflight (PNG only, Linux only)
# ---------------------------------------------------------------------------

def cjk_font_check():
    """Is a CJK font installed? Only meaningful before a PNG render on Linux,
    where a clean server image has none and Chrome bakes every Chinese
    character into the image as a tofu box with no error. On macOS/Windows a
    CJK font is always present, so this passes as skipped."""
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
    ap.add_argument("--kind", choices=["html", "png"], required=True)
    ap.add_argument("--title", help="html：<title> 應包含的文字")
    ap.add_argument("--day-cells", type=int, help="html：格線應有的日格數")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    if args.kind == "png":
        res = verify_png(args.path)
    else:
        res = verify_html(args.path, expect_title=args.title,
                          expect_day_cells=args.day_cells)

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
