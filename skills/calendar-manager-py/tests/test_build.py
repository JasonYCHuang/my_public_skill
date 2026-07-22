"""build.py end-to-end (html path — png needs Chrome and is exercised by
scripts/verify-on-ubuntu-style manual runs), plus the manifest contract."""
import json
import subprocess
import sys
from pathlib import Path

import build as B
import job as J

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"


def _run_build(events, tmp_path, **kw):
    job_dir = tmp_path / "job"
    manifest, results = B.build(events, str(job_dir), 2026, 8, "範例",
                                ["html"], **kw)
    return job_dir, manifest, results


class TestBuild:
    def test_all_artifacts_produced_and_verified(self, events, tmp_path):
        job_dir, manifest, results = _run_build(events, tmp_path)
        expected = {"events-json", "month-html",
                    "week-1-html", "week-2-html", "week-3-html",
                    "week-4-html", "week-5-html"}
        assert set(manifest.data["artifacts"]) == expected
        assert all(r["ok"] for r in results.values()), results
        for aid, entry in manifest.data["artifacts"].items():
            p = Path(entry["path"])
            assert p.exists(), aid
            assert entry["sha256"] == J.sha256_file(str(p))
            assert entry["verified"] is True

    def test_filenames_follow_name_prefix(self, events, tmp_path):
        job_dir, manifest, _ = _run_build(events, tmp_path)
        assert (job_dir / "26年8月.html").exists()
        assert (job_dir / "26年8月-第五週.html").exists()

    def test_events_copy_is_the_input(self, events, tmp_path):
        job_dir, _, _ = _run_build(events, tmp_path)
        saved = json.loads((job_dir / "events.json").read_text(encoding="utf-8"))
        assert saved == events

    def test_skip_weeks(self, events, tmp_path):
        _, manifest, results = _run_build(events, tmp_path, skip_weeks=True)
        assert set(manifest.data["artifacts"]) == {"events-json", "month-html"}

    def test_subject_recorded(self, events, tmp_path):
        _, manifest, _ = _run_build(events, tmp_path)
        subj = manifest.data["subject"]
        assert subj["title"] == "範例 2026 年 8 月行事曆"
        assert (subj["year"], subj["month"]) == (2026, 8)

    def test_derive_names(self):
        assert B.derive_names("範例", 2026, 8) == ("範例 2026 年 8 月行事曆", "26年8月")

    def test_month_day_cell_count(self):
        assert B.month_day_cell_count(2026, 8) == 42   # Sat start, 31 days
        assert B.month_day_cell_count(2026, 2) == 28   # 2026-02-01 is a Sunday
        assert B.month_day_cell_count(2026, 11) == 35


class TestJobCli:
    def _job(self, events, tmp_path):
        job_dir, _, _ = _run_build(events, tmp_path)
        return str(job_dir)

    def _cli(self, *args):
        return subprocess.run([sys.executable, str(SCRIPTS / "job.py"), *args],
                              capture_output=True, text=True)

    def test_list(self, events, tmp_path):
        out = self._cli("list", self._job(events, tmp_path))
        assert out.returncode == 0
        assert "month-html" in out.stdout
        assert "✗" not in out.stdout

    def test_path_resolves_real_file(self, events, tmp_path):
        job = self._job(events, tmp_path)
        out = self._cli("path", job, "month-html")
        assert out.returncode == 0
        assert Path(out.stdout.strip()).exists()

    def test_path_unknown_id_fails(self, events, tmp_path):
        out = self._cli("path", self._job(events, tmp_path), "nope")
        assert out.returncode != 0

    def test_verify_detects_tampering(self, events, tmp_path):
        job = self._job(events, tmp_path)
        assert self._cli("verify", job).returncode == 0
        month = Path(job) / "26年8月.html"
        month.write_text(month.read_text(encoding="utf-8") + "<!-- tampered -->",
                         encoding="utf-8")
        out = self._cli("verify", job)
        assert out.returncode == 1
        assert "month-html" in out.stdout


