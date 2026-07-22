#!/usr/bin/env python3
"""
Build every requested deliverable from one profile.json, in one deterministic
pass — the -py skill's single entry point for turning verified data into
verified files.

    python3 build.py <profile.json|來源.xlsx> [--job-dir DIR]
                     [--formats html,xlsx,png] [--allow-missing-font] [--json]

The input may be a profile.json **or a source xlsx** — a source xlsx is
extracted in-process (entry point A becomes one command instead of two).

What it does, in order, for each run:

  0. **Normalise** the machine-decidable bits (normalize): default an empty
     `timestamp` to today, and merge each photo's `source_url` into `sources`.
     These used to be a field the model filled and a diligence warning it had
     to act on; here they're automatic.
  1. **Validate** the profile against the field contract (validate_profile).
     Any error aborts before a single file is written — same guarantee the
     parent skill's generators give, kept here as the first gate.
  2. **Create/locate the job directory** and a `.tmp/` scratch area in it
     (job.py). One job = one person = one folder.
  3. For each format: **render → verify → atomically place → hash into the
     manifest.** Nothing is announced as done until it exists on disk and has
     passed verify_output's structural checks. PNG additionally runs the CJK
     font preflight *before* launching the browser.
  4. **Write manifest.json** — the one record of what was actually produced,
     each artifact carrying a stable id, real path, size, sha256 and verify
     result. Downstream steps refer to outputs by id via `job.py path …`,
     never by a reconstructed free path.

The exit code is the honest answer to "did it work": 0 only if every
requested artifact was produced and verified. `--json` additionally prints a
machine-readable summary to stdout for an agent to read back instead of
guessing from prose.

This is the marp's 策略柔性/執行剛性 split made concrete: the model does the
research and fills profile.json (soft, cognitive); everything from here down
— directory layout, atomic writes, verification, the manifest — is Python
that behaves identically regardless of which model called it.
"""
import argparse
import json
import os
import subprocess
import sys
from datetime import datetime

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

import job as J  # noqa: E402
import verify_output as V  # noqa: E402
from validate_profile import validate  # noqa: E402
import profile_json_to_html as HTML  # noqa: E402
import profile_json_to_xlsx as XLSX  # noqa: E402
import xlsx_to_profile_json as X2J  # noqa: E402

ALL_FORMATS = ("html", "xlsx", "png")
HTML_TMP_NAME = "card.html"  # ascii tmp name so the node arg stays simple


def _log(msg):
    print(msg, file=sys.stderr)


def _die(msg, code=2):
    _log(msg)
    sys.exit(code)


def _load_profile(path):
    """Load a profile from either a profile.json or a source xlsx. Accepting
    the xlsx here is what collapses entry point A from 'extract, then build'
    into one command — the model no longer has to chain two scripts and
    remember to validate between them."""
    ext = os.path.splitext(path)[1].lower()
    if ext in (".xlsx", ".xlsm"):
        return X2J.extract(path), os.path.abspath(path)
    with open(path, encoding="utf-8") as f:
        return json.load(f), os.path.abspath(path)


def _peek_name(path):
    try:
        return _load_profile(path)[0].get("name") or "profile"
    except Exception:  # noqa: BLE001 — only used to name a default folder
        return "profile"


def normalize(data):
    """Fill the machine-decidable bits so the model doesn't have to, and
    return a list of what was changed (for logging). Runs before validate.

    - `timestamp`: a pure clock value. If blank/'-'/missing, set to today.
    - photo `source_url` -> `sources`: the validator used to only *warn* that
      a photo's source wasn't listed in sources (a diligence step the model
      had to act on). The url is right there on the photo, so merge it.
    """
    notes = []

    ts = (data.get("timestamp") or "").strip()
    if ts in ("", "-"):
        data["timestamp"] = datetime.now().strftime("%Y/%m/%d")
        notes.append(f"timestamp 未填，自動填入今日 {data['timestamp']}")

    sources = data.get("sources")
    if not isinstance(sources, list):
        sources = []
        data["sources"] = sources
    listed = {s.get("url") for s in sources if isinstance(s, dict)}
    for p in data.get("photos") or []:
        if not isinstance(p, dict):
            continue
        u = p.get("source_url")
        if u and u not in listed:
            sources.append({"title": "照片來源", "url": u})
            listed.add(u)
            notes.append(f"已將照片 source_url 併入 sources：{u}")

    return notes


