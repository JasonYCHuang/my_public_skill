"""Tests for doctor.py log classification — sample lines are verbatim from the
real 2026-07-22 incident journal."""

import argparse
import pathlib
import subprocess
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "scripts"))

import doctor  # noqa: E402
from doctor import classify, positive_int, unit_name  # noqa: E402

NOISE = [
    "ERROR gateway.platforms.weixin: [Weixin] poll error (1/3): iLink POST ilink/bot/getupdates HTTP 524:",
    "ERROR gateway.platforms.weixin: [Weixin] poll error (2/3): iLink POST ilink/bot/getupdates HTTP 524:",
    "ERROR gateway.platforms.weixin: [Weixin] poll error (3/3): iLink POST ilink/bot/getupdates HTTP 554:",
]

FAILURES = [
    "ERROR gateway.platforms.weixin: [Weixin] send_document failed to=o9cq805x: CDN upload HTTP 500:",
    "ERROR gateway.platforms.base: [Weixin] Failed to send image: CDN upload HTTP 500:",
]

SESSION = [
    "WARNING gateway.platforms.weixin: Session expired; pausing for 10 minutes",
    "ERROR gateway.platforms.weixin: sendmessage failed: errcode=-14 errmsg=session timeout",
]

HEALTHY = [
    "INFO gateway.run: message delivered",
    "WARNING tools.registry: check_fn check_browser_requirements returned False; dependent tools will be unavailable this turn",
]


def test_noise_is_counted_not_flagged():
    failures, session, noise = classify(NOISE)
    assert failures == []
    assert session == []
    assert noise == 3


def test_send_failures_detected():
    failures, session, noise = classify(NOISE + FAILURES + HEALTHY)
    assert len(failures) == 2
    assert session == []
    assert noise == 3
    assert all("CDN upload HTTP 500" in ln for ln in failures)


def test_session_expiry_detected():
    failures, session, noise = classify(SESSION)
    assert failures == []
    assert len(session) == 2


def test_healthy_log_is_clean():
    failures, session, noise = classify(HEALTHY)
    assert (failures, session, noise) == ([], [], 0)


def test_poll_noise_never_masks_a_real_failure():
    # A line matching both patterns must never be swallowed as noise —
    # POLL_NOISE requires the getupdates signature, send failures don't have it.
    mixed = NOISE * 10 + FAILURES
    failures, _, noise = classify(mixed)
    assert len(failures) == 2
    assert noise == 30


# --- boundary validation: caller input is LLM-generated — validate, don't trust ---


def test_broken_journal_read_is_not_healthy(monkeypatch):
    # A bad --since (or missing journalctl) must yield exit 4 "cannot read",
    # never exit 0 "healthy" derived from an empty measurement.
    monkeypatch.setattr(doctor, "journal_lines", lambda unit, since: None)
    monkeypatch.setattr(doctor, "unit_active", lambda unit: "active")
    assert doctor.main(["diagnose", "--since", "30 minutes go"]) == 4
    assert doctor.main(["verify"]) == 4


def test_journal_lines_returns_none_not_empty_on_journalctl_failure(monkeypatch):
    # Producer side of the same property (mutation testing caught this gap):
    # a failing journalctl must surface as None — an empty [] would read as
    # "no log lines" and flow into a false "healthy" verdict downstream.
    monkeypatch.setattr(doctor, "run",
                        lambda cmd, **kw: subprocess.CompletedProcess(cmd, 1, "", "bad --since"))
    assert doctor.journal_lines("hermes-gateway", "30 minutes go") is None
    monkeypatch.setattr(doctor, "run",
                        lambda cmd, **kw: subprocess.CompletedProcess(cmd, 0, "line1\nline2\n", ""))
    assert doctor.journal_lines("hermes-gateway", "5 min ago") == ["line1", "line2"]


def test_unit_name_rejects_flag_lookalikes_and_garbage():
    assert unit_name("hermes-gateway") == "hermes-gateway"
    assert unit_name("foo@bar.service") == "foo@bar.service"
    for bad in ["-n", "--user", "a b", "a;b", ""]:
        with pytest.raises(argparse.ArgumentTypeError):
            unit_name(bad)


