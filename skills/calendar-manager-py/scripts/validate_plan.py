#!/usr/bin/env python3
"""
Validate (and normalize) a plan.json — the LLM/Python boundary of the write
path.

The model's soft half: read the user's 時間、地點、事項, ask when a field is
missing or ambiguous (never guess, never silently reuse a neighbour's
location), and put the result into a plan.json (contract:
../assets/plan.schema.json). The hard half starts here: everything below is
a mechanical rule the parent skill's SKILL.md used to state as prose for the
model to remember, now enforced on every run:

- **Structure + time sanity** (errors — block apply): required fields per
  op, `YYYY-MM-DD HH:MM` format, end after start, all_day given as a date.
- **Exact duplicates** (error): two creates with the same summary and start
  are almost always the same user line pasted twice.
- **The cross-day typo pattern** (warnings — must be relayed, don't block):
  the parent skill's "chap 05 two days running" incident. Same summary on
  several days, or a numbered series (…04, …05, …05) that repeats or runs
  backwards, gets flagged *before* anything is written, instead of being
  chased down later as "why does my 日誌 show the same chapter twice?".
- **Empty location** (warning): "" means "confirmed there is no location",
  not "didn't ask" — the warning is the nudge to make sure it was the former.

normalize() fills the machine-decidable bits first, so the model doesn't
carry them: a missing end becomes start + default_duration_minutes, and an
all_day create becomes the 00:00–23:59 convention the iCloud backend uses.

    python3 validate_plan.py plan.json [--json]

Exit 0 = no errors (warnings alone don't fail). Library use: normalize(plan)
then validate(plan) -> (errors, warnings).
"""
import json
import os
import re
import sys
from datetime import datetime, timedelta

_HERE = os.path.dirname(os.path.abspath(__file__))
SCHEMA_PATH = os.path.join(_HERE, "..", "assets", "plan.schema.json")

PLAN_SCHEMA_ID = "calendar-manager-py/plan@1"
DT_FMT = "%Y-%m-%d %H:%M"
DT_RE = re.compile(r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}$")
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
BACKENDS = ("icloud", "google", "other")


def _parse_dt(s):
    return datetime.strptime(s, DT_FMT)


# ---------------------------------------------------------------------------
# normalize — fill what a machine can decide
# ---------------------------------------------------------------------------

def normalize(plan):
    """Mutates plan in place; returns a list of human-readable notes about
    what was filled. Runs before validate. Only touches well-formed parts —
    anything malformed is left for validate to report."""
    notes = []
    duration = plan.get("default_duration_minutes", 60)
    if not isinstance(duration, int) or duration < 1:
        return notes  # validate will flag it
    for i, op in enumerate(plan.get("operations") or [], start=1):
        if not isinstance(op, dict) or op.get("op") != "create":
            continue
        start = op.get("start")
        if op.get("all_day"):
            if isinstance(start, str) and DATE_RE.match(start):
                op["start"] = f"{start} 00:00"
                op["end"] = f"{start} 23:59"
                notes.append(f"op#{i}：全天事件展開為 {start} 00:00–23:59")
            continue
        if not op.get("end") and isinstance(start, str) and DT_RE.match(start):
            end = _parse_dt(start) + timedelta(minutes=duration)
            op["end"] = end.strftime(DT_FMT)
            notes.append(f"op#{i}：未給結束時間，依預設時長 {duration} 分鐘填入 {op['end']}")
    return notes


# ---------------------------------------------------------------------------
# validate
# ---------------------------------------------------------------------------

