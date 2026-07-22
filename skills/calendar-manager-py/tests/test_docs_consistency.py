"""Docs must not drift from what's shipped.

The parent calendar-manager's SKILL.md described behaviors and files its code
never shipped (multi-location rendering, SPARE_LETTERS, three listed files
that didn't exist, a monkey-patch that wasn't there). This suite makes that
class of drift fail loudly here.
"""
import json
import re

import generate_calendar as G
import job as J
from validate_plan import SCHEMA_PATH

# Filenames that legitimately appear in docs without shipping in the repo:
# runtime outputs, user-created files, examples.
GENERATED = {
    "plan.json", "events.json", "manifest.json", "apply-report.json",
    "profile.json",  # mentioned only as the sibling skill's boundary file
    "Node.js",       # the runtime, not a file
}

# Longest extensions first + a guard, so "plan.json" can't half-match as
# "plan.js".
FILE_RE = re.compile(r"[\w.一-鿿-]+\.(?:json|yaml|html|py|js|md|txt)(?![A-Za-z0-9])")


def _mentioned_files(text):
    for name in set(FILE_RE.findall(text)):
        if name in GENERATED:
            continue
        if "年" in name:  # generated view filenames like 26年8月.html
            continue
        yield name


def _all_shipped_basenames(skill_root):
    names = set()
    for p in skill_root.rglob("*"):
        if p.is_file() and "node_modules" not in p.parts and "__pycache__" not in p.parts:
            names.add(p.name)
    return names


class TestMentionedFilesExist:
    def _assert_all_exist(self, skill_root, doc):
        shipped = _all_shipped_basenames(skill_root)
        text = (skill_root / doc).read_text(encoding="utf-8")
        missing = [n for n in _mentioned_files(text) if n not in shipped]
        assert not missing, f"{doc} 提到但不存在的檔案：{sorted(missing)}"

    def test_skill_md(self, skill_root):
        self._assert_all_exist(skill_root, "SKILL.md")

    def test_readme(self, skill_root):
        self._assert_all_exist(skill_root, "README.md")

    def test_orchestration(self, skill_root):
        self._assert_all_exist(skill_root, "references/orchestration.md")

    def test_event_input_formats(self, skill_root):
        self._assert_all_exist(skill_root, "references/event-input-formats.md")


class TestDocumentedBehaviorIsShipped:
    """The specific drifts found in the parent skill, pinned as assertions."""

    def test_templates_have_spare_colors(self, skill_root):
        for tpl in ("模板_月曆.html", "模板_週曆.html"):
            text = (skill_root / "assets" / tpl).read_text(encoding="utf-8")
            for letter in G.SPARE_LETTERS:
                assert f"--loc-{letter}:" in text, f"{tpl} 缺 --loc-{letter}"
                assert f".loc--{letter}{{" in text.replace(" ", ""), \
                    f"{tpl} 缺 .loc--{letter} 樣式"

    def test_templates_have_move_badge(self, skill_root):
        for tpl in ("模板_月曆.html", "模板_週曆.html"):
            text = (skill_root / "assets" / tpl).read_text(encoding="utf-8")
            assert ".loc--move" in text, f"{tpl} 缺 .loc--move"

    def test_renderer_really_collects_multiple_locations(self):
        # the parent's first-wins regression, pinned at the unit level
        by = G.parse_events([
            {"summary": "a", "location": "甲",
             "start": {"dateTime": "2026-08-03T09:00:00+08:00"},
             "end": {"dateTime": "2026-08-03T10:00:00+08:00"}},
            {"summary": "b", "location": "乙",
             "start": {"dateTime": "2026-08-03T11:00:00+08:00"},
             "end": {"dateTime": "2026-08-03T12:00:00+08:00"}},
        ])
        assert by[(2026, 8, 3)][0] == ["甲", "乙"]

    def test_schema_id_matches_skill(self):
        with open(SCHEMA_PATH, encoding="utf-8") as f:
            schema = json.load(f)
        assert schema["$id"] == "calendar-manager-py/plan@1"

    def test_manifest_schema_matches_skill(self):
        assert J.MANIFEST_SCHEMA.startswith("calendar-manager-py/")

    def test_skill_md_artifact_ids_match_build(self, skill_root):
        text = (skill_root / "SKILL.md").read_text(encoding="utf-8")
        for aid in ("events-json", "month-html", "week-1-html", "month-png"):
            assert aid in text
