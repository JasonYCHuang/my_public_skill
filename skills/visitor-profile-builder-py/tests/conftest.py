"""Shared fixtures.

The scripts/ dir is not a package (the generators import each other by bare
module name, e.g. `from validate_profile import ...`), so put it on sys.path
rather than trying to import through a package path.
"""
import copy
import json
import sys
from pathlib import Path

import pytest

SKILL_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SKILL_ROOT / "scripts"))


@pytest.fixture(scope="session")
def skill_root():
    return SKILL_ROOT


@pytest.fixture(scope="session")
def _example_raw():
    with open(SKILL_ROOT / "assets" / "profile.example.json", encoding="utf-8") as f:
        return json.load(f)


@pytest.fixture
def profile(_example_raw):
    """A valid profile dict. Deep-copied so a test can mutate it freely."""
    p = copy.deepcopy(_example_raw)
    p.pop("$comment", None)
    return p


@pytest.fixture
def photo_file(tmp_path):
    """A real 1x1 PNG on disk, for exercising the photo-embedding paths."""
    from PIL import Image

    p = tmp_path / "face.png"
    Image.new("RGB", (1, 1), (128, 128, 128)).save(p)
    return p
