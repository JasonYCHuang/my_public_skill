#!/usr/bin/env python3
"""hermes-gateway-doctor: diagnose / restart / verify the hermes-gateway systemd user service.

v2 — generalized self-healing triage. Entry: ANY vague complaint (didn't
receive / no reply / bot silent / image send fails). diagnose classifies the
journal against a known-error library and prints ONE verdict, in this order:

  not running -> start  |  session expired -> QR re-scan (restart useless)
  |  active-but-silent hang -> restart  |  any send failure (text too) -> restart
  |  poll exhaustion spanning >10 min -> restart (single bursts self-recover:
  the adapter backs off 10 min and retries)  |  unknown ERROR -> restart ONCE,
  then escalate + add the pattern here  |  clean -> look outside the gateway.

Guardrails that keep "auto" from becoming "runaway": getupdates 5xx poll noise
is never a signal (it appears when healthy too); >=3 restarts/hour escalates
instead of looping; every unknown error gets blind-fixed at most once.

Restart path: ALWAYS `systemctl --user restart` (via a detached systemd-run
timer). NEVER `hermes gateway restart` — it signals SIGUSR1 into the asyncio
loop and fails exactly when the gateway is hung (upstream issue #12438).

Self-restart trap: the agent runs INSIDE hermes-gateway.service (nohup'd children
share the cgroup and die with it), so `restart` schedules a detached delayed
restart via `systemd-run --user --on-active=Ns`, outside the gateway's cgroup.

Python 3 stdlib only.
"""

import argparse
import collections
import json
import pathlib
import re
import subprocess
import sys
import time

DEFAULT_UNIT = "hermes-gateway"

# systemd unit-name charset; no leading "-" (would parse as a flag). Caller
# input is LLM-generated — validate, don't trust.
UNIT_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9:_.@-]*$")


def unit_name(s):
    """argparse type: a plausible systemd unit name."""
    if not UNIT_NAME.match(s):
        raise argparse.ArgumentTypeError(f"invalid unit name: {s!r}")
    return s


def positive_int(s):
    """argparse type: integer >= 1 (restart delay)."""
    n = int(s)
    if n < 1:
        raise argparse.ArgumentTypeError(f"must be >= 1, got {n}")
    return n

# Real send failures (actionable), ANY payload type INCLUDING text: e.g.
#   ERROR gateway.platforms.weixin: [Weixin] send_document failed to=...: CDN upload HTTP 500:
#   ERROR gateway.platforms.base: [Weixin] Failed to send image: CDN upload HTTP 500:
#   ... send_text failed ... / ... Failed to send message ...
SEND_FAIL = re.compile(r"\bsend_?\w* failed|Failed to send \w+")

# Harmless background noise (NOT a health signal — observed on every poll cycle
# even while real traffic flows fine): e.g.
#   ERROR gateway.platforms.weixin: [Weixin] poll error (1/3): iLink POST ilink/bot/getupdates HTTP 524:
POLL_NOISE = re.compile(r"poll error \(\d/\d\).*getupdates HTTP 5\d\d")

# The FINAL retry of a poll burst, e.g. "poll error (3/3): ...". ONE exhausted
# burst is still not actionable — the adapter self-backoffs 10 minutes and
# usually recovers (hermes-wechat adapter docs). Only repeated bursts spanning
# MORE than one backoff window (EXHAUST_SPAN_S) mean inbound is really broken.
POLL_EXHAUST = re.compile(r"poll error \((\d+)/\1\)")
EXHAUST_SPAN_S = 600

# Genuine session/token expiry (restart won't fix — needs QR re-scan by the user).
# Checked BEFORE SEND_FAIL: "sendmessage failed: errcode=-14" is expiry, not a
# restartable send failure.
SESSION_EXPIRED = re.compile(r"Session expired|session timeout|[Tt]oken expired|errcode=-14")

# Catch-all for ERROR lines no pattern above recognises: restart ONCE (most
# unknown errors are stale state); if the SAME error survives the restart,
# escalate AND add its pattern above — blind-fix each new error at most once.
UNKNOWN_ERR = re.compile(r"\bERROR\b")

# journalctl -o short-iso line prefix, e.g. "2026-07-22T12:34:56+0800 host ..."
ISO_TS = re.compile(r"^(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})")

