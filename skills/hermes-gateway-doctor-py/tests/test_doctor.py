"""Tests for doctor.py log classification — sample lines are verbatim from the
real 2026-07-22 incident journal."""

import argparse
import json
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

# Verbatim from the 2026-07-23 calibration (72h of production journal): poll
# errors WITHOUT the "getupdates HTTP 5xx" signature — still pure noise.
CONNECT_NOISE = [
    "ERROR gateway.platforms.weixin: [Weixin] poll error (1/3): Cannot connect to host ilinkai.wechat.com:443 ssl:default [Connect call failed ('43.159.94.110', 443)]",
    "ERROR gateway.platforms.weixin: [Weixin] poll error (3/3): [Errno 104] Connection reset by peer",
    "ERROR gateway.platforms.weixin: [Weixin] poll error (3/3): Server disconnected",
]

FAILURES = [
    "ERROR gateway.platforms.weixin: [Weixin] send_document failed to=o9cq805x: CDN upload HTTP 500:",
    "ERROR gateway.platforms.base: [Weixin] Failed to send image: CDN upload HTTP 500:",
]

# v2 broadening: text sends failing are just as actionable as image/file sends
TEXT_FAILURES = [
    "ERROR gateway.platforms.weixin: [Weixin] send_text failed to=o9cq805x: iLink POST HTTP 500:",
    "ERROR gateway.platforms.base: [Weixin] Failed to send message: connection reset",
]

SESSION = [
    "WARNING gateway.platforms.weixin: Session expired; pausing for 10 minutes",
    "ERROR gateway.platforms.weixin: sendmessage failed: errcode=-14 errmsg=session timeout",
]

UNKNOWN = [
    "ERROR gateway.platforms.weixin: [Weixin] KeyError: 'msg_id' in update handler",
]

HEALTHY = [
    "INFO gateway.run: message delivered",
    "WARNING tools.registry: check_fn check_browser_requirements returned False; dependent tools will be unavailable this turn",
]


def test_noise_is_counted_not_flagged():
    c = classify(NOISE)
    assert c.send_failures == []
    assert c.session_lines == []
    assert c.unknown_errors == []
    assert c.noise == 3


def test_send_failures_detected():
    c = classify(NOISE + FAILURES + HEALTHY)
    assert len(c.send_failures) == 2
    assert c.session_lines == []
    assert c.noise == 3
    assert all("CDN upload HTTP 500" in ln for ln in c.send_failures)


def test_text_send_failures_are_actionable_too():
    # v2: "沒收到" isn't only about images — failing TEXT sends must not be
    # invisible (v1's regex only matched image/document/file/video/audio).
    c = classify(TEXT_FAILURES)
    assert len(c.send_failures) == 2
    assert c.unknown_errors == []


def test_session_expiry_detected():
    c = classify(SESSION)
    assert c.send_failures == []
    assert len(c.session_lines) == 2


def test_session_wins_over_send_on_the_same_line():
    # "sendmessage failed: errcode=-14" matches BOTH broadened SEND_FAIL and
    # SESSION_EXPIRED — it must land in session (restart cannot fix expiry).
    c = classify(["ERROR gateway.platforms.weixin: sendmessage failed: errcode=-14"])
    assert c.send_failures == []
    assert len(c.session_lines) == 1


def test_healthy_log_is_clean():
    # INFO/WARNING lines are not errors — the unknown-error catch-all only
    # bites on ERROR lines.
    c = classify(HEALTHY)
    assert (c.send_failures, c.session_lines, c.noise, c.unknown_errors) == ([], [], 0, [])


def test_poll_noise_never_masks_a_real_failure():
    # A line matching both patterns must never be swallowed as noise —
    # POLL_NOISE requires the getupdates signature, send failures don't have it.
    mixed = NOISE * 10 + FAILURES
    c = classify(mixed)
    assert len(c.send_failures) == 2
    assert c.noise == 30


