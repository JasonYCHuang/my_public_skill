#!/usr/bin/env python3
"""
Validate an events array against the rendering-input contract
(../assets/events.schema.json) — the pivot format both backends feed into
build.py. Before this gate existed, a malformed event (missing start, a bare
string date) surfaced as a KeyError mid-render or a silently wrong page.

    python3 validate_events.py events.json [--json]

Library use: validate(events) -> errors (list of "第N筆：…" strings).
Hand-rolled checks always run (no hard dependency); jsonschema additionally
runs against the schema file when installed, so validator/schema drift
surfaces as an error.
"""
import json
import os
import re
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
SCHEMA_PATH = os.path.join(_HERE, "..", "assets", "events.schema.json")
SCHEMA_ID = "calendar-manager-py/events@1"

DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
DATETIME_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}")


def _check_when(i, ev, field, errors):
    w = ev.get(field)
    if not isinstance(w, dict):
        errors.append(f"第{i}筆：缺 {field}（需為含 date 或 dateTime 的物件）")
        return
    if "date" in w:
        if not (isinstance(w["date"], str) and DATE_RE.match(w["date"])):
            errors.append(f"第{i}筆：{field}.date「{w['date']}」不是 YYYY-MM-DD")
    elif "dateTime" in w:
        if not (isinstance(w["dateTime"], str) and DATETIME_RE.match(w["dateTime"])):
            errors.append(f"第{i}筆：{field}.dateTime「{w['dateTime']}」不是 ISO 8601")
    else:
        errors.append(f"第{i}筆：{field} 缺 date/dateTime")


def validate(events):
    """-> errors。空陣列合法（該月沒事件也要能產出空月曆）。"""
    if not isinstance(events, list):
        return ["events 最外層必須是事件陣列本身（不是包在物件裡）"]
    errors = []
    for i, ev in enumerate(events, start=1):
        if not isinstance(ev, dict):
            errors.append(f"第{i}筆：必須是物件")
            continue
        if "summary" in ev and not isinstance(ev["summary"], str):
            errors.append(f"第{i}筆：summary 必須是字串")
        if "location" in ev and not isinstance(ev.get("location"), (str, type(None))):
            errors.append(f"第{i}筆：location 必須是字串或 null")
        _check_when(i, ev, "start", errors)
        _check_when(i, ev, "end", errors)
        st, en = ev.get("start"), ev.get("end")
        if (isinstance(st, dict) and isinstance(en, dict)
                and "dateTime" in st and "dateTime" in en
                and DATETIME_RE.match(str(st["dateTime"]))
                and DATETIME_RE.match(str(en["dateTime"]))
                and en["dateTime"] < st["dateTime"]):
            errors.append(f"第{i}筆：end 早於 start")

    try:
        import jsonschema
        with open(SCHEMA_PATH, encoding="utf-8") as f:
            schema = json.load(f)
        for err in jsonschema.Draft202012Validator(schema).iter_errors(events):
            path = "/".join(str(p) for p in err.absolute_path) or "(root)"
            msg = f"schema：{path}：{err.message}"
            if msg not in errors:
                errors.append(msg)
    except ImportError:
        pass
    return errors


def main():
    import argparse
    ap = argparse.ArgumentParser(description="Validate an events.json")
    ap.add_argument("events_json")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()
    with open(args.events_json, encoding="utf-8") as f:
        events = json.load(f)
    errors = validate(events)
    if args.json:
        print(json.dumps({"schema": "calendar-manager-py/validate-events-result@1",
                          "ok": not errors, "errors": errors},
                         ensure_ascii=False, indent=2))
    else:
        for e in errors:
            print(f"❌ {e}")
        print("驗證通過。" if not errors else f"驗證失敗（{len(errors)} 項）。")
    sys.exit(0 if not errors else 1)


if __name__ == "__main__":
    main()