# Ruled out in the 2026-07-22 incident; printed with the restart verdict:
EXCLUDED_CAUSES = (
    "Tencent-side outage",
    "file size (a 121KB file failed too)",
    "non-ASCII filename (ASCII-only retry failed the same way)",
)

# Text still works in this failure mode — reply BEFORE the restart fires:
SUGGESTED_REPLY = "圖片傳送失敗，我重啟一下 gateway，約 30 秒後請再叫我重傳"

# Escalation is user-only: interactive + secrets — never scripted.
ESCALATE = ("user must re-run `hermes gateway setup` THEMSELVES (QR re-scan; "
            "interactive + secrets — never run it via scripts), then "
            "`systemctl --user restart hermes-gateway` from their own shell "
            "(no self-restart trap there).")


# --- output: prose for humans, --json for the agent -------------------------
# The agent must read FIELDS (verdict/next/suggested_reply/evidence), never
# scrape prose. say() feeds both; note() sets fields; finish() emits.

_MODE = {"json": False}
_OUT = {}
_LINES = []


def say(text=""):
    _LINES.append(text)
    if not _MODE["json"]:
        print(text)


def note(**fields):
    _OUT.update(fields)


def finish(code):
    if _MODE["json"]:
        print(json.dumps(dict(_OUT, exit=code, transcript=_LINES), ensure_ascii=False))
    return code


Classified = collections.namedtuple(
    "Classified", "send_failures session_lines noise exhaust_ts unknown_errors")


def line_ts(ln):
    """Epoch seconds from a journalctl -o short-iso line, else None.

    Malformed-but-digit-shaped stamps ("2026-19-99T...") must degrade to None,
    not crash the whole diagnosis — a broken measurement never becomes a traceback."""
    m = ISO_TS.match(ln)
    if not m:
        return None
    try:
        return time.mktime(time.strptime(m.group(1), "%Y-%m-%dT%H:%M:%S"))
    except (ValueError, OverflowError):
        return None


def classify(lines):
    """Sort journal lines into the known-error library's buckets.

    Order matters: expiry markers can sit on a send-failure line
    ("sendmessage failed: errcode=-14") — session must win, because a restart
    cannot fix it. Poll noise wins over everything: it is never a signal."""
    c = Classified([], [], 0, [], [])
    noise = 0
    for ln in lines:
        if POLL_NOISE.search(ln):
            noise += 1
            if POLL_EXHAUST.search(ln):
                ts = line_ts(ln)
                if ts is not None:
                    c.exhaust_ts.append(ts)
        elif SESSION_EXPIRED.search(ln):
            c.session_lines.append(ln.rstrip())
        elif SEND_FAIL.search(ln):
            c.send_failures.append(ln.rstrip())
        elif UNKNOWN_ERR.search(ln):
            c.unknown_errors.append(ln.rstrip())
    return c._replace(noise=noise)


def inbound_broken(exhaust_ts):
    """Repeated poll-retry exhaustion spanning more than one adapter backoff
    window — inbound is broken and will NOT self-recover; a single burst would."""
    return len(exhaust_ts) >= 2 and max(exhaust_ts) - min(exhaust_ts) > EXHAUST_SPAN_S


def run(cmd, **kw):
    try:
        return subprocess.run(cmd, capture_output=True, text=True, **kw)
    except FileNotFoundError:
        # e.g. journalctl/systemctl missing (dev machine) — report cleanly, don't traceback
        return subprocess.CompletedProcess(cmd, 127, "", f"{cmd[0]}: command not found")


def journal_lines(unit, since):
    """Journal lines, or None if journalctl failed (bad --since etc.) — None vs []
    matters: a broken measurement must never read as "no failures = healthy"."""
    # short-iso (not cat): the timestamps feed the inbound exhaustion-span check
    r = run(["journalctl", "--user", "-u", unit, "--since", since, "--no-pager", "-o", "short-iso"])
    if r.returncode != 0:
        print(f"[doctor] journalctl failed: {r.stderr.strip()}", file=sys.stderr)
        return None
    return r.stdout.splitlines()


def unit_active(unit):
    r = run(["systemctl", "--user", "is-active", unit])
    return r.stdout.strip() or f"unknown ({r.stderr.strip()})"


def watchdog_usec(unit):
    """WatchdogUSec of the unit ("0" = no systemd watchdog configured)."""
    r = run(["systemctl", "--user", "show", unit, "-p", "WatchdogUSec", "--value"])
    return r.stdout.strip()


