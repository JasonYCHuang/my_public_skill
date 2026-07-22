"""The write-path boundary: normalize() fills what a machine can decide,
validate() enforces what used to be prose rules in the parent SKILL.md."""
import pytest

from validate_plan import normalize, validate


def _ok(plan):
    errors, warnings = validate(plan)
    assert errors == [], errors
    return warnings


# ---------------------------------------------------------------------------
# normalize
# ---------------------------------------------------------------------------

class TestNormalize:
    def test_fills_end_from_default_duration(self, plan):
        plan["operations"] = [{"op": "create", "summary": "會", "location": "地點A",
                               "start": "2026-08-02 09:00"}]
        notes = normalize(plan)
        assert plan["operations"][0]["end"] == "2026-08-02 10:00"
        assert len(notes) == 1

    def test_respects_custom_duration(self, plan):
        plan["default_duration_minutes"] = 90
        plan["operations"] = [{"op": "create", "summary": "會", "location": "地點A",
                               "start": "2026-08-02 23:00"}]
        normalize(plan)
        assert plan["operations"][0]["end"] == "2026-08-03 00:30"  # 跨日也要對

    def test_expands_all_day_to_convention(self, plan):
        normalize(plan)
        op = plan["operations"][1]
        assert op["start"] == "2026-08-05 00:00"
        assert op["end"] == "2026-08-05 23:59"

    def test_keeps_explicit_end(self, plan):
        normalize(plan)
        assert plan["operations"][0]["end"] == "2026-08-02 10:00"

    def test_leaves_malformed_input_for_validate(self, plan):
        plan["operations"] = [{"op": "create", "summary": "會", "location": "x",
                               "start": "not-a-time"}]
        notes = normalize(plan)
        assert notes == []
        assert "end" not in plan["operations"][0]


# ---------------------------------------------------------------------------
# validate — structure
# ---------------------------------------------------------------------------

class TestStructure:
    def test_valid_plan_passes(self, plan):
        normalize(plan)
        _ok(plan)

    def test_missing_calendar(self, plan):
        del plan["calendar"]
        errors, _ = validate(plan)
        assert any("calendar" in e for e in errors)

    def test_bad_backend(self, plan):
        plan["backend"] = "outlook"
        errors, _ = validate(plan)
        assert any("backend" in e for e in errors)

    def test_bad_duration(self, plan):
        plan["default_duration_minutes"] = 0
        errors, _ = validate(plan)
        assert any("default_duration_minutes" in e for e in errors)

    def test_unknown_top_level_key(self, plan):
        plan["extra"] = 1
        errors, _ = validate(plan)
        assert any("extra" in e for e in errors)

    def test_empty_operations(self, plan):
        plan["operations"] = []
        errors, _ = validate(plan)
        assert any("operations" in e for e in errors)

    def test_unknown_op(self, plan):
        plan["operations"] = [{"op": "upsert", "summary": "x"}]
        errors, _ = validate(plan)
        assert any("upsert" in e for e in errors)


class TestCreateRules:
    def _one(self, plan, op):
        plan["operations"] = [op]
        return plan

    def test_missing_required_fields(self, plan):
        errors, _ = validate(self._one(plan, {"op": "create", "summary": "x"}))
        assert any("location" in e for e in errors)
        assert any("start" in e for e in errors)

    def test_empty_summary(self, plan):
        errors, _ = validate(self._one(plan, {
            "op": "create", "summary": " ", "location": "x", "start": "2026-08-02 09:00"}))
        assert any("summary" in e for e in errors)

    def test_bad_start_format(self, plan):
        errors, _ = validate(self._one(plan, {
            "op": "create", "summary": "會", "location": "x", "start": "2026/08/02 0900"}))
        assert any("start" in e for e in errors)

    def test_end_not_after_start(self, plan):
        errors, _ = validate(self._one(plan, {
            "op": "create", "summary": "會", "location": "x",
            "start": "2026-08-02 09:00", "end": "2026-08-02 09:00"}))
        assert any("之後" in e for e in errors)

    def test_date_only_start_needs_all_day(self, plan):
        errors, _ = validate(self._one(plan, {
            "op": "create", "summary": "會", "location": "x", "start": "2026-08-02"}))
        assert any("all_day" in e for e in errors)

    def test_empty_location_warns_not_errors(self, plan):
        plan = self._one(plan, {"op": "create", "summary": "會", "location": "",
                                "start": "2026-08-02 09:00", "end": "2026-08-02 10:00"})
        errors, warnings = validate(plan)
        assert errors == []
        assert any("location 為空" in w for w in warnings)