def test_unknown_error_lines_are_caught_not_dropped():
    c = classify(NOISE + HEALTHY + UNKNOWN)
    assert c.unknown_errors == UNKNOWN
    assert c.send_failures == []


# --- calibration regressions (2026-07-23, 72h of production journal) ---


def test_recent_restarts_survives_a_corrupt_state_file(tmp_path):
    # The cross-death memory file may get truncated/garbled mid-write — the
    # frequency guard must degrade to 0 (allow restart), never crash restart.
    state = tmp_path / "state"
    state.mkdir()
    (state / "restarts.log").write_text("garbage\nnot-a-float\n")
    assert doctor.recent_restarts(state) == 0


def test_connect_failure_poll_errors_are_noise_not_unknown():
    # Calibration caught this: connect-level poll failures lack the
    # "getupdates HTTP 5xx" signature — a narrower POLL_NOISE let them fall
    # into the unknown-ERROR bucket and trigger a needless restart.
    c = classify(CONNECT_NOISE)
    assert c.unknown_errors == []
    assert c.send_failures == []
    assert c.noise == 3


def test_chronic_final_retry_exhaustion_is_healthy():
    # THE calibration lesson: a healthy gateway logs the (1/3)(2/3)(3/3) cycle
    # every ~90s all day (782 final-retry lines in 72h, traffic flowing fine).
    # No amount of poll-error repetition may ever produce a restart verdict.
    chronic = (NOISE + CONNECT_NOISE) * 200  # ~30-min window at real cadence
    c = classify(chronic)
    assert c.send_failures == [] and c.unknown_errors == []
    assert c.noise == len(chronic)


def test_diagnose_stays_healthy_under_chronic_poll_noise(monkeypatch, capsys):
    monkeypatch.setattr(doctor, "unit_active", lambda unit: "active")
    monkeypatch.setattr(doctor, "journal_lines",
                        lambda unit, since: (NOISE + CONNECT_NOISE) * 200 + HEALTHY)
    monkeypatch.setattr(doctor, "watchdog_usec", lambda unit: "0")
    assert doctor.main(["--prose", "diagnose"]) == 0
    assert "healthy" in capsys.readouterr().out


def test_kanban_tick_failure_lands_in_the_catch_all():
    # Real unknown-bucket resident found during calibration — documents that
    # the catch-all (not silence) is the current policy for it.
    c = classify(["ERROR gateway.run: kanban dispatcher: tick failed on board default"])
    assert len(c.unknown_errors) == 1


# --- boundary validation: caller input is LLM-generated — validate, don't trust ---


def test_broken_journal_read_is_not_healthy(monkeypatch):
    # A bad --since (or missing journalctl) must yield exit 4 "cannot read",
    # never exit 0 "healthy" derived from an empty measurement.
    monkeypatch.setattr(doctor, "journal_lines", lambda unit, since: None)
    monkeypatch.setattr(doctor, "unit_active", lambda unit: "active")
    assert doctor.main(["diagnose", "--since", "30 minutes go"]) == 4
    assert doctor.main(["--prose", "verify"]) == 4


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
    assert doctor.main(["--prose", "diagnose"]) == 1
    out = capsys.readouterr().out
    assert "ruled-out causes" in out                    # don't re-investigate false causes
    assert doctor.SUGGESTED_REPLY in out                # reply-in-text-first, message included
    assert "IGNORE" in out                              # poll noise called out as non-signal


def test_session_expired_verdict_hands_qr_rescan_to_the_user(monkeypatch, capsys):
    monkeypatch.setattr(doctor, "unit_active", lambda unit: "active")
    monkeypatch.setattr(doctor, "journal_lines", lambda unit, since: FAILURES + SESSION)
    assert doctor.main(["--prose", "diagnose"]) == 3
    out = capsys.readouterr().out
    assert "hermes gateway setup" in out
    assert "never run it via scripts" in out