def _validate_create(i, op, errors, warnings):
    for field in ("summary", "location", "start"):
        if field not in op:
            errors.append(f"op#{i}（create）缺少必填欄位 {field}")
    summary = op.get("summary")
    if summary is not None and not str(summary).strip():
        errors.append(f"op#{i}：summary 不可為空")
    if "location" in op and not str(op.get("location") or "").strip():
        warnings.append(
            f"op#{i}「{summary}」：location 為空。空地點必須代表「確認過沒有地點」，"
            "不能是「使用者沒說、也沒問」——缺地點要先問人。")
    start, end = op.get("start"), op.get("end")
    if isinstance(start, str) and DATE_RE.match(start) and not op.get("all_day"):
        errors.append(f"op#{i}：start 只有日期沒有時間；全天事件請設 all_day: true")
    if isinstance(start, str) and not (DT_RE.match(start) or DATE_RE.match(start)):
        errors.append(f"op#{i}：start「{start}」不是 YYYY-MM-DD HH:MM 格式")
    if end:
        if not DT_RE.match(str(end)):
            errors.append(f"op#{i}：end「{end}」不是 YYYY-MM-DD HH:MM 格式")
        elif isinstance(start, str) and DT_RE.match(start):
            if _parse_dt(str(end)) <= _parse_dt(start):
                errors.append(f"op#{i}「{summary}」：結束時間 {end} 不在開始時間 {start} 之後")


def _validate_update(i, op, errors):
    if not str(op.get("uid") or "").strip():
        errors.append(f"op#{i}（update）缺少 uid")
    if not any(k in op for k in ("summary", "location", "start", "end")):
        errors.append(f"op#{i}（update）沒有任何要改的欄位")
    for k in ("start", "end"):
        v = op.get(k)
        if v is not None and not DT_RE.match(str(v)):
            errors.append(f"op#{i}：{k}「{v}」不是 YYYY-MM-DD HH:MM 格式")
    if op.get("start") and op.get("end"):
        if _parse_dt(op["end"]) <= _parse_dt(op["start"]):
            errors.append(f"op#{i}：結束時間不在開始時間之後")


_NUM_RE = re.compile(r"\d+")


def _series_warnings(creates, warnings):
    """The cross-day typo detector. Groups creates whose summaries are
    identical once digits are masked; inside a group, the numbers should not
    repeat, and when the events are on distinct days the numbers should move
    in the same direction as the dates."""
    groups = {}
    for i, op in creates:
        summary = str(op.get("summary") or "")
        masked = _NUM_RE.sub("#", summary)
        groups.setdefault(masked, []).append((i, op, summary))

    for masked, items in groups.items():
        if len(items) < 2:
            continue
        # same summary + same start = pasted twice -> error-level is handled
        # by the exact-duplicate check; here we look at the series shape.
        days = {}
        for i, op, summary in items:
            day = str(op.get("start") or "")[:10]
            days.setdefault(day, []).append((i, summary))
        for day, hits in days.items():
            if len(hits) > 1:
                ops = ", ".join(f"op#{i}「{s}」" for i, s in hits)
                warnings.append(f"同一天（{day}）出現多筆同型摘要：{ops}——確認不是重複輸入。")
        if "#" not in masked:
            if len(days) > 1:
                ops = ", ".join(f"op#{i}" for i, _, _ in items)
                warnings.append(
                    f"「{items[0][2]}」在 {len(days)} 天出現（{ops}）——跨日同摘要，確認是刻意重複。")
            continue
        # numbered series: numbers should not repeat across different days
        by_day = sorted((day, hits[0]) for day, hits in days.items())
        nums = []
        for day, (i, summary) in by_day:
            m = _NUM_RE.findall(summary)
            nums.append((day, i, tuple(int(x) for x in m)))
        seen = {}
        for day, i, tup in nums:
            if tup in seen:
                j, prev_day = seen[tup]
                warnings.append(
                    f"op#{i}（{day}）與 op#{j}（{prev_day}）的編號相同"
                    f"（{'/'.join(map(str, tup))}）——「連三天同一章」的跨日 typo 模式，向使用者確認。")
            else:
                seen[tup] = (i, day)
        ordered = [tup for _, _, tup in nums]
        if len(set(ordered)) == len(ordered) and ordered != sorted(ordered):
            warnings.append(
                f"「{masked}」系列的編號未隨日期遞增（{ordered}）——確認不是打錯天或打錯號。")