class TestBuildCli:
    def test_json_summary_and_exit_zero(self, events, tmp_path):
        ev_file = tmp_path / "events.json"
        ev_file.write_text(json.dumps(events, ensure_ascii=False), encoding="utf-8")
        job_dir = tmp_path / "job"
        out = subprocess.run(
            [sys.executable, str(SCRIPTS / "build.py"), str(ev_file),
             "--year", "2026", "--month", "8", "--title-prefix", "範例",
             "--job-dir", str(job_dir), "--json"],
            capture_output=True, text=True)
        assert out.returncode == 0, out.stderr
        summary = json.loads(out.stdout)
        assert summary["ok"] is True
        assert summary["artifacts"]["month-html"]["ok"] is True
        assert Path(summary["artifacts"]["month-html"]["path"]).exists()

    def test_rejects_non_array_events(self, tmp_path):
        ev_file = tmp_path / "events.json"
        ev_file.write_text('{"events": []}', encoding="utf-8")
        out = subprocess.run(
            [sys.executable, str(SCRIPTS / "build.py"), str(ev_file),
             "--year", "2026", "--month", "8", "--title-prefix", "範例",
             "--job-dir", str(tmp_path / "job")],
            capture_output=True, text=True)
        assert out.returncode != 0
        assert "陣列" in out.stderr

    def test_rejects_unknown_format(self, tmp_path):
        out = subprocess.run(
            [sys.executable, str(SCRIPTS / "build.py"), "x.json",
             "--year", "2026", "--month", "8", "--title-prefix", "範例",
             "--formats", "pdf"],
            capture_output=True, text=True)
        assert out.returncode != 0
        assert "未知格式" in out.stderr

    def test_print_range_needs_no_other_args(self):
        out = subprocess.run(
            [sys.executable, str(SCRIPTS / "build.py"),
             "--year", "2026", "--month", "8", "--print-range"],
            capture_output=True, text=True)
        assert out.returncode == 0, out.stderr
        assert out.stdout.strip() == "2026-08-01 2026-09-06"

    def test_print_range_json(self):
        out = subprocess.run(
            [sys.executable, str(SCRIPTS / "build.py"),
             "--year", "2026", "--month", "8", "--print-range", "--json"],
            capture_output=True, text=True)
        assert json.loads(out.stdout) == {"schema": "calendar-manager-py/range@1",
                                          "start": "2026-08-01", "end": "2026-09-06"}

    def test_missing_title_prefix_rejected_without_print_range(self, tmp_path):
        out = subprocess.run(
            [sys.executable, str(SCRIPTS / "build.py"), "x.json",
             "--year", "2026", "--month", "8"],
            capture_output=True, text=True)
        assert out.returncode != 0
        assert "--title-prefix" in out.stderr


class TestMediaCli:
    def _media(self, job_dir):
        return subprocess.run(
            [sys.executable, str(SCRIPTS / "job.py"), "media", str(job_dir)],
            capture_output=True, text=True)

    def test_no_verified_png_exits_nonzero(self, events, tmp_path):
        job_dir, _, _ = _run_build(events, tmp_path)
        out = self._media(job_dir)
        assert out.returncode == 1

    def test_prints_month_first_then_weeks(self, events, tmp_path):
        import pytest
        Image = pytest.importorskip("PIL.Image")
        job_dir, manifest, _ = _run_build(events, tmp_path)
        for aid, name in [("week-2-png", "w2.png"), ("month-png", "m.png"),
                          ("week-1-png", "w1.png")]:
            p = tmp_path / "job" / name
            im = Image.new("RGB", (700, 500), (255, 255, 255))
            im.putpixel((0, 0), (0, 0, 0))
            im.save(p)
            manifest.record(aid, str(p), "png", verify={"ok": True, "checks": []})
        manifest.save()
        out = self._media(job_dir)
        assert out.returncode == 0
        lines = out.stdout.strip().splitlines()
        assert [l.rsplit("/", 1)[-1] for l in lines] == ["m.png", "w1.png", "w2.png"]
        assert all(l.startswith("MEDIA:/") for l in lines)


