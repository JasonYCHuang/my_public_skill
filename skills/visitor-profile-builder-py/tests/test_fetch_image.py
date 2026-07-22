"""fetch_image.py: the photo download + "is it really an image" checks that
used to be a curl recipe and a prose reminder in photo-sourcing.md.

Network is stubbed — `fetch` is monkeypatched so tests exercise the sniffing,
dimension-parsing and verification logic, not connectivity.
"""
import io

import pytest

import fetch_image as F


def _png_bytes(size=(120, 90), color=(30, 60, 90)):
    from PIL import Image

    buf = io.BytesIO()
    Image.new("RGB", size, color).save(buf, format="PNG")
    return buf.getvalue()


def _jpeg_bytes(size=(200, 150)):
    from PIL import Image

    buf = io.BytesIO()
    Image.new("RGB", size, (200, 100, 50)).save(buf, format="JPEG")
    return buf.getvalue()


# --- magic sniffing --------------------------------------------------------

def test_sniff_ext_recognizes_real_images():
    assert F.sniff_ext(_png_bytes()) == "png"
    assert F.sniff_ext(_jpeg_bytes()) == "jpg"
    assert F.sniff_ext(b"GIF89a....") == "gif"
    assert F.sniff_ext(b"RIFF\x00\x00\x00\x00WEBPxxxx") == "webp"


def test_sniff_ext_rejects_html():
    """The exact failure mode a 403 produces: an HTML page saved as .jpg."""
    assert F.sniff_ext(b"<!DOCTYPE html><html>Access Denied</html>") is None


# --- dimensions from headers ----------------------------------------------

def test_png_dimensions_from_header():
    assert F.dimensions(_png_bytes(size=(321, 123)), "png") == (321, 123)


def test_jpeg_dimensions_walks_to_sof():
    data = _jpeg_bytes(size=(200, 150))
    assert F._jpeg_size(data) == (200, 150)


def test_gif_dimensions_little_endian():
    # width=4 height=1 as little-endian uint16 pairs after 'GIF89a'
    data = b"GIF89a" + (4).to_bytes(2, "little") + (1).to_bytes(2, "little")
    assert F.dimensions(data, "gif") == (4, 1)


# --- fetch_and_verify (network stubbed) -----------------------------------

def test_fetch_and_verify_rejects_html_page(tmp_path, monkeypatch):
    monkeypatch.setattr(F, "fetch", lambda *a, **k: b"<html>403 Forbidden</html>")
    out = tmp_path / "photo.jpg"
    res = F.fetch_and_verify("http://x/y.jpg", str(out))
    assert not res["ok"]
    assert not out.exists()  # nothing written when it isn't an image


def test_fetch_and_verify_rejects_empty(tmp_path, monkeypatch):
    monkeypatch.setattr(F, "fetch", lambda *a, **k: b"")
    res = F.fetch_and_verify("http://x/y.jpg", str(tmp_path / "p.jpg"))
    assert not res["ok"]


def test_fetch_and_verify_writes_real_image(tmp_path, monkeypatch):
    monkeypatch.setattr(F, "fetch", lambda *a, **k: _png_bytes(size=(300, 240)))
    out = tmp_path / "photo.png"
    res = F.fetch_and_verify("http://x/y", str(out))
    assert res["ok"]
    assert out.exists() and out.stat().st_size > 0
    assert res["type"] == "png"
    assert res["dimensions"] == [300, 240]


def test_fetch_and_verify_flags_low_res(tmp_path, monkeypatch):
    monkeypatch.setattr(F, "fetch", lambda *a, **k: _png_bytes(size=(64, 84)))
    res = F.fetch_and_verify("http://x/y", str(tmp_path / "p.png"))
    assert res["ok"] and "low_res" in res