def validate(plan):
    """-> (errors, warnings). Errors block apply; warnings must be relayed to
    the user but don't block."""
    errors, warnings = [], []
    if not isinstance(plan, dict):
        return ["plan 最外層必須是物件"], []

    if not str(plan.get("calendar") or "").strip():
        errors.append("缺少 calendar（iCloud 行事曆顯示名稱或 Google calendarId）")
    backend = plan.get("backend", "icloud")
    if backend not in BACKENDS:
        errors.append(f"backend「{backend}」不在 {BACKENDS}")
    duration = plan.get("default_duration_minutes", 60)
    if not isinstance(duration, int) or not (1 <= duration <= 1440):
        errors.append(f"default_duration_minutes「{duration}」必須是 1–1440 的整數")

    known_keys = {"schema", "calendar", "backend", "default_duration_minutes", "operations"}
    for k in plan:
        if k not in known_keys:
            errors.append(f"未知的欄位「{k}」（允許：{'、'.join(sorted(known_keys))}）")
    if "schema" in plan and plan["schema"] != PLAN_SCHEMA_ID:
        errors.append(f"schema「{plan['schema']}」不是 {PLAN_SCHEMA_ID}")

    ops = plan.get("operations")
    if not isinstance(ops, list) or not ops:
        errors.append("operations 必須是非空陣列")
        return errors, warnings

    creates = []
    seen_create = {}
    for i, op in enumerate(ops, start=1):
        if not isinstance(op, dict):
            errors.append(f"op#{i} 必須是物件")
            continue
        kind = op.get("op")
        if kind == "create":
            _validate_create(i, op, errors, warnings)
            creates.append((i, op))
            key = (str(op.get("summary")), str(op.get("start")))
            if key in seen_create:
                errors.append(
                    f"op#{i} 與 op#{seen_create[key]} 完全重複（同摘要同開始時間）——同一行貼了兩次？")
            else:
                seen_create[key] = i
        elif kind == "update":
            _validate_update(i, op, errors)
        elif kind == "delete":
            if not str(op.get("uid") or "").strip():
                errors.append(f"op#{i}（delete）缺少 uid")
        else:
            errors.append(f"op#{i}：op「{kind}」不是 create/update/delete")

    _series_warnings(creates, warnings)

    # jsonschema is the documented contract; run it too when installed, so a
    # drift between this validator and the schema file surfaces as an error.
    try:
        import jsonschema
        with open(SCHEMA_PATH, encoding="utf-8") as f:
            schema = json.load(f)
        v = jsonschema.Draft202012Validator(schema)
        for err in v.iter_errors(plan):
            msg = f"schema：{'/'.join(str(p) for p in err.absolute_path) or '(root)'}：{err.message}"
            if msg not in errors:
                errors.append(msg)
    except ImportError:
        pass

    return errors, warnings


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    import argparse
    ap = argparse.ArgumentParser(description="Normalize + validate a plan.json")
    ap.add_argument("plan_json")
    ap.add_argument("--json", action="store_true", help="機器可讀輸出")
    args = ap.parse_args()

    with open(args.plan_json, encoding="utf-8") as f:
        plan = json.load(f)
    notes = normalize(plan)
    errors, warnings = validate(plan)

    if args.json:
        print(json.dumps({"schema": "calendar-manager-py/validate-result@1",
                          "ok": not errors, "notes": notes,
                          "errors": errors, "warnings": warnings},
                         ensure_ascii=False, indent=2))
    else:
        for n in notes:
            print(f"ℹ️  {n}")
        for w in warnings:
            print(f"⚠️  {w}")
        for e in errors:
            print(f"❌ {e}")
        print("驗證通過。" if not errors else f"驗證失敗（{len(errors)} 項錯誤）。")
    sys.exit(0 if not errors else 1)


if __name__ == "__main__":
    main()