class TestPngBranch:
    """The png half of build() without a real Chrome: the node call is faked,
    so the branch logic (placement, failure reporting, font flag) is what's
    under test — screenshot.js itself is covered by the live-run script."""

    def _fake_node(self, make_png=True, returncode=0):
        import pytest
        Image = pytest.importorskip("PIL.Image")

        def run(cmd, capture_output=True, text=True):
            import types
            if make_png:
                tmp_dir = Path(cmd[2])
                for html in tmp_dir.glob("*.html"):
                    im = Image.new("RGB", (700, 500), (255, 255, 255))
                    im.putpixel((1, 1), (0, 0, 0))
                    im.save(html.with_suffix(".png"))
            return types.SimpleNamespace(returncode=returncode, stdout="", stderr="")
        return run

    def test_png_recorded_and_verified(self, events, tmp_path, monkeypatch):
        monkeypatch.setattr(B.subprocess, "run", self._fake_node())
        job_dir = tmp_path / "job"
        manifest, results = B.build(events, str(job_dir), 2026, 8, "範例",
                                    ["html", "png"], skip_weeks=True)
        assert results["month-png"]["ok"], results
        entry = manifest.data["artifacts"]["month-png"]
        assert entry["verified"] is True
        assert Path(entry["path"]).exists()
        assert entry["path"].endswith("26年8月.png")
        assert not list((job_dir / ".tmp").glob("*.png"))  # staged copy moved out

    def test_screenshot_failure_is_reported_not_hidden(self, events, tmp_path, monkeypatch):
        monkeypatch.setattr(B.subprocess, "run",
                            self._fake_node(make_png=False, returncode=1))
        manifest, results = B.build(events, str(tmp_path / "job"), 2026, 8, "範例",
                                    ["html", "png"], skip_weeks=True)
        assert results["month-png"]["ok"] is False
        assert "month-png" not in manifest.data["artifacts"]  # 沒產出就不登記
        assert results["month-html"]["ok"]  # html half unaffected

    def test_font_preflight_blocks_before_browser(self, events, tmp_path, monkeypatch):
        import pytest
        monkeypatch.setattr(B.V, "cjk_font_check",
                            lambda: {"ok": False, "skipped": False, "detail": "no font"})
        launched = []
        monkeypatch.setattr(B.subprocess, "run",
                            lambda *a, **k: launched.append(1))
        with pytest.raises(SystemExit) as e:
            B.build(events, str(tmp_path / "job"), 2026, 8, "範例",
                    ["html", "png"], skip_weeks=True)
        assert e.value.code == 3
        assert launched == []  # 瀏覽器從未啟動

    def test_allow_missing_font_places_but_marks_unverified(self, events, tmp_path, monkeypatch):
        monkeypatch.setattr(B.V, "cjk_font_check",
                            lambda: {"ok": False, "skipped": False, "detail": "no font"})
        monkeypatch.setattr(B.subprocess, "run", self._fake_node())
        manifest, results = B.build(events, str(tmp_path / "job"), 2026, 8, "範例",
                                    ["html", "png"], skip_weeks=True,
                                    allow_missing_font=True)
        entry = manifest.data["artifacts"]["month-png"]
        assert Path(entry["path"]).exists()      # 搬進去方便查看
        assert entry["verified"] is False        # 但標記未通過
        assert results["month-png"]["ok"] is False


class TestBuildFailurePath:
    def test_failing_html_verify_fails_the_build(self, events, tmp_path, monkeypatch):
        monkeypatch.setattr(B.V, "verify_html",
                            lambda *a, **k: {"ok": False, "checks": [], "detail": "forced"})
        manifest, results = B.build(events, str(tmp_path / "job"), 2026, 8, "範例",
                                    ["html"], skip_weeks=True)
        assert results["month-html"]["ok"] is False
        assert manifest.data["artifacts"]["month-html"]["verified"] is False
        assert not all(r["ok"] for r in results.values())  # CLI 據此回非零


