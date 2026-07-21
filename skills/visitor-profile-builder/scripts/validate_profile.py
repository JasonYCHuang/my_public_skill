#!/usr/bin/env python3
"""
Validate a profile.json against assets/profile.schema.json before rendering.

Both generators call validate() at startup, so a malformed profile is caught
before it becomes a mis-laid-out xlsx or a PNG with an orphaned stat tile.

The 訪客信息 record is a closed set of 10 fields (see the schema's
x-field-no annotations). Unknown keys are rejected, all 10 must be present,
and a field with no data holds the literal string "-".

Two severities, deliberately:

  errors   -- the record breaks the field contract or the rendered layout.
              Generation stops.
  warnings -- editorial: the output is valid but unusually long, or carries
              data the chosen format will silently drop. Generation continues.

Where a ceiling was given as a hard requirement (positions ≤3, career ≤10)
it is an error. Where it is only an editorial preference (education) it is a
warning — a real person can legitimately have more degrees than expected,
and hard-failing that would push people to edit the schema or drop true data.

Usage:
    python3 validate_profile.py <profile.json> [--target html|xlsx] [--strict]

    --target   also report fields that the given output format drops
               (x-target in the schema)
    --strict   treat warnings as errors (exit 1)
"""
import argparse
import json
import os
import sys

SCHEMA_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "assets", "profile.schema.json",
)

# "-" is the one sanctioned way to say "no data" (matching the original
# 個人信息登記表 seed files). The point is that empty cells stay greppable, so
# near-misses have to be blocked or the contract is worthless. Note this
# includes the previous convention "不詳（未公開）" — profiles written under
# the old contract need migrating, see references/field-contract.md.
DISALLOWED_EMPTY_MARKERS = {
    "不詳（未公開）", "不詳(未公開)", "不詳", "未知", "無", "待確認", "查無",
    "N/A", "n/a", "NA", "TBD", "tbd", "－", "—", "–", "?", "？",
    "null", "None", "nil",
}
SANCTIONED = "-"

# Keys whose values are URLs/paths, where a bare "-" is not a placeholder.
_SKIP_KEYS = {"url", "path", "source_url"}


def _readable(err):
    """jsonschema's default message inlines the whole offending value, which
    for an over-long array dumps every entry into the terminal. Say what the
    limit was instead."""
    v, param = err.validator, err.validator_value
    if v == "maxItems":
        return f"最多 {param} 筆，目前 {len(err.instance)} 筆"
    if v == "minItems":
        return f"至少需要 {param} 筆，目前 {len(err.instance)} 筆"
    if v == "required":
        return err.message
    if v == "type":
        return f"型別錯誤：應為 {param}"
    if len(err.message) > 160:
        return err.message[:157] + "..."
    return err.message


def load_schema():
    with open(SCHEMA_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def _walk_strings(node, path="", skip_keys=_SKIP_KEYS):
    """Yield (json_path, string_value) for every string in the document."""
    if isinstance(node, dict):
        for k, v in node.items():
            if k in skip_keys or k == "$comment":
                continue
            yield from _walk_strings(v, f"{path}.{k}" if path else k, skip_keys)
    elif isinstance(node, list):
        for i, v in enumerate(node):
            yield from _walk_strings(v, f"{path}[{i}]", skip_keys)
    elif isinstance(node, str):
        yield path, node


def validate(data, target=None):
    """Return (errors, warnings) as lists of human-readable strings."""
    errors, warnings = [], []
    schema = load_schema()
    props = schema.get("properties", {})

    # 1. Structural checks straight out of the schema.
    try:
        import jsonschema
    except ImportError:
        warnings.append(
            "jsonschema 未安裝，已跳過 schema 結構驗證（僅執行內建規則）。"
            "安裝：pip install jsonschema"
        )
    else:
        validator = jsonschema.Draft202012Validator(schema)
        for e in sorted(validator.iter_errors(data), key=lambda e: list(e.path)):
            loc = ".".join(str(p) for p in e.path) or "(root)"
            errors.append(f"{loc}：{_readable(e)}")

    # 2. Rules JSON Schema can't express: exactly one spelling of "no data".
    for loc, value in _walk_strings(data):
        if value.strip() in DISALLOWED_EMPTY_MARKERS:
            errors.append(
                f'{loc}：不可用 "{value.strip()}" 表示查無資料，'
                f'請改用 "{SANCTIONED}"（這是可 grep 的欄位約定）。'
            )

    # 3. Editorial ceilings (x-soft-max) — warn, never block.
    for field, spec in props.items():
        soft_max = spec.get("x-soft-max")
        value = data.get(field)
        if soft_max and isinstance(value, list) and len(value) > soft_max:
            warnings.append(
                f"{field}：{len(value)} 筆，超過建議上限 {soft_max} 筆。"
                "版面會偏長，確認是否精簡。"
            )

    # 4. Fields the chosen output format will silently drop.
    if target:
        dropped = [
            f for f, spec in props.items()
            if data.get(f)
            and "x-target" in spec
            and target not in spec["x-target"]
            and "meta" not in spec["x-target"]
        ]
        if dropped:
            warnings.append(
                f"以下欄位有資料但不會出現在 {target}：{', '.join(dropped)}。"
                "這是版型設計如此，非錯誤（見 references/note-writing-guide.md）。"
            )

    return errors, warnings


def report(errors, warnings, stream=sys.stderr):
    for w in warnings:
        print(f"⚠️  {w}", file=stream)
    for e in errors:
        print(f"❌ {e}", file=stream)


def validate_or_exit(data, target=None):
    """Used by the generators: print findings, abort on any error."""
    errors, warnings = validate(data, target=target)
    report(errors, warnings)
    if errors:
        sys.exit(
            f"\nprofile.json 驗證失敗（{len(errors)} 項），未產生檔案。"
            "\n修正 JSON 後重跑；欄位規格見 assets/profile.schema.json。"
        )
    return data


def main():
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("profile_json")
    ap.add_argument("--target", choices=["html", "xlsx"],
                    help="一併檢查該格式會丟棄哪些欄位")
    ap.add_argument("--strict", action="store_true", help="警告也視為失敗")
    args = ap.parse_args()

    with open(args.profile_json, "r", encoding="utf-8") as f:
        data = json.load(f)

    errors, warnings = validate(data, target=args.target)
    report(errors, warnings)

    if errors or (args.strict and warnings):
        sys.exit(1)
    print(f"✅ {args.profile_json} 通過驗證"
          f"（{len(warnings)} 項警告）" if warnings else f"✅ {args.profile_json} 通過驗證")


if __name__ == "__main__":
    main()