def test_delay_must_be_at_least_one_second():
    assert positive_int("5") == 5
    for bad in ["0", "-3"]:
        with pytest.raises(argparse.ArgumentTypeError):
            positive_int(bad)


# --- output contract: the playbook guidance lives in doctor.py's verdicts,
#     not in prose docs — these tests pin that the guidance is actually printed ---


def test_restart_verdict_carries_the_full_playbook(monkeypatch, capsys):
    monkeypatch.setattr(doctor, "unit_active", lambda unit: "active")
    monkeypatch.setattr(doctor, "journal_lines", lambda unit, since: NOISE + FAILURES)
    assert doctor.main(["diagnose"]) == 1
    out = capsys.readouterr().out
    assert "ruled-out causes" in out                    # don't re-investigate false causes
    assert doctor.SUGGESTED_REPLY in out                # reply-in-text-first, message included
    assert "IGNORE" in out                              # poll noise called out as non-signal


def test_session_expired_verdict_hands_qr_rescan_to_the_user(monkeypatch, capsys):
    monkeypatch.setattr(doctor, "unit_active", lambda unit: "active")
    monkeypatch.setattr(doctor, "journal_lines", lambda unit, since: FAILURES + SESSION)
    assert doctor.main(["diagnose"]) == 3
    out = capsys.readouterr().out
    assert "hermes gateway setup" in out
    assert "never run it via scripts" in out


def test_verify_failure_escalates_and_success_demands_end_to_end_proof(monkeypatch, capsys):
    monkeypatch.setattr(doctor, "unit_active", lambda unit: "active")
    monkeypatch.setattr(doctor, "journal_lines", lambda unit, since: FAILURES)
    assert doctor.main(["verify"]) == 1
    assert "hermes gateway setup" in capsys.readouterr().out

    monkeypatch.setattr(doctor, "journal_lines", lambda unit, since: HEALTHY)
    assert doctor.main(["verify"]) == 0
    assert "re-send an image" in capsys.readouterr().out


def test_diagnose_healthy_and_not_running(monkeypatch, capsys):
    monkeypatch.setattr(doctor, "journal_lines", lambda unit, since: NOISE + HEALTHY)
    monkeypatch.setattr(doctor, "unit_active", lambda unit: "active")
    assert doctor.main(["diagnose"]) == 0
    assert "healthy" in capsys.readouterr().out

    monkeypatch.setattr(doctor, "unit_active", lambda unit: "inactive")
    assert doctor.main(["diagnose"]) == 2
    assert "systemctl --user start" in capsys.readouterr().out
    assert doctor.main(["verify"]) == 2


# --- cmd_restart: the safety-critical paths ---


class FakeRun:
    """Records argvs passed to doctor.run; returns scripted (rc, stdout) results."""

    def __init__(self, results):
        self.results = [(r, "") if isinstance(r, int) else r for r in results]
        self.calls = []

    def __call__(self, cmd, **kw):
        self.calls.append(cmd)
        rc, out = self.results.pop(0)
        return subprocess.CompletedProcess(cmd, rc, out, "boom")


def restart_argv(tmp_path, *extra):
    # every test gets an isolated state dir so the frequency guard sees no history
    return ["restart", "--state-dir", str(tmp_path / "state"), *extra]


def test_restart_schedules_detached_delayed_transient_unit(monkeypatch, capsys, tmp_path):
    fake = FakeRun([0, 0])  # list-timers, systemd-run
    monkeypatch.setattr(doctor, "run", fake)
    monkeypatch.setattr(doctor, "inside_unit", lambda unit: True)
    assert doctor.main(restart_argv(tmp_path)) == 0
    cmd = fake.calls[1]
    assert cmd[0] == "systemd-run" and "--collect" in cmd and "--on-active=5s" in cmd
    assert cmd[-4:] == ["systemctl", "--user", "restart", "hermes-gateway"]
    assert doctor.SUGGESTED_REPLY in capsys.readouterr().out  # reply-before-fire warning
    assert doctor.recent_restarts(tmp_path / "state") == 1    # survives agent death