class TestApplyPlanRange:
    def test_range_over_ops(self, tmp_path):
        plan = {"calendar": "c", "backend": "google", "operations": [
            {"op": "create", "summary": "a", "location": "x",
             "start": "2026-08-03 09:00", "end": "2026-08-03 10:00"},
            {"op": "create", "summary": "b", "location": "x",
             "start": "2026-07-30 09:00", "end": "2026-07-30 10:00"}]}
        f = tmp_path / "plan.json"
        f.write_text(json.dumps(plan, ensure_ascii=False), encoding="utf-8")
        out = subprocess.run(
            [sys.executable, str(SCRIPTS / "apply_plan.py"), "range", str(f)],
            capture_output=True, text=True)
        assert out.returncode == 0, out.stderr
        assert out.stdout.strip() == "2026-07-30 2026-08-03"


class TestApplyPlanCheck:
    """The backend-agnostic read-back verification."""

    def _check(self, tmp_path, plan, events):
        plan_f = tmp_path / "plan.json"
        plan_f.write_text(json.dumps(plan, ensure_ascii=False), encoding="utf-8")
        ev_f = tmp_path / "fetched.json"
        ev_f.write_text(json.dumps(events, ensure_ascii=False), encoding="utf-8")
        return subprocess.run(
            [sys.executable, str(SCRIPTS / "apply_plan.py"), "check",
             str(plan_f), str(ev_f)],
            capture_output=True, text=True)

    def test_present_event_passes(self, tmp_path, events):
        plan = {"calendar": "c", "backend": "google", "operations": [
            {"op": "create", "summary": "部門月會", "location": "地點A",
             "start": "2026-08-03 09:00", "end": "2026-08-03 10:00"}]}
        out = self._check(tmp_path, plan, events)
        assert out.returncode == 0, out.stderr

    def test_missing_event_fails(self, tmp_path, events):
        plan = {"calendar": "c", "backend": "google", "operations": [
            {"op": "create", "summary": "沒寫進去的會", "location": "地點A",
             "start": "2026-08-03 09:00", "end": "2026-08-03 10:00"}]}
        out = self._check(tmp_path, plan, events)
        assert out.returncode == 1
        assert "找不到" in out.stderr

    def test_all_day_create_matches_date_shape(self, tmp_path, events):
        plan = {"calendar": "c", "backend": "google", "operations": [
            {"op": "create", "summary": "教育訓練", "location": "北京",
             "start": "2026-08-12", "all_day": True}]}
        out = self._check(tmp_path, plan, events)
        assert out.returncode == 0, out.stderr

    def test_location_mismatch_reports_connector_quirk(self, tmp_path, events):
        plan = {"calendar": "c", "backend": "google", "operations": [
            {"op": "create", "summary": "部門月會", "location": "別的地方",
             "start": "2026-08-03 09:00", "end": "2026-08-03 10:00"}]}
        out = self._check(tmp_path, plan, events)
        assert out.returncode == 1
        assert "location" in out.stderr

    def test_apply_dry_run_writes_nothing(self, tmp_path, plan):
        plan_f = tmp_path / "plan.json"
        plan_f.write_text(json.dumps(plan, ensure_ascii=False), encoding="utf-8")
        out = subprocess.run(
            [sys.executable, str(SCRIPTS / "apply_plan.py"), "apply",
             str(plan_f), "--dry-run"],
            capture_output=True, text=True)
        assert out.returncode == 0, out.stderr
        assert "dry-run" in out.stderr
        assert not (tmp_path / "apply-report.json").exists()

    def test_apply_refuses_google_backend(self, tmp_path, plan):
        plan["backend"] = "google"
        plan_f = tmp_path / "plan.json"
        plan_f.write_text(json.dumps(plan, ensure_ascii=False), encoding="utf-8")
        out = subprocess.run(
            [sys.executable, str(SCRIPTS / "apply_plan.py"), "apply", str(plan_f)],
            capture_output=True, text=True)
        assert out.returncode != 0
        assert "check" in out.stderr  # points at the check flow instead