def test_session_expiry_alone_escalates_without_needing_send_failures(monkeypatch, capsys):
    # v2: expiry evidence is decisive on its own (v1 only escalated when send
    # failures were ALSO present, so a pure-expiry log read as healthy).
    monkeypatch.setattr(doctor, "unit_active", lambda unit: "active")
    monkeypatch.setattr(doctor, "journal_lines", lambda unit, since: SESSION)
    assert doctor.main(["--prose", "diagnose"]) == 3
    assert "self-recover" in capsys.readouterr().out  # fresh expiry may heal itself


def test_active_but_silent_journal_is_a_hang_not_healthy(monkeypatch, capsys):
    # OpenClaw doctor's lesson: "running" is not "responding". zero journal
    # lines while active -> likely hung event loop -> restart, never "healthy".
    monkeypatch.setattr(doctor, "unit_active", lambda unit: "active")
    monkeypatch.setattr(doctor, "journal_lines", lambda unit, since: [])
    assert doctor.main(["--prose", "diagnose"]) == 1
    out = capsys.readouterr().out
    assert "hung" in out
    assert "wider --since" in out  # idle-window caveat is part of the verdict

    # ...but "not running" still wins over "silent":
    monkeypatch.setattr(doctor, "unit_active", lambda unit: "inactive")
    assert doctor.main(["--prose", "diagnose"]) == 2


def test_unknown_error_verdict_restarts_once_with_provenance(monkeypatch, capsys):
    monkeypatch.setattr(doctor, "unit_active", lambda unit: "active")
    monkeypatch.setattr(doctor, "journal_lines", lambda unit, since: HEALTHY + UNKNOWN)
    assert doctor.main(["--prose", "diagnose"]) == 1
    out = capsys.readouterr().out
    assert "unrecognized errors" in out
    assert UNKNOWN[0] in out                      # raw line shown, not paraphrased
    assert "add its pattern to doctor.py" in out  # recurrence prevention
    assert doctor.SUGGESTED_REPLY in out


def test_healthy_verdict_points_outside_the_gateway_and_reports_watchdog(monkeypatch, capsys):
    # v2: a clean gateway + a complaining user must not dead-end — the verdict
    # redirects the search (agent layer / WeChat client) and reports whether
    # the systemd watchdog (built-in hang auto-restart) is configured.
    monkeypatch.setattr(doctor, "unit_active", lambda unit: "active")
    monkeypatch.setattr(doctor, "journal_lines", lambda unit, since: NOISE + HEALTHY)
    monkeypatch.setattr(doctor, "watchdog_usec", lambda unit: "0")
    assert doctor.main(["--prose", "diagnose"]) == 0
    out = capsys.readouterr().out
    assert "OUTSIDE" in out
    assert "watchdog is OFF" in out

    monkeypatch.setattr(doctor, "watchdog_usec", lambda unit: "1min")
    assert doctor.main(["--prose", "diagnose"]) == 0
    assert "WatchdogUSec=1min" in capsys.readouterr().out


def test_verify_failure_escalates_and_success_demands_end_to_end_proof(monkeypatch, capsys):
    monkeypatch.setattr(doctor, "unit_active", lambda unit: "active")
    monkeypatch.setattr(doctor, "journal_lines", lambda unit, since: FAILURES)
    assert doctor.main(["--prose", "verify"]) == 1
    assert "hermes gateway setup" in capsys.readouterr().out

    monkeypatch.setattr(doctor, "journal_lines", lambda unit, since: HEALTHY)
    assert doctor.main(["--prose", "verify"]) == 0
    assert "re-send an image" in capsys.readouterr().out


def test_verify_unknown_error_survivor_means_blind_restart_is_spent(monkeypatch, capsys):
    # The blind-fix budget for an unknown error is exactly one restart: if it
    # is still in the log AFTER the restart, verify must escalate and demand
    # the pattern be added to the known-error library — not restart again.
    monkeypatch.setattr(doctor, "unit_active", lambda unit: "active")
    monkeypatch.setattr(doctor, "journal_lines", lambda unit, since: HEALTHY + UNKNOWN)
    assert doctor.main(["--prose", "verify"]) == 1
    out = capsys.readouterr().out
    assert "survived the restart" in out
    assert "add this error's pattern" in out
    assert UNKNOWN[0] in out


