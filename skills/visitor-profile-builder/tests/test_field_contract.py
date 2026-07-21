"""The 10-field contract, as enforced by validate_profile.py.

These encode references/field-contract.md. If a test here fails after an
intentional spec change, update the schema and the doc together — the schema
is the source of truth, this file only checks it is actually enforced.
"""
import json

import pytest

from validate_profile import (
    DISALLOWED_EMPTY_MARKERS,
    SANCTIONED,
    load_schema,
    validate,
    validate_or_exit,
)

TEN_FIELDS = [
    "name", "gender", "birth", "zodiac", "hometown", "contact",
    "education", "positions", "career", "photos",
]


def errors_for(profile):
    return validate(profile)[0]


def test_example_profile_is_valid(profile):
    assert errors_for(profile) == []


def test_schema_declares_exactly_the_ten_fields():
    schema = load_schema()
    assert sorted(schema["required"]) == sorted(TEN_FIELDS)


def test_field_numbers_are_one_through_ten_without_gaps():
    props = load_schema()["properties"]
    numbers = sorted(
        spec["x-field-no"] for spec in props.values() if "x-field-no" in spec
    )
    assert numbers == list(range(1, 11))


@pytest.mark.parametrize("field", TEN_FIELDS)
def test_every_field_is_required(profile, field):
    del profile[field]
    assert errors_for(profile), f"刪除 {field} 後應該報錯"


def test_unknown_top_level_key_is_rejected(profile):
    profile["nickname"] = "小明"
    assert errors_for(profile)


def test_sources_entry_rejects_unknown_key(profile):
    """Regression: sources.items was the one object left open."""
    profile["sources"][0]["note"] = "typo"
    assert errors_for(profile)


# --- 硬限制 -----------------------------------------------------------------

@pytest.mark.parametrize(
    "field,limit,make",
    [
        ("education", 5, lambda i: {"school": f"校{i}", "major": "科",
                                    "degree_level": "學士", "degree": "學位"}),
        ("positions", 3, lambda i: f"職位{i}"),
        ("career", 10, lambda i: {"date": f"20{i:02d}", "org": f"單位{i}",
                                  "role": "職"}),
    ],
)
def test_count_ceilings(profile, field, limit, make):
    profile[field] = [make(i) for i in range(limit)]
    assert errors_for(profile) == [], f"{field} 剛好 {limit} 筆應該通過"

    profile[field] = [make(i) for i in range(limit + 1)]
    assert errors_for(profile), f"{field} 超過 {limit} 筆應該報錯"


def test_photos_ceiling_is_two(profile, photo_file):
    entry = {"path": str(photo_file), "caption": "說明"}
    profile["photos"] = [entry, entry]
    assert errors_for(profile) == []
    profile["photos"] = [entry, entry, entry]
    assert errors_for(profile)


def test_sources_needs_at_least_one(profile):
    profile["sources"] = []
    assert errors_for(profile)


# --- 空值寫法 ---------------------------------------------------------------

def test_sanctioned_placeholder_is_accepted(profile):
    profile["hometown"] = SANCTIONED
    assert errors_for(profile) == []


@pytest.mark.parametrize("marker", sorted(DISALLOWED_EMPTY_MARKERS))
def test_every_disallowed_marker_is_rejected(profile, marker):
    profile["hometown"] = marker
    errs = errors_for(profile)
    assert errs, f'"{marker}" 應該被拒絕'
    assert any("可 grep" in e or marker in e for e in errs)


def test_placeholder_check_skips_urls(profile):
    """A URL or path may legitimately contain a bare '-'."""
    profile["sources"] = [{"title": "來源", "url": "https://example.com/a-b-c"}]
    assert errors_for(profile) == []


# --- 呼叫端行為 -------------------------------------------------------------

def test_validate_or_exit_aborts_on_error(profile):
    profile["positions"] = ["a", "b", "c", "d"]
    with pytest.raises(SystemExit):
        validate_or_exit(profile)


def test_validate_or_exit_returns_data_when_clean(profile):
    assert validate_or_exit(profile) is profile


# --- 盡職查證（原本只寫在 SKILL.md 裡的規則）---------------------------------
#
# 全部是 warning：這些規則講的是「查得夠不夠仔細」，不是「能不能渲染」。
# 做成 error 會擋掉入口 A 那條文件明載的兩行流程。

def warnings_for(profile):
    return validate(profile)[1]


def test_valid_example_raises_no_diligence_warning(profile):
    """新規則不得誤傷正確的用法。"""
    assert warnings_for(profile) == []


def test_missing_note_warns(profile):
    profile["note"] = None
    assert any("note 未填" in w for w in warnings_for(profile))


def test_photos_without_note_mention_warns(profile, photo_file):
    profile["photos"] = [{"path": str(photo_file), "caption": "系所網頁"}]
    profile["note"] = "資料彙整自公開網路資訊。"
    assert any("未提及照片" in w for w in warnings_for(profile))


def test_photos_mentioned_in_note_is_clean(profile, photo_file):
    profile["photos"] = [{"path": str(photo_file), "caption": "系所網頁"}]
    profile["note"] = "照片取自系所網頁，非官方授權提供，解析度較低。"
    assert not any("未提及照片" in w for w in warnings_for(profile))


def test_photo_source_url_not_in_sources_warns(profile, photo_file):
    profile["photos"] = [{
        "path": str(photo_file),
        "caption": "系所網頁",
        "source_url": "https://example.edu/photo.jpg",
    }]
    profile["note"] = "照片取自系所網頁，非官方。"
    assert any("source_url 未列入 sources" in w for w in warnings_for(profile))


def test_photo_source_url_listed_in_sources_is_clean(profile, photo_file):
    url = "https://example.edu/photo.jpg"
    profile["photos"] = [{"path": str(photo_file), "caption": "系所網頁",
                          "source_url": url}]
    profile["note"] = "照片取自系所網頁，非官方。"
    profile["sources"].append({"title": "照片來源", "url": url})
    assert not any("source_url" in w for w in warnings_for(profile))


def test_sources_without_any_url_warns(profile):
    """入口 A 的預設產物：滿足 minItems 1，但沒有任何可回溯的網址，
    而 HTML 會因此整個不顯示頁尾。"""
    profile["sources"] = [{"title": "原始來源檔案", "url": ""}]
    assert any("沒有任何可用網址" in w for w in warnings_for(profile))


def test_diligence_warnings_never_block_generation(profile):
    """全部是 warning —— validate_or_exit 不得因此中止。"""
    profile["note"] = None
    profile["sources"] = [{"title": "原始來源檔案", "url": ""}]
    assert validate_or_exit(profile) is profile


def test_photo_caption_must_not_be_empty(profile, photo_file):
    """caption 原本是 schema 裡唯一沒有 minLength 的必填字串；空字串會在
    縮圖下方留下一塊沒有說明的照片。"""
    profile["photos"] = [{"path": str(photo_file), "caption": ""}]
    assert errors_for(profile)


def test_missing_jsonschema_only_warns(profile, monkeypatch):
    """Without jsonschema the validator degrades to built-in rules and says so
    — it must not start failing valid files."""
    import builtins

    real_import = builtins.__import__

    def fake_import(name, *a, **kw):
        if name == "jsonschema":
            raise ImportError("simulated")
        return real_import(name, *a, **kw)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    errors, warnings = validate(profile)
    assert errors == []
    assert any("jsonschema" in w for w in warnings)