class TestUpdateDeleteRules:
    def test_update_needs_uid(self, plan):
        plan["operations"] = [{"op": "update", "summary": "x"}]
        errors, _ = validate(plan)
        assert any("uid" in e for e in errors)

    def test_update_needs_some_field(self, plan):
        plan["operations"] = [{"op": "update", "uid": "u1"}]
        errors, _ = validate(plan)
        assert any("要改的欄位" in e for e in errors)

    def test_update_time_sanity(self, plan):
        plan["operations"] = [{"op": "update", "uid": "u1",
                               "start": "2026-08-02 10:00", "end": "2026-08-02 09:00"}]
        errors, _ = validate(plan)
        assert any("之後" in e for e in errors)

    def test_delete_needs_uid(self, plan):
        plan["operations"] = [{"op": "delete"}]
        errors, _ = validate(plan)
        assert any("uid" in e for e in errors)


# ---------------------------------------------------------------------------
# the cross-day typo detector — the "chap 05 two days running" incident
# ---------------------------------------------------------------------------

def _create(summary, start, loc="在家"):
    # end omitted on purpose — _series_plan's normalize() fills it.
    return {"op": "create", "summary": summary, "location": loc, "start": start}


def _series_plan(plan, *ops):
    plan["operations"] = list(ops)
    normalize(plan)
    return plan


class TestTypoDetection:
    def test_exact_duplicate_is_error(self, plan):
        plan["operations"] = [
            {"op": "create", "summary": "會", "location": "x",
             "start": "2026-08-02 09:00", "end": "2026-08-02 10:00"},
            {"op": "create", "summary": "會", "location": "x",
             "start": "2026-08-02 09:00", "end": "2026-08-02 10:00"},
        ]
        errors, _ = validate(plan)
        assert any("完全重複" in e for e in errors)

    def test_repeated_chapter_number_warns(self, plan):
        p = _series_plan(plan,
                         _create("晚間讀書會 chap 04", "2026-08-17 19:30"),
                         _create("晚間讀書會 chap 05", "2026-08-18 19:30"),
                         _create("晚間讀書會 chap 05", "2026-08-19 19:30"))
        warnings = _ok(p)
        assert any("編號相同" in w for w in warnings)

    def test_monotonic_series_is_quiet(self, plan):
        p = _series_plan(plan,
                         _create("晚間讀書會 chap 04", "2026-08-17 19:30"),
                         _create("晚間讀書會 chap 05", "2026-08-18 19:30"),
                         _create("晚間讀書會 chap 06", "2026-08-19 19:30"))
        warnings = _ok(p)
        assert not any("編號" in w for w in warnings)

    def test_backwards_series_warns(self, plan):
        p = _series_plan(plan,
                         _create("週報 07", "2026-08-17 09:00"),
                         _create("週報 06", "2026-08-18 09:00"))
        warnings = _ok(p)
        assert any("未隨日期遞增" in w for w in warnings)

    def test_same_summary_multi_day_warns(self, plan):
        p = _series_plan(plan,
                         _create("例行晨會", "2026-08-17 08:00"),
                         _create("例行晨會", "2026-08-18 08:00"))
        warnings = _ok(p)
        assert any("跨日同摘要" in w for w in warnings)


# ---------------------------------------------------------------------------
# schema file agreement (when jsonschema is installed)
# ---------------------------------------------------------------------------

def test_schema_accepts_valid_plan(plan):
    jsonschema = pytest.importorskip("jsonschema")
    import json
    from validate_plan import SCHEMA_PATH
    with open(SCHEMA_PATH, encoding="utf-8") as f:
        schema = json.load(f)
    normalize(plan)
    jsonschema.Draft202012Validator(schema).validate(plan)
