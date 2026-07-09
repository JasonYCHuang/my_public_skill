# Source xlsx layout spec ("個人信息登記表")

Reverse-engineered from two seed files in the format `{單位}-{姓名} 個人信息表.xlsx`
(names/units are placeholders here — the real seed files this was derived
from are internal working documents and are deliberately **not** included
in or referenced by name from this shareable skill package; only the
structural shape below is reusable).
`scripts/xlsx_to_profile_json.py` and `scripts/profile_json_to_xlsx.py` both
depend on this exact merged-cell shape. If you're pointed at a differently-shaped
source file, read this doc first, then adjust the two scripts' cell
coordinates rather than guessing.

## Cell map

| Cell(s) | Merge | Content |
|---|---|---|
| `A1:F1` | yes | Timestamp, right-aligned (e.g. `2026/04/23 PM15:00`) |
| `A2:F2` | yes | Title, always literal string `個人信息登記表` |
| `G2:M3` | yes | Photo placeholder (top) — empty in both seed files |
| `A3` | no | Label `姓　　名` | `B3` value = name |
| `C3` | no | Label `性　　別` | `D3:E3` merged, value = gender |
| `F3:F{N}` | yes | Vertical note/photo-caption column, spans rows 3 through the last row of the 教育經歷 section. Empty in one seed file, holds a short bracketed note (e.g. `（照片無官方披露）`) in the other. |
| `A4` / `C4` | no | Labels `出生年月` / `生　　肖`; `B4` / `D4:E4` values |
| `A5` / `C5` | no | Labels `聯繫方式` / `籍　　貫`; `B5` / `D5:E5` values |
| `A6:A{N}` | yes | Section label `教育經歷`, rowspan = 1 header row + however many education rows exist (seed files use 2; not fixed) |
| `B6..E6` | no | Column headers `畢業院校` / `專業` / `學歷` / `學位` |
| `B{r}..E{r}` | no | One row per degree; unused rows filled with `-` placeholders in the seed files |
| `A{N}:A{M}` | yes | Section label `現任職位`, rowspan = however many current positions exist (seed files use 3) |
| `B{r}:F{r}` | yes, per row | One merged row per position |
| `A{M}:A{P}` | yes | Section label `主要履歷`, rowspan = 1 header row + however many career rows exist (seed files use 2 and 7 — this section's length varies the most) |
| `B{M}` / `C{M}:E{M}` / `F{M}` | no / yes / no | Column headers `起止年月` / `工作單位` / `職位` |
| `B{r}` / `C{r}:E{r}` / `F{r}` | no / yes / no | One row per career entry |
| `G5:M{P}` | yes | Large photo/notes placeholder (bottom), spans rows 5 through the last row of 主要履歷. Separate merge from `G2:M3` — there's a visible gap at row 4 between the two blocks (row 4's G–M cells are individual, unmerged, empty cells). |
| `A{P+1}:F{P+1}` | yes | Optional trailing note row, only present in one of the two seed files — a short `注：...` sentence explaining data gaps (see `note-writing-guide.md` for how to phrase this). |

`N`, `M`, `P` are computed dynamically in both directions — `xlsx_to_profile_json.py`
finds each section's row range by scanning `ws.merged_cells.ranges` for a
column-A merge whose top-left cell value matches the section label
(`教育經歷` / `現任職位` / `主要履歷`), rather than hardcoding row numbers.
`profile_json_to_xlsx.py` does the inverse: it computes row numbers from
`len(education)`, `len(positions)`, `len(career)` in the JSON.

## Styling notes (approximate, not pixel-exact)

- Font: Arial throughout. Title 20pt bold. Section labels / row-1 field
  labels 14pt bold. Data cells 12–14pt regular.
- Label cells (column A section labels, and the 6 field labels in rows 3–5)
  use a light blue fill (Excel theme color 3, tint ~0.9 — approximated in
  the scripts as solid `#DCE6F1`).
- Subheader cells (教育經歷/主要履歷 column headers) use a light gray fill
  (Excel theme 0, tint ~-0.05 — approximated as solid `#F2F2F2`).
- Column widths: A=12.5, B=23.0, C=18.625, D=13.5, E=15.125, F=27.625,
  G onward ≈10.0. Row heights: header row2 ≈38.25, most data rows ≈35.1.

## Placeholder convention

Both seed files use literal `-` for "no data" in per-row cells (education,
current positions, career). `is_placeholder()` in both scripts treats
`None`, `""`, `-`, `－`, `—` as equivalent — treat any of these as "empty",
not as a real value, when reading or writing.
