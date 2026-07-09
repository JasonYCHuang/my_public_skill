#!/usr/bin/env python3
"""
Extract structured profile data out of a "個人信息登記表" style xlsx
(the format used in reference/*.xlsx) into a profile.json matching
assets/profile.schema.json.

Usage:
    python3 xlsx_to_profile_json.py <input.xlsx> [-o <output.json>]

If -o is omitted, writes <input-basename>.json next to the input file.

Expected xlsx layout (see references/xlsx-source-format.md for the full
reverse-engineered spec):
    A1        timestamp
    A2:F2     title ("個人信息登記表")
    A3/C3     姓名 / 性別 labels, B3/D3:E3 values
    A4/C4     出生年月 / 生肖
    A5/C5     聯繫方式 / 籍貫
    A6:A8+    教育經歷 (merged label) -> header row + N data rows
              (畢業院校 / 專業 / 學歷 / 學位)
    A9:A11+   現任職位 (merged label) -> N rows, each B:F merged
    A12:..+   主要履歷 (merged label) -> header row + N data rows
              (起止年月 / 工作單位(C:E merged) / 職位)
    any cell in column A starting with "注：" -> note
"""
import argparse
import json
import sys

try:
    import openpyxl
except ImportError:
    sys.exit("需要 openpyxl：pip install openpyxl")

PLACEHOLDER_VALUES = {None, "", "-", "－", "—"}


def is_placeholder(v):
    return v is None or str(v).strip() in PLACEHOLDER_VALUES


def find_section_rows(ws, label):
    for mr in ws.merged_cells.ranges:
        if mr.min_col == 1 and ws.cell(row=mr.min_row, column=1).value == label:
            return mr.min_row, mr.max_row
    return None


def extract(path):
    wb = openpyxl.load_workbook(path, data_only=True)
    ws = wb.active

    data = {
        "timestamp": ws["A1"].value or "",
        "name": ws["B3"].value or "",
        "gender": None if is_placeholder(ws["D3"].value) else ws["D3"].value,
        "birth": None if is_placeholder(ws["B4"].value) else ws["B4"].value,
        "zodiac": None if is_placeholder(ws["D4"].value) else ws["D4"].value,
        "contact": None if is_placeholder(ws["B5"].value) else ws["B5"].value,
        "hometown": None if is_placeholder(ws["D5"].value) else ws["D5"].value,
        "education": [],
        "positions": [],
        "career": [],
        "note": None,
    }

    edu_range = find_section_rows(ws, "教育經歷")
    if edu_range:
        header_row, last_row = edu_range
        for r in range(header_row + 1, last_row + 1):
            school, major, degree_level, degree = (
                ws.cell(row=r, column=c).value for c in (2, 3, 4, 5)
            )
            if not all(is_placeholder(v) for v in (school, major, degree_level, degree)):
                data["education"].append(
                    {"school": school, "major": major, "degree_level": degree_level, "degree": degree}
                )

    pos_range = find_section_rows(ws, "現任職位")
    if pos_range:
        first_row, last_row = pos_range
        for r in range(first_row, last_row + 1):
            v = ws.cell(row=r, column=2).value
            if not is_placeholder(v):
                data["positions"].append(v)

    career_range = find_section_rows(ws, "主要履歷")
    if career_range:
        header_row, last_row = career_range
        for r in range(header_row + 1, last_row + 1):
            date, org, role = (
                ws.cell(row=r, column=2).value,
                ws.cell(row=r, column=3).value,
                ws.cell(row=r, column=6).value,
            )
            if not all(is_placeholder(v) for v in (date, org, role)):
                data["career"].append({"date": date, "org": org, "role": role})

    for row in ws.iter_rows():
        for cell in row:
            if cell.column == 1 and isinstance(cell.value, str) and cell.value.startswith("注："):
                data["note"] = cell.value[2:].strip()

    data["photos"] = []
    data["sources"] = [{"title": "原始來源檔案", "url": ""}]
    return data


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("input", help="來源 xlsx 檔路徑")
    ap.add_argument("-o", "--output", help="輸出 json 路徑（預設：同檔名 .json）")
    args = ap.parse_args()

    data = extract(args.input)

    out_path = args.output
    if not out_path:
        import os

        out_path = os.path.splitext(args.input)[0] + ".json"

    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"wrote {out_path}")


if __name__ == "__main__":
    main()
