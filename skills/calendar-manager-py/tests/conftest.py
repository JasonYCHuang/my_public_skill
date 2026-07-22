"""Shared fixtures.

The scripts/ dir is not a package (the scripts import each other by bare
module name, e.g. `import job`), so put it on sys.path rather than importing
through a package path. The sibling visitor-profile-builder-py suite uses
the same bare names (job, build, verify_output) — purge any cached copies so
this suite always gets *this* skill's modules, whichever suite ran first.
"""
import copy
import sys
from pathlib import Path

import pytest

SKILL_ROOT = Path(__file__).resolve().parent.parent
_SHARED_BARE_NAMES = ("job", "build", "verify_output")
for _name in _SHARED_BARE_NAMES:
    mod = sys.modules.get(_name)
    if mod is not None and str(SKILL_ROOT) not in str(getattr(mod, "__file__", "")):
        del sys.modules[_name]
sys.path.insert(0, str(SKILL_ROOT / "scripts"))


@pytest.fixture(scope="session")
def skill_root():
    return SKILL_ROOT


_SAMPLE_EVENTS = [
    {"summary": "部門月會", "location": "地點A",
     "start": {"dateTime": "2026-08-03T09:00:00+08:00"},
     "end": {"dateTime": "2026-08-03T10:00:00+08:00"}},
    {"summary": "供應商拜訪", "location": "地點B",
     "start": {"dateTime": "2026-08-03T14:00:00+08:00"},
     "end": {"dateTime": "2026-08-03T15:30:00+08:00"}},
    {"summary": "教育訓練", "location": "北京",
     "start": {"date": "2026-08-12"}, "end": {"date": "2026-08-13"}},
    {"summary": "晚間讀書會 chap 04", "location": "在家",
     "start": {"dateTime": "2026-08-17T19:30:00+08:00"},
     "end": {"dateTime": "2026-08-17T20:30:00+08:00"}},
    {"summary": "月底檢討", "location": "地點C",
     "start": {"dateTime": "2026-08-31T16:00:00+08:00"},
     "end": {"dateTime": "2026-08-31T17:00:00+08:00"}},
    {"summary": "跨月專案會議", "location": "地點D",
     "start": {"dateTime": "2026-09-01T10:00:00+08:00"},
     "end": {"dateTime": "2026-09-01T11:00:00+08:00"}},
]


@pytest.fixture
def events():
    """A small but structurally rich events array for 2026-08: a two-location
    day, an all-day event, two unmapped locations, and a spill into 09."""
    return copy.deepcopy(_SAMPLE_EVENTS)


@pytest.fixture
def plan():
    """A valid write plan. Deep-copied so a test can mutate it freely."""
    return copy.deepcopy({
        "calendar": "測試行事曆",
        "backend": "icloud",
        "default_duration_minutes": 60,
        "operations": [
            {"op": "create", "summary": "部門月會", "location": "地點A",
             "start": "2026-08-02 09:00", "end": "2026-08-02 10:00"},
            {"op": "create", "summary": "全天工作坊", "location": "地點B",
             "start": "2026-08-05", "all_day": True},
            {"op": "update", "uid": "abc-123", "start": "2026-08-03 09:30",
             "end": "2026-08-03 10:30"},
            {"op": "delete", "uid": "def-456"},
        ],
    })