def since_last_start(unit):
    """--since bound at the unit's last activation, so verify never counts
    failures from BEFORE the restart (false 'still failing' -> false QR escalation)."""
    r = run(["systemctl", "--user", "show", unit, "-p", "ActiveEnterTimestamp", "--value"])
    m = re.search(r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}", r.stdout)
    return m.group(0) if m else None


def pending_restart():
    """True if a doctor-scheduled restart timer is already waiting to fire."""
    r = run(["systemctl", "--user", "list-timers", "gateway-doctor-restart-*",
             "--no-legend", "--plain"])
    return r.returncode == 0 and bool(r.stdout.strip())


def recent_restarts(state_dir, window_s=3600):
    """How many doctor restarts fired in the last hour — the agent dies with each
    restart and forgets; this file is the memory that survives it."""
    try:
        stamps = (pathlib.Path(state_dir) / "restarts.log").read_text().split()
        return sum(1 for t in stamps if time.time() - float(t) < window_s)
    except (OSError, ValueError):
        return 0


def note_restart(state_dir):
    p = pathlib.Path(state_dir)
    p.mkdir(parents=True, exist_ok=True)
    with open(p / "restarts.log", "a") as f:
        f.write(f"{time.time()}\n")


def inside_unit(unit, cgroup_path="/proc/self/cgroup"):
    """True if this process runs inside <unit>.service's cgroup (self-restart trap)."""
    try:
        with open(cgroup_path) as f:
            return f"{unit}.service" in f.read()
    except OSError:  # non-Linux (e.g. dev on macOS)
        return False


def _next_restart():
    note(suggested_reply=SUGGESTED_REPLY,
         next=["send suggested_reply to the user as TEXT first",
               "python3 scripts/doctor.py restart"])
    say(f"next: TRY a text reply to the user first, e.g. \"{SUGGESTED_REPLY}\", "
        "then: doctor.py restart")
    say("(restart goes via systemctl — NEVER `hermes gateway restart`: it signals "
        "SIGUSR1 into the asyncio loop and fails exactly when the gateway is sick)")


def cmd_diagnose(args):
    state = unit_active(args.unit)
    lines = journal_lines(args.unit, args.since)
    if lines is None:
        note(verdict="no-journal")
        say(f"VERDICT: cannot read journal (bad --since {args.since!r}? journalctl missing?) "
            "— no health claim possible.")
        return finish(4)
    c = classify(lines)
    note(service=state, since=args.since, log_lines=len(lines), noise=c.noise)

    say(f"service: {state}")
    say(f"window:  since {args.since!r}, {len(lines)} log lines")
    say(f"noise:   {c.noise} getupdates-poll 5xx lines (IGNORE — not a health signal)")

    if state != "active":
        note(verdict="not-running", next=[f"systemctl --user start {args.unit}"])
        say("\nVERDICT: service not running -> start it: "
            f"systemctl --user start {args.unit}")
        return finish(2)
    if c.session_lines:
        note(verdict="session-expired", evidence=c.session_lines[-3:],
             next=["if evidence is fresh (<15 min): re-run diagnose in ~15 min — the "
                   "adapter may self-recover after its 10-min pause",
                   "else escalate: user re-runs `hermes gateway setup` THEMSELVES, then "
                   "restarts from their own shell"])
        say("\nSession/token-expiry evidence (restart will NOT fix this):")
        for ln in c.session_lines[-3:]:
            say(f"  {ln}")
        say(f"\nVERDICT: session expired -> {ESCALATE}")
        say("(a JUST-expired token may still self-recover: the adapter pauses 10 min "
            "and retries — if the evidence is fresh, re-run diagnose in ~15 min "
            "before doing the QR re-scan)")
        return finish(3)
    if not lines:
        note(verdict="hang")
        say("\nVERDICT: service is active but logged NOTHING in the window — likely "
            "hung ('running' is not 'responding'); restart recommended.")
        say("(a genuinely idle gateway can also be silent — if in doubt, re-run with "
            "a wider --since first)")
        _next_restart()
        return finish(1)
    if c.send_failures:
        note(verdict="send-failures", evidence=c.send_failures[-5:])
        say(f"\n{len(c.send_failures)} real send failure(s):")
        for ln in c.send_failures[-5:]:
            say(f"  {ln}")
        say("\nruled-out causes (do not re-investigate): " + "; ".join(EXCLUDED_CAUSES))
        say("VERDICT: stale gateway state -> restart recommended.")
        _next_restart()
        return finish(1)
    if inbound_broken(c.exhaust_ts):
        note(verdict="inbound-broken", exhausted_bursts=len(c.exhaust_ts))
        say(f"\npoll retries exhausted {len(c.exhaust_ts)}x spanning >10 min — the "
            "adapter's built-in 10-min backoff is not recovering.")
        say("VERDICT: inbound (getupdates) broken -> restart recommended.")
        _next_restart()
        return finish(1)
    if c.unknown_errors:
        note(verdict="unknown-errors", evidence=c.unknown_errors[-3:])
        say(f"\n{len(c.unknown_errors)} ERROR line(s) matching NO known pattern:")
        for ln in c.unknown_errors[-3:]:
            say(f"  {ln}")
        say("\nVERDICT: unrecognized errors -> restart ONCE (most unknown errors are "
            "stale state). If the SAME error survives the restart, escalate to the "
            "user AND add its pattern to doctor.py — blind-fix each new error at most once.")
        _next_restart()
        return finish(1)
    wd = watchdog_usec(args.unit)
    note(verdict="healthy", watchdog_usec=wd,
         next=["if the user still complains: look OUTSIDE the gateway (agent layer, "
               "WeChat client) — ask the user to send a test message for end-to-end proof"])
    say("\nVERDICT: healthy (real sends OK; poll noise is expected).")
    say("if the user still reports missed/ignored messages: the gateway is clean — "
        "look OUTSIDE it (agent layer, WeChat client). next: ask the user to send "
        "a test message for end-to-end proof.")
    if wd in ("", "0"):
        say("note: systemd watchdog is OFF for this unit — consider Type=notify + "
            "WatchdogSec so systemd auto-restarts a hung event loop.")
    else:
        say(f"watchdog: WatchdogUSec={wd} (systemd auto-restarts a hung loop)")
    return finish(0)


