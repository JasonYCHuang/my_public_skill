"""The -py skill's added layer: job dir, atomic writes, the Artifact Manifest,
and output verification.

These guard the pieces that turn "the model claimed it produced a file" into
"the file exists, verified, and is recorded" — the whole reason this variant
exists. Each test's docstring says which guarantee it holds.
"""
import json
import os
import struct

import pytest

import job as J
import verify_output as V
import build as B


# --- slugify ---------------------------------------------------------------

def test_slugify_keeps_cjk_strips_path_chars():
    """A job id derives from the person's name; it must be a legal folder name
    on every platform, but CJK is legal and should survive."""
    assert J.slugify("王小明") == "王小明"
    assert "/" not in J.slugify("a/b:c*d")
    assert J.slugify("  ") == "profile"  # empty falls back, never ""


# --- atomic writes ---------------------------------------------------------

def test_atomic_write_leaves_no_temp_file(tmp_path):
    """A crash mid-write must not leave a half-written target; a clean write
    must not leave a stray .part behind either."""
    dst = tmp_path / "out.txt"
    J.atomic_write_text(str(dst), "hello")
    assert dst.read_text() == "hello"
    strays = [p.name for p in tmp_path.iterdir() if p.name.startswith(".tmp-")]
    assert not strays, f"殘留暫存檔：{strays}"


def test_atomic_write_overwrites_completely(tmp_path):
    dst = tmp_path / "out.txt"
    J.atomic_write_text(str(dst), "first-longer-content")
    J.atomic_write_text(str(dst), "second")
    assert dst.read_text() == "second"


# --- manifest --------------------------------------------------------------

def test_manifest_records_only_existing_files(tmp_path, profile):
    """manifest.record hashes the file as it registers it — so an entry can
    never point at a path that was announced but never written."""
    m = J.Manifest.create(str(tmp_path / "job"), profile)
    assert (tmp_path / "job" / ".tmp").is_dir()
    f = tmp_path / "job" / "a.txt"
    J.atomic_write_text(str(f), "data")
    entry = m.record("thing", str(f), "text")
    assert entry["sha256"] and entry["bytes"] == 4
    assert m.resolve("thing") == str(f)

    with pytest.raises(FileNotFoundError):
        m.record("ghost", str(tmp_path / "nope.txt"), "text")


def test_manifest_resolve_unknown_id_is_explicit(tmp_path, profile):
    m = J.Manifest.create(str(tmp_path / "job"), profile)
    with pytest.raises(KeyError):
        m.resolve("does-not-exist")


def test_manifest_reverify_catches_tampering(tmp_path, profile):
    """job.py verify re-hashes every artifact; a file changed or deleted after
    the job ran must be reported, not silently trusted."""
    m = J.Manifest.create(str(tmp_path / "job"), profile)
    f = tmp_path / "job" / "a.txt"
    J.atomic_write_text(str(f), "data")
    m.record("thing", str(f), "text")
    assert m.reverify_hashes()["thing"]["ok"]

    f.write_text("tampered")
    assert not m.reverify_hashes()["thing"]["ok"]

    f.unlink()
    r = m.reverify_hashes()["thing"]
    assert not r["ok"] and "不存在" in r["reason"]


def test_manifest_save_and_load_roundtrip(tmp_path, profile):
    job = str(tmp_path / "job")
    m = J.Manifest.create(job, profile)
    f = tmp_path / "job" / "a.txt"
    J.atomic_write_text(str(f), "data")
    m.record("thing", str(f), "text")
    m.save()
    again = J.Manifest.load(job)
    assert again.resolve("thing") == str(f)
    assert again.data["schema"] == J.MANIFEST_SCHEMA


# --- verify_output: PNG ----------------------------------------------------

def _write_png(path, size=(300, 300), color=(120, 130, 140)):
    from PIL import Image

    Image.new("RGB", size, color).save(path)


def test_png_dimensions_from_header(tmp_path):
    p = tmp_path / "x.png"
    _write_png(p, size=(321, 123))
    assert V.png_dimensions(str(p)) == (321, 123)


def test_verify_png_rejects_non_png(tmp_path):
    """A saved 403/HTML error page (a real failure mode) must not pass as an
    image just because the filename ends .png."""
    p = tmp_path / "fake.png"
    p.write_text("<html>Access Denied</html>")
    res = V.verify_png(str(p))
    assert not res["ok"]
    assert any(c["name"] == "is_png" and not c["ok"] for c in res["checks"])


def test_verify_png_flags_blank_image(tmp_path):
    pytest.importorskip("PIL")
    p = tmp_path / "blank.png"
    _write_png(p, color=(255, 255, 255))  # one flat colour
    res = V.verify_png(str(p))
    assert not res["ok"]
    assert any(c["name"] == "not_blank" and not c["ok"] for c in res["checks"])


def test_verify_png_accepts_real_multicolor(tmp_path):
    from PIL import Image

    p = tmp_path / "ok.png"
    im = Image.new("RGB", (300, 300), (255, 255, 255))
    for x in range(300):
        for y in range(0, 300, 2):
            im.putpixel((x, y), (x % 256, y % 256, 40))
    im.save(p)
    assert V.verify_png(str(p))["ok"]