def test_diagnose_healthy_and_not_running(monkeypatch, capsys):
    monkeypatch.setattr(doctor, "journal_lines", lambda unit, since: NOISE + HEALTHY)
    monkeypatch.setattr(doctor, "unit_active", lambda unit: "active")
    monkeypatch.setattr(doctor, "watchdog_usec", lambda unit: "0")
    assert doctor.main(["--prose", "diagnose"]) == 0
    assert "healthy" in capsys.readouterr().out

    monkeypatch.setattr(doctor, "unit_active", lambda unit: "inactive")
    assert doctor.main(["--prose", "diagnose"]) == 2
    assert "systemctl --user start" in capsys.readouterr().out
    assert doctor.main(["--prose", "verify"]) == 2


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
    assert doctor.main(["--prose", *restart_argv(tmp_path)]) == 0
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
    assert doctor.main(["--prose", *restart_argv(tmp_path)]) == 1
    assert len(fake.calls) == 2  # list-timers + systemd-run, no direct restart

    # Outside the unit the fallback IS safe and must engage:
    fake = FakeRun([0, 1, 0])
    monkeypatch.setattr(doctor, "run", fake)
    monkeypatch.setattr(doctor, "inside_unit", lambda unit: False)
    assert doctor.main(["--prose", *restart_argv(tmp_path)]) == 0
    assert fake.calls[2] == ["systemctl", "--user", "restart", "hermes-gateway"]


def test_restart_does_not_stack_on_a_pending_timer(monkeypatch, tmp_path):
    # An impatient user pinging repeatedly must not queue multiple restarts.
    fake = FakeRun([(0, "Mon 2026-07-22 12:00:05 CST  5s left  -  -  "
                       "gateway-doctor-restart-123.timer  gateway-doctor-restart-123.service")])
    monkeypatch.setattr(doctor, "run", fake)
    assert doctor.main(["--prose", *restart_argv(tmp_path)]) == 0
    assert len(fake.calls) == 1  # only the list-timers probe; nothing scheduled


def test_restart_frequency_guard_escalates_instead_of_looping(monkeypatch, capsys, tmp_path):
    # The agent dies (and forgets) with every restart — this state file is the
    # cross-death memory that stops an endless restart loop.
    state = tmp_path / "state"
    doctor.note_restart(state)
    doctor.note_restart(state)
    fake = FakeRun([])
    monkeypatch.setattr(doctor, "run", fake)
    assert doctor.main(["--prose", *restart_argv(tmp_path)]) == 3
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
    assert doctor.main(["--prose", "verify"]) == 0
    assert seen["since"] == "2026-07-22 12:00:05"

    monkeypatch.setattr(doctor, "since_last_start", lambda unit: None)
    assert doctor.main(["--prose", "verify"]) == 0
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


# --- auto: unattended selfcheck (the timer's brain) ---


def test_auto_restarts_on_send_failures_with_guards(monkeypatch, capsys, tmp_path):
    monkeypatch.setattr(doctor, "unit_active", lambda unit: "active")
    monkeypatch.setattr(doctor, "journal_lines", lambda unit, since: FAILURES)
    monkeypatch.setattr(doctor, "since_last_start", lambda unit: None)
    fake = FakeRun([0, 0])  # list-timers, systemd-run
    monkeypatch.setattr(doctor, "run", fake)
    monkeypatch.setattr(doctor, "inside_unit", lambda unit: False)
    assert doctor.main(["--prose", "auto", "--state-dir", str(tmp_path / "s")]) == 0
    assert fake.calls[1][0] == "systemd-run"  # went through the guarded restart path
    assert "unattended" in capsys.readouterr().out


