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