def _render_html_to_tmp(data, tmp_dir):
    """Render the card and stage it in .tmp/. Returns (tmp_html_path, text)."""
    text = HTML.render(data)
    tmp_html = os.path.join(tmp_dir, HTML_TMP_NAME)
    with open(tmp_html, "w", encoding="utf-8") as f:
        f.write(text)
    return tmp_html, text


def _run_html_to_png(tmp_html):
    """Screenshot the staged html. node writes <base>.png beside it, so the
    png lands in .tmp/ where we can verify it before moving it into place."""
    script = os.path.join(_HERE, "html_to_png.js")
    proc = subprocess.run(
        ["node", script, tmp_html],
        capture_output=True, text=True,
    )
    png = tmp_html[:-len(".html")] + ".png"
    return proc, png


def build(profile_path, job_dir, formats, allow_missing_font=False):
    data, source = _load_profile(profile_path)

    # 0. Normalise the machine-fillable bits before validating, so the model
    #    doesn't carry them: timestamp, and photo source_url -> sources.
    for n in normalize(data):
        _log(f"ℹ️  {n}")

    # 1. Validate — abort before writing anything.
    errors, warnings = validate(data)
    for w in warnings:
        _log(f"⚠️  {w}")
    if errors:
        for e in errors:
            _log(f"❌ {e}")
        _die(f"\nprofile.json 驗證失敗（{len(errors)} 項），未產生任何檔案。", code=2)

    name = data.get("name", "")

    # 2. Job dir + manifest.
    manifest = J.Manifest.create(job_dir, data, source=source)
    tmp_dir = os.path.join(manifest.job_dir, J.TMP_DIRNAME)

    # Provenance: keep the exact profile the artifacts were built from.
    prof_copy = os.path.join(manifest.job_dir, "profile.json")
    J.atomic_write_text(prof_copy, json.dumps(data, ensure_ascii=False, indent=2) + "\n")
    manifest.record("profile-json", prof_copy, "json",
                    verify={"ok": True, "checks": [], "detail": "來源資料副本"})

    results = {}  # artifact_id -> {"ok", "detail"}

    # Render html once if any consumer needs it (html output and/or png).
    tmp_html = html_text = None
    if "html" in formats or "png" in formats:
        tmp_html, html_text = _render_html_to_tmp(data, tmp_dir)

    # 3a. HTML.
    if "html" in formats:
        hv = V.verify_html(tmp_html, name=name)
        final_html = os.path.join(manifest.job_dir, f"{name} 個人檔案.html")
        J.atomic_write_text(final_html, html_text)
        manifest.record("card-html", final_html, "html", verify=hv)
        results["card-html"] = {"ok": hv["ok"], "detail": hv["detail"]}

    # 3b. XLSX.
    if "xlsx" in formats:
        wb = XLSX.build(data)
        tmp_xlsx = os.path.join(tmp_dir, "registry.xlsx")
        wb.save(tmp_xlsx)
        xv = V.verify_xlsx(tmp_xlsx)
        final_xlsx = os.path.join(manifest.job_dir, f"{name} 個人信息表.xlsx")
        if xv["ok"]:
            J.atomic_move(tmp_xlsx, final_xlsx)
            manifest.record("registry-xlsx", final_xlsx, "xlsx", verify=xv)
        results["registry-xlsx"] = {"ok": xv["ok"], "detail": xv["detail"]}

    # 3c. PNG — font preflight, then screenshot, then verify.
    if "png" in formats:
        font = V.cjk_font_check()
        if not font["ok"] and not allow_missing_font:
            _die(
                f"\n❌ CJK 字型預檢失敗：{font['detail']}\n"
                "PNG 內的中文會變成空心方框。裝好字型後重跑，"
                "或加 --allow-missing-font 明知風險仍要產出（產出會標記為未通過驗證）。",
                code=3,
            )
        proc, tmp_png = _run_html_to_png(tmp_html)
        if proc.returncode != 0 or not os.path.exists(tmp_png):
            _log(proc.stderr.strip() or proc.stdout.strip())
            results["card-png"] = {"ok": False, "detail": "html_to_png.js 失敗（Chrome 未安裝？見 README）"}
        else:
            pv = V.verify_png(tmp_png)
            if not font["ok"]:
                pv["ok"] = False
                pv["checks"].append({"name": "cjk_font", "ok": False, "detail": font["detail"]})
                pv["detail"] += "｜字型預檢未過，中文可能是方框"
            elif not font.get("skipped"):
                pv["checks"].append({"name": "cjk_font", "ok": True, "detail": font["detail"]})
            final_png = os.path.join(manifest.job_dir, f"{name} 個人檔案.png")
            J.atomic_move(tmp_png, final_png)  # move even when flagged, so it can be inspected
            manifest.record("card-png", final_png, "png", verify=pv)
            results["card-png"] = {"ok": pv["ok"], "detail": pv["detail"]}

    manifest.save()
    return manifest, results