def test_auto_starts_a_dead_unit_instead_of_restarting(monkeypatch, capsys, tmp_path):
    monkeypatch.setattr(doctor, "unit_active", lambda unit: "inactive")
    monkeypatch.setattr(doctor, "journal_lines", lambda unit, since: [])
    monkeypatch.setattr(doctor, "since_last_start", lambda unit: None)
    fake = FakeRun([0])
    monkeypatch.setattr(doctor, "run", fake)
    assert doctor.main(["--prose", "auto", "--state-dir", str(tmp_path / "s")]) == 0
    assert fake.calls[0] == ["systemctl", "--user", "start", "hermes-gateway"]


def test_auto_hang_is_report_only(monkeypatch, capsys, tmp_path):
    # Unattended absence-of-logs must never restart: a live gateway is never
    # silent for long (chronic poll noise), but the cost of being wrong here is
    # an unattended restart loop at 3am. WatchdogSec owns real hangs.
    monkeypatch.setattr(doctor, "unit_active", lambda unit: "active")
    monkeypatch.setattr(doctor, "journal_lines", lambda unit, since: [])
    monkeypatch.setattr(doctor, "since_last_start", lambda unit: None)
    fake = FakeRun([])
    monkeypatch.setattr(doctor, "run", fake)
    assert doctor.main(["--prose", "auto", "--state-dir", str(tmp_path / "s")]) == 1
    assert fake.calls == []  # no restart, no start — report only
    assert "REPORT-ONLY" in capsys.readouterr().out


def test_auto_bounds_window_at_a_recent_unit_start(monkeypatch, tmp_path):
    # Pre-restart failures still sit inside "3 hours ago" — without the bound,
    # every tick would re-see them and restart again until the rate guard trips.
    seen = {}

    def fake_journal(unit, since):
        seen["since"] = since
        return HEALTHY

    recent = doctor.time.strftime("%Y-%m-%d %H:%M:%S",
                                  doctor.time.localtime(doctor.time.time() - 60))
    monkeypatch.setattr(doctor, "unit_active", lambda unit: "active")
    monkeypatch.setattr(doctor, "journal_lines", fake_journal)
    monkeypatch.setattr(doctor, "since_last_start", lambda unit: recent)
    monkeypatch.setattr(doctor, "watchdog_usec", lambda unit: "0")
    assert doctor.main(["--prose", "auto", "--state-dir", str(tmp_path / "s")]) == 0
    assert seen["since"] == recent


def test_auto_session_expiry_surfaces_as_exit_3(monkeypatch, tmp_path):
    # The selfcheck unit going "failed" is how the operator finds out — auto
    # must not swallow it, and must not try a (useless) restart.
    monkeypatch.setattr(doctor, "unit_active", lambda unit: "active")
    monkeypatch.setattr(doctor, "journal_lines", lambda unit, since: SESSION)
    monkeypatch.setattr(doctor, "since_last_start", lambda unit: None)
    fake = FakeRun([])
    monkeypatch.setattr(doctor, "run", fake)
    assert doctor.main(["--prose", "auto", "--state-dir", str(tmp_path / "s")]) == 3
    assert fake.calls == []


# --- --json: the agent reads FIELDS, never scrapes prose ---


def test_json_diagnose_restart_verdict_is_machine_readable(monkeypatch, capsys):
    monkeypatch.setattr(doctor, "unit_active", lambda unit: "active")
    monkeypatch.setattr(doctor, "journal_lines", lambda unit, since: NOISE + FAILURES)
    assert doctor.main(["--json", "diagnose"]) == 1
    data = json.loads(capsys.readouterr().out)  # loads() proves stdout is ONLY json
    assert data["cmd"] == "diagnose" and data["exit"] == 1
    assert data["verdict"] == "send-failures"
    assert data["suggested_reply"] == doctor.SUGGESTED_REPLY
    assert any("restart" in step for step in data["next"])
    assert any("CDN upload HTTP 500" in ln for ln in data["evidence"])
    assert data["noise"] == 3