# --- verify_output: HTML ---------------------------------------------------

def test_verify_html_ok_and_name_check(tmp_path):
    good = '<!DOCTYPE html><div class="card"><h1>王小明</h1></div>'
    p = tmp_path / "c.html"
    p.write_text(good, encoding="utf-8")
    assert V.verify_html(str(p), name="王小明")["ok"]
    assert not V.verify_html(str(p), name="李四")["ok"]  # wrong name -> fail


def test_verify_html_catches_truncation(tmp_path):
    p = tmp_path / "c.html"
    p.write_text('<!DOCTYPE html><div class="card"><h1>王小明</h1>', encoding="utf-8")
    assert not V.verify_html(str(p), name="王小明")["ok"]  # no closing tag


# --- verify_output: xlsx & font -------------------------------------------

def test_verify_xlsx_ok_on_generated_and_fails_on_garbage(tmp_path, profile):
    import profile_json_to_xlsx as X

    good = tmp_path / "g.xlsx"
    X.build(profile).save(str(good))
    assert V.verify_xlsx(str(good))["ok"]

    bad = tmp_path / "b.xlsx"
    bad.write_text("not a spreadsheet")
    assert not V.verify_xlsx(str(bad))["ok"]


def test_cjk_font_check_shape():
    r = V.cjk_font_check()
    assert set(r) >= {"ok", "detail"}
    import sys
    if sys.platform != "linux":
        assert r["ok"] and r.get("skipped")


# --- build end-to-end (no Chrome) -----------------------------------------

def test_build_produces_verified_manifest(tmp_path, profile):
    """The whole point, in one test: validate -> generate -> verify -> record,
    with a manifest whose entries all verify and whose paths all exist."""
    pj = tmp_path / "profile.json"
    pj.write_text(json.dumps(profile, ensure_ascii=False), encoding="utf-8")
    job = str(tmp_path / "job")

    manifest, results = B.build(str(pj), job, ["html", "xlsx"])

    assert results["card-html"]["ok"]
    assert results["registry-xlsx"]["ok"]
    for aid in ("profile-json", "card-html", "registry-xlsx"):
        entry = manifest.data["artifacts"][aid]
        assert os.path.exists(entry["path"])
    # re-hash: everything recorded still matches disk
    assert all(r["ok"] for r in manifest.reverify_hashes().values())
    # manifest.json itself was written
    assert (tmp_path / "job" / "manifest.json").exists()


def test_normalize_fills_timestamp_when_blank(profile):
    """timestamp is a clock value; a blank one is filled by code, not the model."""
    profile["timestamp"] = "-"
    notes = B.normalize(profile)
    assert profile["timestamp"] != "-" and "/" in profile["timestamp"]
    assert any("timestamp" in n for n in notes)


def test_normalize_keeps_supplied_timestamp(profile):
    profile["timestamp"] = "2026/01/01"
    B.normalize(profile)
    assert profile["timestamp"] == "2026/01/01"


def test_normalize_merges_photo_source_url_into_sources(profile, photo_file):
    """A photo's source_url used to be a diligence warning the model had to act
    on; normalize merges it so the footer traceability is automatic."""
    profile["photos"] = [{"path": str(photo_file), "caption": "x",
                          "source_url": "https://example.org/pic"}]
    profile["sources"] = [{"title": "a", "url": "https://example.org/a"}]
    B.normalize(profile)
    urls = {s["url"] for s in profile["sources"]}
    assert "https://example.org/pic" in urls


def test_normalize_does_not_duplicate_existing_source(profile, photo_file):
    profile["photos"] = [{"path": str(photo_file), "caption": "x",
                          "source_url": "https://example.org/pic"}]
    profile["sources"] = [{"title": "a", "url": "https://example.org/pic"}]
    B.normalize(profile)
    assert sum(s["url"] == "https://example.org/pic" for s in profile["sources"]) == 1


def test_build_accepts_source_xlsx_directly(tmp_path, profile):
    """Entry point A in one command: build.py takes an xlsx and extracts it
    in-process, no separate xlsx->json step."""
    import profile_json_to_xlsx as X

    src = tmp_path / "來源.xlsx"
    X.build(profile).save(str(src))
    job = str(tmp_path / "job")

    manifest, results = B.build(str(src), job, ["html", "xlsx"])
    assert results["card-html"]["ok"] and results["registry-xlsx"]["ok"]
    # the extracted+built profile carries the person's name through
    assert manifest.data["profile"]["name"] == profile["name"]


def test_build_aborts_on_invalid_profile(tmp_path, profile):
    """A profile over a hard limit must stop the build before any file lands."""
    profile["positions"] = ["a", "b", "c", "d"]  # >3, a hard error
    pj = tmp_path / "profile.json"
    pj.write_text(json.dumps(profile, ensure_ascii=False), encoding="utf-8")
    job = tmp_path / "job"
    with pytest.raises(SystemExit):
        B.build(str(pj), str(job), ["html"])
    # nothing rendered
    assert not (job / "manifest.json").exists() or not list(job.glob("*.html"))