def test_restart_never_direct_restarts_from_inside_the_unit(monkeypatch, tmp_path):
    # Regression guard for the self-kill trap: if systemd-run fails while we run
    # inside the unit, the ONLY acceptable outcome is exit 1 — a direct
    # `systemctl restart` fallback would kill the agent mid-task.
    fake = FakeRun([0, 1])
    monkeypatch.setattr(doctor, "run", fake)
    monkeypatch.setattr(doctor, "inside_unit", lambda unit: True)
    assert doctor.main(restart_argv(tmp_path)) == 1
    assert len(fake.calls) == 2  # list-timers + systemd-run, no direct restart

    # Outside the unit the fallback IS safe and must engage:
    fake = FakeRun([0, 1, 0])
    monkeypatch.setattr(doctor, "run", fake)
    monkeypatch.setattr(doctor, "inside_unit", lambda unit: False)
    assert doctor.main(restart_argv(tmp_path)) == 0
    assert fake.calls[2] == ["systemctl", "--user", "restart", "hermes-gateway"]


def test_restart_does_not_stack_on_a_pending_timer(monkeypatch, tmp_path):
    # An impatient user pinging repeatedly must not queue multiple restarts.
    fake = FakeRun([(0, "Mon 2026-07-22 12:00:05 CST  5s left  -  -  "
                       "gateway-doctor-restart-123.timer  gateway-doctor-restart-123.service")])
    monkeypatch.setattr(doctor, "run", fake)
    assert doctor.main(restart_argv(tmp_path)) == 0
    assert len(fake.calls) == 1  # only the list-timers probe; nothing scheduled


def test_restart_frequency_guard_escalates_instead_of_looping(monkeypatch, capsys, tmp_path):
    # The agent dies (and forgets) with every restart — this state file is the
    # cross-death memory that stops an endless restart loop.
    state = tmp_path / "state"
    doctor.note_restart(state)
    doctor.note_restart(state)
    fake = FakeRun([])
    monkeypatch.setattr(doctor, "run", fake)
    assert doctor.main(restart_argv(tmp_path)) == 3
    assert "hermes gateway setup" in capsys.readouterr().out  # points at escalation
    assert fake.calls == []                                   # no restart attempted

    monkeypatch.setattr(doctor, "run", FakeRun([0, 0]))
    monkeypatch.setattr(doctor, "inside_unit", lambda unit: False)
    assert doctor.main(restart_argv(tmp_path, "--force")) == 0  # explicit override works


def test_verify_window_starts_at_last_unit_activation(monkeypatch):
    # Pre-restart failures must not leak into the verify window (they would
    # trigger a false "still failing" -> needless QR escalation).
    seen = {}

    def fake_journal(unit, since):
        seen["since"] = since
        return HEALTHY

    monkeypatch.setattr(doctor, "unit_active", lambda unit: "active")
    monkeypatch.setattr(doctor, "journal_lines", fake_journal)
    monkeypatch.setattr(doctor, "since_last_start", lambda unit: "2026-07-22 12:00:05")
    assert doctor.main(["verify"]) == 0
    assert seen["since"] == "2026-07-22 12:00:05"

    monkeypatch.setattr(doctor, "since_last_start", lambda unit: None)
    assert doctor.main(["verify"]) == 0
    assert seen["since"] == "5 min ago"  # fallback when activation time unknown


def test_since_last_start_parses_systemctl_timestamp(monkeypatch):
    fake = FakeRun([(0, "Tue 2026-07-22 10:30:00 CST\n"), (0, "n/a\n")])
    monkeypatch.setattr(doctor, "run", fake)
    assert doctor.since_last_start("hermes-gateway") == "2026-07-22 10:30:00"
    assert doctor.since_last_start("hermes-gateway") is None


def test_inside_unit_reads_cgroup(tmp_path):
    cg = tmp_path / "cgroup"
    cg.write_text("0::/user.slice/user-1000.slice/hermes-gateway.service\n")
    assert doctor.inside_unit("hermes-gateway", cgroup_path=str(cg)) is True
    cg.write_text("0::/user.slice/user-1000.slice/session-1.scope\n")
    assert doctor.inside_unit("hermes-gateway", cgroup_path=str(cg)) is False
    assert doctor.inside_unit("hermes-gateway", cgroup_path=str(tmp_path / "nope")) is False


def test_run_reports_missing_binary_without_traceback():
    r = doctor.run(["doctor-no-such-binary-xyz"])
    assert r.returncode == 127 and "command not found" in r.stderr
