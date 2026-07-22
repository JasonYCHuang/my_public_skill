"""輸入/輸出檔案契約：events 進場驗證、plan 自我標識、輸出 schema 檔、
統一的 --json 信封（{"schema": ..., "ok": ...}）。"""
import json
import subprocess
import sys
from pathlib import Path

import pytest

import build as B
from validate_events import validate as validate_events
from validate_plan import PLAN_SCHEMA_ID, validate as validate_plan

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
ASSETS = Path(__file__).resolve().parent.parent / "assets"


# ---------------------------------------------------------------------------
# 輸入：events.json
# ---------------------------------------------------------------------------

class TestValidateEvents:
    def test_good_events_pass(self, events):
        assert validate_events(events) == []

    def test_empty_list_is_legal(self):
        assert validate_events([]) == []  # 空月份也要能產出空月曆

    def test_extra_fields_allowed(self, events):
        events[0]["htmlLink"] = "https://..."  # Google 會多給很多欄位
        events[0]["uid"] = "x"
        assert validate_events(events) == []

    def test_not_a_list(self):
        assert any("陣列" in e for e in validate_events({"events": []}))

    def test_missing_start(self, events):
        del events[0]["start"]
        assert any("第1筆" in e and "start" in e for e in validate_events(events))

    def test_bad_date_format(self, events):
        events[2]["start"] = {"date": "2026/08/12"}
        assert any("YYYY-MM-DD" in e for e in validate_events(events))

    def test_bad_datetime_format(self, events):
        events[0]["start"] = {"dateTime": "2026-08-03 09:00"}
        assert any("ISO 8601" in e for e in validate_events(events))

    def test_end_before_start(self, events):
        events[0]["end"] = {"dateTime": "2026-08-03T08:00:00+08:00"}
        assert any("end 早於 start" in e for e in validate_events(events))

    def test_non_dict_item(self):
        assert any("物件" in e for e in validate_events(["oops"]))

    def test_build_gate_rejects_bad_events(self, events, tmp_path):
        events[0].pop("start")
        ev_file = tmp_path / "events.json"
        ev_file.write_text(json.dumps(events, ensure_ascii=False), encoding="utf-8")
        out = subprocess.run(
            [sys.executable, str(SCRIPTS / "build.py"), str(ev_file),
             "--year", "2026", "--month", "8", "--title-prefix", "範例",
             "--job-dir", str(tmp_path / "job")],
            capture_output=True, text=True)
        assert out.returncode != 0
        assert "第1筆" in out.stderr
        assert not (tmp_path / "job").exists()  # 未產生任何檔案

    def test_schema_file_agrees(self, events):
        jsonschema = pytest.importorskip("jsonschema")
        schema = json.loads((ASSETS / "events.schema.json").read_text(encoding="utf-8"))
        jsonschema.Draft202012Validator(schema).validate(events)


# ---------------------------------------------------------------------------
# 輸入：plan.json 自我標識
# ---------------------------------------------------------------------------

class TestPlanSchemaField:
    def test_parser_emits_schema_id(self, tmp_path):
        out = subprocess.run(
            [sys.executable, str(SCRIPTS / "parse_entries.py"), "-",
             "--calendar", "c", "--year", "2026", "--json"],
            input="7/15 1930 深圳 chap 04\n", capture_output=True, text=True)
        assert json.loads(out.stdout)["plan"]["schema"] == PLAN_SCHEMA_ID

    def test_schema_field_accepted(self, plan):
        plan["schema"] = PLAN_SCHEMA_ID
        from validate_plan import normalize
        normalize(plan)
        errors, _ = validate_plan(plan)
        assert errors == []

    def test_wrong_schema_id_rejected(self, plan):
        plan["schema"] = "somebody-else/plan@9"
        errors, _ = validate_plan(plan)
        assert any("schema" in e for e in errors)


# ---------------------------------------------------------------------------
# 輸出：manifest / apply-report 契約
# ---------------------------------------------------------------------------