def test_json_diagnose_healthy_carries_watchdog_and_next(monkeypatch, capsys):
    monkeypatch.setattr(doctor, "unit_active", lambda unit: "active")
    monkeypatch.setattr(doctor, "journal_lines", lambda unit, since: HEALTHY)
    monkeypatch.setattr(doctor, "watchdog_usec", lambda unit: "0")
    assert doctor.main(["--json", "diagnose"]) == 0
    data = json.loads(capsys.readouterr().out)
    assert data["verdict"] == "healthy" and data["watchdog_usec"] == "0"
    assert any("OUTSIDE" in step for step in data["next"])


def test_json_restart_scheduled_contract(monkeypatch, capsys, tmp_path):
    fake = FakeRun([0, 0])
    monkeypatch.setattr(doctor, "run", fake)
    monkeypatch.setattr(doctor, "inside_unit", lambda unit: True)
    assert doctor.main(["--json", *restart_argv(tmp_path)]) == 0
    data = json.loads(capsys.readouterr().out)
    assert data["verdict"] == "scheduled" and data["delay_s"] == 5
    assert data["suggested_reply"] == doctor.SUGGESTED_REPLY
    assert data["self_kill"] is True
    assert data["next"][0].startswith("reply to the user NOW")


def test_json_verify_unknown_survivor_demands_pattern_and_test(monkeypatch, capsys):
    monkeypatch.setattr(doctor, "unit_active", lambda unit: "active")
    monkeypatch.setattr(doctor, "journal_lines", lambda unit, since: UNKNOWN)
    assert doctor.main(["--json", "verify"]) == 1
    data = json.loads(capsys.readouterr().out)
    assert data["verdict"] == "unknown-error-survived"
    assert data["evidence"] == UNKNOWN
    # the 入庫 gate is part of the contract: pattern + test + pytest, not just "edit the file"
    assert any("pytest" in step for step in data["next"])


def test_piped_stdout_defaults_to_json():
    # The agent always consumes doctor through a pipe — it must get fields
    # WITHOUT remembering any flag (the old "一律帶 --json" prose rule, now code).
    # Prose is reserved for a human at a real TTY (or --prose).
    r = subprocess.run([sys.executable, doctor.__file__, "diagnose"],
                       capture_output=True, text=True)
    data = json.loads(r.stdout)  # whatever the verdict, stdout must be pure JSON
    assert data["cmd"] == "diagnose"


def test_escalation_is_routed_to_the_operator_not_the_visitor(monkeypatch, capsys):
    # The complaining WeChat user may be a visitor; QR re-scan/SSH belongs to
    # the machine owner. The routing lives in the verdict fields, not in prose.
    monkeypatch.setattr(doctor, "unit_active", lambda unit: "active")
    monkeypatch.setattr(doctor, "journal_lines", lambda unit, since: SESSION)
    assert doctor.main(["--json", "diagnose"]) == 3
    data = json.loads(capsys.readouterr().out)
    assert any("OPERATOR" in step for step in data["next"])


def test_json_mode_state_does_not_leak_between_invocations(monkeypatch, capsys):
    # main() must reset json mode and fields each call — a --json run followed
    # by a prose run (and vice versa) must not mix outputs or stale verdicts.
    monkeypatch.setattr(doctor, "unit_active", lambda unit: "active")
    monkeypatch.setattr(doctor, "journal_lines", lambda unit, since: NOISE + FAILURES)
    assert doctor.main(["--json", "diagnose"]) == 1
    assert json.loads(capsys.readouterr().out)["verdict"] == "send-failures"

    monkeypatch.setattr(doctor, "journal_lines", lambda unit, since: HEALTHY)
    monkeypatch.setattr(doctor, "watchdog_usec", lambda unit: "0")
    assert doctor.main(["--prose", "diagnose"]) == 0
    out = capsys.readouterr().out
    assert "healthy" in out and not out.lstrip().startswith("{")  # prose mode back

    assert doctor.main(["--json", "diagnose"]) == 0
    data = json.loads(capsys.readouterr().out)
    assert data["verdict"] == "healthy"
    assert "evidence" not in data  # stale send-failure fields must not leak
