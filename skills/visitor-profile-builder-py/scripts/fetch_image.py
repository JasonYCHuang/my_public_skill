#!/usr/bin/env python3
"""
Download a candidate photo and verify it is actually an image — replacing the
curl recipe and the "check what you downloaded" prose that photo-sourcing.md
used to leave to the model.

Two things this mechanises:

1. **The 403 workaround.** Many institutional sites (`.edu.tw` in particular)
   block a bare download with a 403 bot-challenge page even though the image
   loads fine in a browser. Sending a browser User-Agent and a Referer
   pointing at the page you found the image on gets past it. That used to be a
   curl command the model had to assemble correctly; here it is the default.

2. **"Verify what you actually downloaded."** A 403/redirect saves an HTML
   error page under a `.jpg` name, which then fails much later as a broken
   image in the card. This script sniffs the real bytes: if what came back
   isn't a PNG/JPEG/GIF/WebP (e.g. it's HTML), it fails now, with the hint to
   pass --referer. When Pillow is present it also decodes the image, catching
   a truncated download, and reports the real pixel dimensions.

What stays the model's job (soft, cognitive): deciding the photo is of the
*right person*, and whether a low-resolution informal shot is acceptable.
This script only answers "did I get a real, whole image file back".

    python3 fetch_image.py <url> -o <path> [--referer PAGE_URL] [--json]

Exit 0 on a verified image, 1 otherwise.
"""
import argparse
import io
import json as _json
import os
import struct
import sys
import urllib.error
import urllib.request

# The UA that got past the Imperva TS0... challenge in the original session.
DEFAULT_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)


def sniff_ext(data):
    """Real file type from magic bytes, independent of the URL's extension."""
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return "png"
    if data[:3] == b"\xff\xd8\xff":
        return "jpg"
    if data[:6] in (b"GIF87a", b"GIF89a"):
        return "gif"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "webp"
    return None


def _jpeg_size(data):
    """(w, h) by walking JPEG segments to the SOF marker. No Pillow needed."""
    if data[:2] != b"\xff\xd8":
        return None
    i, n = 2, len(data)
    while i + 1 < n:
        if data[i] != 0xFF:
            i += 1
            continue
        while i < n and data[i] == 0xFF:  # skip fill bytes
            i += 1
        if i >= n:
            break
        marker = data[i]
        i += 1
        # Standalone markers (SOI/EOI/RSTn/TEM): no length field.
        if marker in (0xD8, 0xD9, 0x01) or 0xD0 <= marker <= 0xD7:
            continue
        if i + 1 >= n:
            break
        seg_len = int.from_bytes(data[i:i + 2], "big")
        # SOF0..SOF15 except DHT(C4)/JPG(C8)/DAC(CC): height/width live here.
        if 0xC0 <= marker <= 0xCF and marker not in (0xC4, 0xC8, 0xCC):
            h = int.from_bytes(data[i + 3:i + 5], "big")
            w = int.from_bytes(data[i + 5:i + 7], "big")
            return (w, h)
        i += seg_len
    return None


def dimensions(data, ext):
    """Pixel size without decoding, for the formats where the header carries
    it; Pillow (if present) covers webp and anything exotic."""
    if ext == "png" and len(data) >= 24:
        return struct.unpack(">II", data[16:24])
    if ext == "jpg":
        return _jpeg_size(data)
    if ext == "gif" and len(data) >= 10:
        return (int.from_bytes(data[6:8], "little"),
                int.from_bytes(data[8:10], "little"))
    try:
        from PIL import Image
        with Image.open(io.BytesIO(data)) as im:
            return im.size
    except Exception:  # noqa: BLE001 — no dims is a soft outcome, not a crash
        return None


def decode_ok(data):
    """If Pillow is available, fully decode to catch a truncated download.
    Returns (ok, detail); ok=True/skipped when Pillow isn't installed."""
    try:
        from PIL import Image
    except ImportError:
        return True, "未安裝 Pillow，略過解碼檢查"
    try:
        with Image.open(io.BytesIO(data)) as im:
            im.load()
        return True, "解碼成功"
    except Exception as e:  # noqa: BLE001
        return False, f"影像解碼失敗（可能下載不完整）：{e}"


def fetch(url, referer=None, timeout=30):
    headers = {"User-Agent": DEFAULT_UA}
    if referer:
        headers["Referer"] = referer
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read()


def fetch_and_verify(url, out_path, referer=None, timeout=30):
    """Returns a result dict; writes the file only when it's a real image."""
    try:
        data = fetch(url, referer=referer, timeout=timeout)
    except urllib.error.HTTPError as e:
        return {"ok": False, "reason": f"HTTP {e.code}：{e.reason}。"
                "若是 403，改用 --referer 指到你找到這張圖的頁面再試一次。"}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "reason": f"下載失敗：{e}"}

    if not data:
        return {"ok": False, "reason": "下載到 0 位元組。"}

    ext = sniff_ext(data)
    if ext is None:
        head = data.lstrip()[:1]
        hint = ("（看起來是 HTML/文字，多半是 403 或轉址錯誤頁）"
                if head in (b"<", b"{") else "")
        return {"ok": False, "reason": f"下載到的不是圖片{hint}。"
                "試試 --referer 指到你找到這張圖的頁面。"}

    ok, decode_detail = decode_ok(data)
    if not ok:
        return {"ok": False, "reason": decode_detail}

    dims = dimensions(data, ext)
    os.makedirs(os.path.dirname(os.path.abspath(out_path)) or ".", exist_ok=True)
    with open(out_path, "wb") as f:
        f.write(data)

    res = {
        "ok": True,
        "path": os.path.abspath(out_path),
        "type": ext,
        "bytes": len(data),
        "dimensions": list(dims) if dims else None,
        "decode": decode_detail,
    }
    if dims and (dims[0] < 100 or dims[1] < 100):
        # Informational, not a failure: faculty thumbnails are legitimately
        # tiny. photo-sourcing.md §3 — say so in note/caption.
        res["low_res"] = f"{dims[0]}x{dims[1]}，解析度偏低，請在 note/caption 標明"
    return res


def main():
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("url")
    ap.add_argument("-o", "--output", required=True, help="輸出圖片路徑")
    ap.add_argument("--referer", help="你找到這張圖的頁面網址（破 403 用）")
    ap.add_argument("--timeout", type=int, default=30)
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    res = fetch_and_verify(args.url, args.output, referer=args.referer,
                           timeout=args.timeout)
    if args.json:
        print(_json.dumps(res, ensure_ascii=False, indent=2))
    elif res["ok"]:
        dims = res["dimensions"]
        print(f"✓ {res['path']}  {res['type']} "
              f"{f'{dims[0]}x{dims[1]}' if dims else '尺寸未知'}  {res['bytes']} bytes")
        if res.get("low_res"):
            print(f"  ⚠️  {res['low_res']}")
        print("  下一步：看一眼確認是本人，再填進 profile.json 的 photos（含 source_url）。")
    else:
        print(f"✗ {res['reason']}", file=sys.stderr)
    sys.exit(0 if res["ok"] else 1)


if __name__ == "__main__":
    main()
