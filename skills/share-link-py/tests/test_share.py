import json
import os
import string
import sys
import time

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
import cleanup as C  # noqa: E402
import share as S  # noqa: E402

BASE = "https://share.example.com"


# ---------- ttl ----------

@pytest.mark.parametrize("text,expect", [
    ("7d", 7 * 86400), ("24h", 24 * 3600), ("30m", 1800),
    ("never", None), ("0", None), ("NEVER", None),
])
def test_parse_ttl(text, expect):
    assert S.parse_ttl(text) == expect


@pytest.mark.parametrize("bad", ["", "7", "d7", "1w", "3 days"])
def test_parse_ttl_rejects(bad):
    with pytest.raises(ValueError):
        S.parse_ttl(bad)


# ---------- 檔名規劃 ----------

def test_first_html_becomes_index_first_png_becomes_card():
    names = S.plan_names(["/a/王小明 個人檔案.html", "/a/王小明 個人檔案.png"])
    assert names == ["index.html", "card.png"]


def test_second_html_gets_slug_and_cjk_falls_back():
    names = S.plan_names(["/a/王小明.html", "/a/王小明.html"])
    assert names[0] == "index.html"
    # 純 CJK 檔名 slug 之後空了 → fallback file-N
    assert names[1] == "file-2.html"


def test_duplicate_names_get_suffixed():
    names = S.plan_names(["/a/report.pdf", "/b/report.pdf"])
    assert names == ["report.pdf", "report-2.pdf"]


def test_ascii_slug_strips_unsafe():
    assert S.ascii_slug("My Résumé (final).PDF", "x") == "my-resume-final.pdf"


# ---------- share ----------

def _mk(tmp_path, name, content=b"hello"):
    p = tmp_path / name
    p.write_bytes(content)
    return str(p)


def test_share_publishes_and_writes_meta(tmp_path):
    root = str(tmp_path / "root")
    f = _mk(tmp_path, "王小明 個人檔案.html", b"<html>hi</html>")
    meta, urls = S.share([f], root, BASE, S.parse_ttl("7d"))

    token = meta["token"]
    assert all(c in string.ascii_letters + string.digits + "-_" for c in token)
    pub = os.path.join(root, "pub", token, "index.html")
    assert os.path.isfile(pub)
    # html 的 URL 是短網址（目錄），靠 index.html
    assert urls[0]["url"] == f"{BASE}/{token}/"
    # meta 在 webroot 之外
    mp = os.path.join(root, "meta", f"{token}.json")
    assert os.path.isfile(mp)
    with open(mp, encoding="utf-8") as fh:
        m = json.load(fh)
    assert m["files"][0]["original"] == "王小明 個人檔案.html"
    assert m["expires_at"] - m["created_at"] == 7 * 86400
    # robots.txt 自動生成且擋全站
    with open(os.path.join(root, "pub", "robots.txt"), encoding="utf-8") as fh:
        assert "Disallow: /" in fh.read()


def test_share_never_expires(tmp_path):
    root = str(tmp_path / "root")
    meta, _ = S.share([_mk(tmp_path, "a.png")], root, BASE, None)
    assert meta["expires_at"] is None


def test_share_no_stage_leftover(tmp_path):
    root = str(tmp_path / "root")
    S.share([_mk(tmp_path, "a.png")], root, BASE, 60)
    assert os.listdir(os.path.join(root, ".tmp")) == []


# ---------- vpb job dir 整合 ----------

def _mk_jobdir(tmp_path, verified_png=True):
    job = tmp_path / "job"
    job.mkdir()
    html = job / "王小明 個人檔案.html"
    html.write_text("<html/>", encoding="utf-8")
    png = job / "王小明 個人檔案.png"
    png.write_bytes(b"\x89PNG")
    manifest = {
        "artifacts": {
            "profile-json": {"path": str(job / "profile.json"), "verified": True},
            "card-html": {"path": str(html), "verified": True},
            "card-png": {"path": str(png), "verified": verified_png},
        }
    }
    (job / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    return str(job)


def test_resolve_vpb_jobdir_picks_shareable_only(tmp_path):
    job = _mk_jobdir(tmp_path)
    files = S.resolve_inputs([job])
    basenames = [os.path.basename(f) for f in files]
    assert basenames == ["王小明 個人檔案.html", "王小明 個人檔案.png"]  # 不含 profile.json


def test_resolve_vpb_jobdir_skips_unverified(tmp_path):
    job = _mk_jobdir(tmp_path, verified_png=False)
    files = S.resolve_inputs([job])
    assert [os.path.basename(f) for f in files] == ["王小明 個人檔案.html"]


def test_resolve_plain_dir_dies(tmp_path):
    d = tmp_path / "nomanifest"
    d.mkdir()
    with pytest.raises(SystemExit):
        S.resolve_inputs([str(d)])


def test_resolve_missing_file_dies(tmp_path):
    with pytest.raises(SystemExit):
        S.resolve_inputs([str(tmp_path / "ghost.html")])


# ---------- cleanup ----------

def test_cleanup_removes_expired_keeps_live(tmp_path):
    root = str(tmp_path / "root")
    live, _ = S.share([_mk(tmp_path, "live.png")], root, BASE, 3600)
    dead, _ = S.share([_mk(tmp_path, "dead.png")], root, BASE, 60)

    res = C.cleanup(root, now=time.time() + 600)
    assert [r["token"] for r in res["removed"]] == [dead["token"]]
    assert res["kept"] == 1
    assert not os.path.exists(os.path.join(root, "pub", dead["token"]))
    assert not os.path.exists(os.path.join(root, "meta", f"{dead['token']}.json"))
    assert os.path.isfile(os.path.join(root, "pub", live["token"], "card.png"))


def test_cleanup_never_expires_kept_forever(tmp_path):
    root = str(tmp_path / "root")
    S.share([_mk(tmp_path, "a.png")], root, BASE, None)
    res = C.cleanup(root, now=time.time() + 10 * 365 * 86400)
    assert res["removed"] == [] and res["kept"] == 1


def test_cleanup_dry_run_deletes_nothing(tmp_path):
    root = str(tmp_path / "root")
    dead, _ = S.share([_mk(tmp_path, "a.png")], root, BASE, 60)
    res = C.cleanup(root, dry_run=True, now=time.time() + 600)
    assert res["removed"]
    assert os.path.isdir(os.path.join(root, "pub", dead["token"]))


def test_cleanup_removes_old_orphan_spares_robots_and_fresh(tmp_path):
    root = str(tmp_path / "root")
    S.share([_mk(tmp_path, "a.png")], root, BASE, 3600)  # 建出 pub/ + robots.txt
    pub = os.path.join(root, "pub")
    old = os.path.join(pub, "orphan-old")
    os.makedirs(old)
    past = time.time() - 2 * C.ORPHAN_GRACE
    os.utime(old, (past, past))
    fresh = os.path.join(pub, "orphan-fresh")
    os.makedirs(fresh)

    res = C.cleanup(root)
    reasons = {r["token"]: r["reason"] for r in res["removed"]}
    assert reasons == {"orphan-old": "orphan"}
    assert os.path.isdir(fresh)
    assert os.path.isfile(os.path.join(pub, "robots.txt"))


# ---------- systemd units ----------

def test_install_systemd_units_shape():
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
    import install_systemd as I
    service, timer = I.build_units(["/usr/bin/python3", "/x/cleanup.py"])
    assert "Type=oneshot" in service and "cleanup.py" in service
    assert "OnCalendar=*-*-* *:15:00" in timer and "Persistent=true" in timer
