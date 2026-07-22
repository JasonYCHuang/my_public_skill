"""Do the docs still describe what the code actually does?

This is the class of bug plain review keeps missing: a function gets deleted,
a limit changes, a warning stops firing — and the prose that described it
stays behind, confidently wrong. These checks are mechanical so they survive
the next refactor.
"""
import json
import re

import pytest

from validate_profile import load_schema

TEXT_GLOBS = ("*.md", "scripts/*.py", "scripts/*.js")


def text_files(root):
    files = []
    for pattern in TEXT_GLOBS:
        files.extend(sorted(root.glob(pattern)))
    files.extend(sorted((root / "references").glob("*.md")))
    return files


def read_all(root):
    return {f: f.read_text(encoding="utf-8") for f in text_files(root)}


# --- 交叉引用 ---------------------------------------------------------------

# json before js, html before h*: a regex alternation matches left-to-right, so
# listing "js" first would clip "profile.schema.json" down to a nonexistent
# "profile.schema.js". \b stops the match short of a longer real extension.
# The lookbehind keeps this anchored to paths relative to the skill root: without
# it, a sibling-skill path like `calendar-manager/scripts/screenshot.js` would
# match from "scripts/" onward and be reported as missing from this package.
PATH_RE = re.compile(
    r"(?<![\w/-])(?:references|scripts|assets|tests)/[A-Za-z0-9_.-]+"
    r"\.(?:json|js|md|py|html|sh)\b"
)

# Placeholders that appear in prose/usage examples, not real paths.
IGNORED_PATHS = {"scripts/....py"}


def test_no_dangling_file_references(skill_root):
    missing = []
    for path, body in read_all(skill_root).items():
        for ref in set(PATH_RE.findall(body)):
            if ref in IGNORED_PATHS:
                continue
            if not (skill_root / ref).exists():
                missing.append(f"{path.name} → {ref}")
    assert not missing, "文件指向不存在的檔案：" + ", ".join(missing)


def test_referenced_functions_exist(skill_root):
    """Docs name specific helpers; deleting one must not leave the prose."""
    named = {"is_placeholder", "cell_value", "val", "validate_or_exit",
             "validate", "find_section_rows", "split_name", "esc"}
    sources = "\n".join(
        (skill_root / "scripts" / f).read_text(encoding="utf-8")
        for f in ("validate_profile.py", "xlsx_to_profile_json.py",
                  "profile_json_to_xlsx.py", "profile_json_to_html.py")
    )
    docs = "\n".join(
        body for path, body in read_all(skill_root).items() if path.suffix == ".md"
    )
    for fn in named:
        if f"{fn}()" in docs:
            assert f"def {fn}(" in sources, f"文件提到 {fn}() 但程式裡沒有"


# --- schema 與文件的數字 -----------------------------------------------------

def test_schema_requires_exactly_ten_fields():
    assert len(load_schema()["required"]) == 10


@pytest.mark.parametrize("field", ["education", "positions", "career", "photos"])
def test_hard_limits_in_docs_match_the_schema(skill_root, field):
    limit = load_schema()["properties"][field]["maxItems"]
    doc = (skill_root / "references" / "field-contract.md").read_text(encoding="utf-8")
    assert re.search(rf"{field}.*?{limit}|最多 {limit}|{limit} 張", doc), (
        f"field-contract.md 沒有反映 {field} 的上限 {limit}"
    )


def test_sanctioned_placeholder_is_documented(skill_root):
    doc = (skill_root / "references" / "field-contract.md").read_text(encoding="utf-8")
    assert "半形 `-`" in doc


# --- 產生的檔案是否過期 ------------------------------------------------------

def test_example_html_is_up_to_date(skill_root):
    """maintaining.md requires regenerating assets/profile.example.html in the
    same commit as any template or example-JSON change. A stale sample teaches
    the wrong layout, so enforce it rather than trusting the habit."""
    from profile_json_to_html import render

    with open(skill_root / "assets" / "profile.example.json", encoding="utf-8") as f:
        data = json.load(f)
    on_disk = (skill_root / "assets" / "profile.example.html").read_text(encoding="utf-8")
    assert render(data) == on_disk, (
        "assets/profile.example.html 已過期，重新產生：\n"
        "  python3 scripts/profile_json_to_html.py "
        "assets/profile.example.json -o assets/profile.example.html"
    )


def test_example_profile_stays_fictional(skill_root):
    """This package gets copied and redistributed as a unit."""
    with open(skill_root / "assets" / "profile.example.json", encoding="utf-8") as f:
        raw = f.read()
    assert "範例" in raw or "示範" in raw
    assert "$comment" in raw, "範例檔應保留說明其為虛構資料的 $comment"


# --- 用語一致 ---------------------------------------------------------------

@pytest.mark.parametrize("stale,current", [("主要經歷", "主要履歷")])
def test_no_stale_terminology(skill_root, stale, current):
    hits = [p.name for p, body in read_all(skill_root).items() if stale in body]
    assert not hits, f"仍有檔案使用舊用語「{stale}」（應為「{current}」）：{hits}"


def test_venv_path_is_consistent(skill_root):
    """README and SKILL.md both tell the reader to build the same venv; if they
    drift, an agent following one and a human following the other end up with
    two different interpreters."""
    paths = set()
    for name in ("README.md", "SKILL.md"):
        body = (skill_root / name).read_text(encoding="utf-8")
        paths.update(re.findall(r"python3 -m venv (\S+)", body))
    assert len(paths) == 1, f"venv 路徑不一致：{paths}"


# --- SKILL.md frontmatter ---------------------------------------------------

def test_skill_frontmatter_has_required_keys(skill_root):
    body = (skill_root / "SKILL.md").read_text(encoding="utf-8")
    assert body.startswith("---\n")
    front = body.split("---", 2)[1]
    for key in ("name:", "description:"):
        assert key in front, f"SKILL.md frontmatter 缺少 {key}"


def test_skill_name_matches_directory(skill_root):
    body = (skill_root / "SKILL.md").read_text(encoding="utf-8")
    declared = re.search(r"^name:\s*(\S+)", body, re.M).group(1)
    assert declared == skill_root.name


# --- 隱私規範 ---------------------------------------------------------------

def test_no_generated_profiles_committed(skill_root):
    """SKILL.md: never save a real profile.json/html/xlsx/png inside this
    folder. Only the fictional example is allowed."""
    allowed = {"profile.example.json", "profile.example.html", "profile.schema.json"}
    strays = [
        p.name
        for p in (skill_root / "assets").iterdir()
        if p.is_file() and p.name not in allowed
    ]
    assert not strays, f"assets/ 有非預期的檔案：{strays}"