def cmd_restart(args):
    n = recent_restarts(args.state_dir)
    if n >= 2 and not args.force:
        note(verdict="restart-budget-exhausted", recent_restarts=n,
             next=["do NOT restart again — escalate (QR re-scan path)"])
        say(f"[doctor] {n} doctor restarts within the last hour — another restart is "
            f"unlikely to help. Escalate instead: {ESCALATE}")
        say("(--force restarts anyway)")
        return finish(3)
    if pending_restart():
        note(verdict="already-scheduled", next=["wait for the pending timer, then verify"])
        say("a doctor restart is already scheduled (pending timer) — not stacking another.")
        return finish(0)
    self_kill = inside_unit(args.unit)
    if self_kill:
        say(f"[doctor] running INSIDE {args.unit}.service — the restart will kill this "
            f"process too. Reply to the user BEFORE this fires, e.g. \"{SUGGESTED_REPLY}\".")
    tname = f"gateway-doctor-restart-{int(time.time())}"
    r = run(["systemd-run", "--user", "--collect", f"--on-active={args.delay}s",
             "--unit", tname,
             "systemctl", "--user", "restart", args.unit])
    if r.returncode != 0:
        print(f"[doctor] systemd-run failed: {r.stderr.strip()}", file=sys.stderr)
        if not self_kill:
            say("[doctor] falling back to direct restart (safe: not inside the unit)")
            r2 = run(["systemctl", "--user", "restart", args.unit])
            if r2.returncode != 0:
                print(f"[doctor] direct restart failed: {r2.stderr.strip()}", file=sys.stderr)
                note(verdict="restart-failed")
                return finish(1)
            note_restart(args.state_dir)
            note(verdict="restarted-direct",
                 next=["python3 scripts/doctor.py verify",
                       "ask the user to actually re-send an image (end-to-end proof)",
                       "run verify once more"])
            say("restarted.")
            return finish(0)
        note(verdict="restart-failed")
        return finish(1)
    note_restart(args.state_dir)
    note(verdict="scheduled", delay_s=args.delay, transient_unit=tname,
         suggested_reply=SUGGESTED_REPLY, self_kill=self_kill,
         next=["reply to the user NOW (before the timer fires)",
               "after ~30s: python3 scripts/doctor.py verify",
               "ask the user to actually re-send an image (end-to-end proof)",
               "run verify once more"])
    say(f"restart of {args.unit} scheduled in {args.delay}s (transient unit {tname}).")
    say("next: after ~30s run `doctor.py verify`, then ask the user to actually re-send "
        "an image (end-to-end proof) and run verify once more.")
    say("include in the reply: if the bot stays silent for ~2 min, the gateway did not "
        f"come back — someone must SSH in and run `systemctl --user status {args.unit}`.")
    return finish(0)