class TestOutputSchemas:
    def test_real_manifest_validates(self, events, tmp_path):
        jsonschema = pytest.importorskip("jsonschema")
        manifest, _ = B.build(events, str(tmp_path / "job"), 2026, 8, "範例", ["html"])
        schema = json.loads((ASSETS / "manifest.schema.json").read_text(encoding="utf-8"))
        data = json.loads(Path(manifest.path).read_text(encoding="utf-8"))
        jsonschema.Draft202012Validator(schema).validate(data)

    def test_apply_report_shape_matches_schema(self):
        """apply 需要活的 CalDAV 才能跑；這裡驗 schema 與 cmd_apply 寫出的
        欄位集合一致（鍵名直接取自 apply_plan.py 的 report 建構）。"""
        jsonschema = pytest.importorskip("jsonschema")
        schema = json.loads((ASSETS / "apply-report.schema.json").read_text(encoding="utf-8"))
        representative = {
            "schema": "calendar-manager-py/apply-report@1",
            "plan": "/abs/plan.json", "calendar": "c", "backend": "icloud",
            "applied_at": "2026-07-22T10:00:00+08:00", "ok": True,
            "operations": [{"index": 1, "op": "create", "summary": "會",
                            "uid": "u1", "ok": True, "detail": "讀回一致"}],
        }
        jsonschema.Draft202012Validator(schema).validate(representative)
        src = (SCRIPTS / "apply_plan.py").read_text(encoding="utf-8")
        assert 'calendar-manager-py/apply-report@1' in src


# ---------------------------------------------------------------------------
# 輸出：--json 信封統一（schema + ok）
# ---------------------------------------------------------------------------

class TestJsonEnvelopes:
    def _run(self, *argv, stdin=None):
        out = subprocess.run([sys.executable, *argv], input=stdin,
                             capture_output=True, text=True)
        return json.loads(out.stdout)

    def test_build_result(self, events, tmp_path):
        ev = tmp_path / "e.json"
        ev.write_text(json.dumps(events), encoding="utf-8")
        data = self._run(str(SCRIPTS / "build.py"), str(ev), "--year", "2026",
                         "--month", "8", "--title-prefix", "範例",
                         "--job-dir", str(tmp_path / "job"), "--json")
        assert data["schema"] == "calendar-manager-py/build-result@1"
        assert data["ok"] is True

    def test_parse_result(self):
        data = self._run(str(SCRIPTS / "parse_entries.py"), "-",
                         "--calendar", "c", "--year", "2026", "--json",
                         stdin="7/15 1930 深圳 x\n")
        assert data["schema"] == "calendar-manager-py/parse-result@1"
        assert "ok" in data

    def test_validate_result(self, plan, tmp_path):
        f = tmp_path / "plan.json"
        f.write_text(json.dumps(plan, ensure_ascii=False), encoding="utf-8")
        data = self._run(str(SCRIPTS / "validate_plan.py"), str(f), "--json")
        assert data["schema"] == "calendar-manager-py/validate-result@1"

    def test_doctor_result(self):
        data = self._run(str(SCRIPTS / "doctor.py"), "--backend", "none", "--json")
        assert data["schema"] == "calendar-manager-py/doctor-result@1"
        assert "ok" in data and "checks" in data

    def test_check_result(self, events, tmp_path):
        plan = {"calendar": "c", "backend": "google", "operations": [
            {"op": "create", "summary": "部門月會", "location": "地點A",
             "start": "2026-08-03 09:00", "end": "2026-08-03 10:00"}]}
        pf, ef = tmp_path / "p.json", tmp_path / "e.json"
        pf.write_text(json.dumps(plan, ensure_ascii=False), encoding="utf-8")
        ef.write_text(json.dumps(events, ensure_ascii=False), encoding="utf-8")
        data = self._run(str(SCRIPTS / "apply_plan.py"), "check",
                         str(pf), str(ef), "--json")
        assert data["schema"] == "calendar-manager-py/check-result@1"
        assert data["ok"] is True

    def test_range_result(self, tmp_path):
        plan = {"calendar": "c", "backend": "google", "operations": [
            {"op": "create", "summary": "a", "location": "x",
             "start": "2026-08-03 09:00", "end": "2026-08-03 10:00"}]}
        f = tmp_path / "p.json"
        f.write_text(json.dumps(plan, ensure_ascii=False), encoding="utf-8")
        data = self._run(str(SCRIPTS / "apply_plan.py"), "range", str(f), "--json")
        assert data["schema"] == "calendar-manager-py/range@1"

    def test_validate_events_result(self, events, tmp_path):
        f = tmp_path / "e.json"
        f.write_text(json.dumps(events, ensure_ascii=False), encoding="utf-8")
        data = self._run(str(SCRIPTS / "validate_events.py"), str(f), "--json")
        assert data["schema"] == "calendar-manager-py/validate-events-result@1"
        assert data["ok"] is True
