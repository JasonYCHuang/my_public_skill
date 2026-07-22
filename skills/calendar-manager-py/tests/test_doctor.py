"""doctor.py — install prose as checks. Environment-dependent probes are
only shape-tested; the deterministic ones are asserted."""
import doctor as D


def test_python_check_passes_here():
    c = D._check_python()
    assert c["ok"] is True


def test_backend_none_skips_icloud_probes():
    names = [c["name"] for c in D.run_checks(backend="none", png=False)]
    assert not any(n.startswith("icloud:") or n in ("py:caldav", "py:icalendar")
                   for n in names)


def test_backend_icloud_includes_creds_probe():
    names = [c["name"] for c in D.run_checks(backend="icloud", png=False)]
    assert "icloud:credentials" in names
    assert "py:caldav" in names


def test_png_adds_toolchain_probes():
    names = [c["name"] for c in D.run_checks(backend="none", png=True)]
    for n in ("node", "puppeteer-core", "chrome", "cjk-font"):
        assert n in names


def test_every_failed_probe_carries_a_fix():
    for c in D.run_checks(backend="icloud", png=True):
        assert set(c) == {"name", "ok", "detail", "fix"}
        if not c["ok"]:
            assert c["fix"], f"{c['name']} 失敗但沒有修復指令"


def test_optional_module_missing_is_not_failure():
    c = D._check_module("definitely_not_installed_xyz", "why", required=False)
    assert c["ok"] is True
    assert "pip install" in c["fix"]


def test_required_module_missing_is_failure():
    c = D._check_module("definitely_not_installed_xyz", "why", required=True)
    assert c["ok"] is False