def cmd_verify(args):
    state = unit_active(args.unit)
    since = args.since or since_last_start(args.unit) or "5 min ago"
    lines = journal_lines(args.unit, since)
    if lines is None:
        note(verdict="no-journal", since=since)
        say(f"VERDICT: cannot read journal (bad --since {since!r}? journalctl missing?) "
            "— cannot verify.")
        return finish(4)
    c = classify(lines)
    note(service=state, since=since)
    say(f"service: {state}")
    say(f"window:  since {since!r} (bounded at last unit start when --since not given)")
    if state != "active":
        note(verdict="not-active-after-restart",
             next=[f"journalctl --user -u {args.unit} -n 50"])
        say("VERDICT: service NOT active after restart — inspect: "
            f"journalctl --user -u {args.unit} -n 50")
        return finish(2)
    if c.send_failures or c.session_lines:
        note(verdict="still-failing",
             evidence=(c.send_failures + c.session_lines)[-5:],
             next=["escalate: user re-runs `hermes gateway setup` THEMSELVES (QR re-scan)"])
        say(f"VERDICT: still {len(c.send_failures) + len(c.session_lines)} failure(s) "
            f"since {since!r} — escalate: {ESCALATE}")
        return finish(1)
    if c.unknown_errors:
        note(verdict="unknown-error-survived", evidence=c.unknown_errors[-3:],
             next=["escalate to the user",
                   "add this error's pattern to doctor.py, add a test, run pytest"])
        say("VERDICT: unrecognized error(s) survived the restart — blind-restart is "
            f"spent. Escalate: {ESCALATE}")
        say("and add this error's pattern to doctor.py (known-error library) so next "
            "time it is diagnosed, not blind-fixed:")
        for ln in c.unknown_errors[-3:]:
            say(f"  {ln}")
        return finish(1)
    note(verdict="clean",
         next=["ask the user to actually re-send an image (end-to-end proof)",
               "run verify once more; only then consider it fixed"])
    say(f"VERDICT: no send failures since {since!r}.")
    say("next: ask the user to actually re-send an image (end-to-end proof), then run "
        "verify once more; only then consider it fixed.")
    return finish(0)


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--unit", default=DEFAULT_UNIT, type=unit_name,
                   help=f"systemd user unit (default: {DEFAULT_UNIT})")
    p.add_argument("--json", action="store_true",
                   help="emit ONE machine-readable JSON verdict on stdout (fields: "
                        "verdict/next/suggested_reply/evidence/exit) instead of prose")
    sub = p.add_subparsers(dest="cmd", required=True)

    d = sub.add_parser("diagnose", help="classify recent journal lines, print verdict")
    d.add_argument("--since", default="30 min ago")
    d.set_defaults(fn=cmd_diagnose)

    r = sub.add_parser("restart", help="schedule a detached delayed restart (self-restart safe)")
    r.add_argument("--delay", type=positive_int, default=5,
                   help="seconds before restart fires (default 5, min 1)")
    r.add_argument("--state-dir", default=str(pathlib.Path.home() / ".local/state/hermes-gateway-doctor"),
                   help="where restart timestamps persist across agent deaths")
    r.add_argument("--force", action="store_true",
                   help="bypass the 3-restarts-per-hour guard")
    r.set_defaults(fn=cmd_restart)

    v = sub.add_parser("verify", help="post-restart check: service active + no new send failures")
    v.add_argument("--since", default=None,
                   help="window start (default: the unit's last activation, else '5 min ago')")
    v.set_defaults(fn=cmd_verify)

    args = p.parse_args(argv)
    _MODE["json"] = args.json
    _OUT.clear()
    _OUT.update({"cmd": args.cmd, "unit": args.unit})
    _LINES.clear()
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