def _print_human(manifest, results):
    _log("")
    _log(f"job_dir : {manifest.job_dir}")
    _log(f"manifest: {manifest.path}")
    for aid, r in results.items():
        mark = "✓" if r["ok"] else "✗"
        path = manifest.data["artifacts"].get(aid, {}).get("path", "(未寫入)")
        _log(f"  {mark} {aid:<13} {r['detail']}")
        _log(f"      {path}")
    all_ok = all(r["ok"] for r in results.values())
    _log("")
    _log("全部產出並通過驗證。" if all_ok
         else "有 artifact 未通過驗證 —— 見上方 ✗ 與 manifest.verify。")


def main():
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("profile_json", metavar="profile.json|來源.xlsx",
                    help="輸入的 profile.json，或直接給來源 xlsx（會自動抽取）")
    ap.add_argument("--job-dir", help="輸出資料夾（預設：./vpb-out/<姓名>-<時間戳>）")
    ap.add_argument("--formats", default="html,xlsx",
                    help="逗號分隔，可選 html,xlsx,png（預設 html,xlsx；png 需要 Node/Chrome）")
    ap.add_argument("--allow-missing-font", action="store_true",
                    help="Linux 無 CJK 字型時仍產 PNG（會標記為未通過驗證）")
    ap.add_argument("--json", action="store_true", help="在 stdout 輸出機器可讀的結果摘要")
    args = ap.parse_args()

    formats = [x.strip() for x in args.formats.split(",") if x.strip()]
    bad = [x for x in formats if x not in ALL_FORMATS]
    if bad:
        _die(f"未知格式：{', '.join(bad)}（可選：{', '.join(ALL_FORMATS)}）")

    job_dir = args.job_dir
    if not job_dir:
        nm = _peek_name(args.profile_json)
        job_dir = os.path.join("vpb-out", f"{J.slugify(nm)}-{J.now_stamp()}")

    manifest, results = build(args.profile_json, job_dir, formats,
                              allow_missing_font=args.allow_missing_font)

    all_ok = all(r["ok"] for r in results.values())
    if args.json:
        print(json.dumps({
            "ok": all_ok,
            "job_dir": manifest.job_dir,
            "manifest": manifest.path,
            "artifacts": {
                aid: {
                    "path": manifest.data["artifacts"].get(aid, {}).get("path"),
                    "verified": r["ok"],
                    "detail": r["detail"],
                }
                for aid, r in results.items()
            },
        }, ensure_ascii=False, indent=2))
    else:
        _print_human(manifest, results)

    sys.exit(0 if all_ok else 1)


if __name__ == "__main__":
    main()
