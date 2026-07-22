#!/usr/bin/env python3
"""hermes-gateway-doctor: diagnose / restart / verify the hermes-gateway systemd user service.

Failure mode: WeChat text OK but every image/file send fails "CDN upload HTTP 500"
— stale iLink session state in the long-running gateway; fix = restart (see
EXCLUDED_CAUSES; QR re-scan only if failures persist, see ESCALATE).

Self-restart trap: the agent runs INSIDE hermes-gateway.service (nohup'd children
share the cgroup and die with it), so `restart` schedules a detached delayed
restart via `systemd-run --user --on-active=Ns`, outside the gateway's cgroup.

Python 3 stdlib only.
"""

import argparse
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

# Real send failures (actionable): e.g.
#   ERROR gateway.platforms.weixin: [Weixin] send_document failed to=...: CDN upload HTTP 500:
#   ERROR gateway.platforms.base: [Weixin] Failed to send image: CDN upload HTTP 500:
SEND_FAIL = re.compile(r"send_document failed|Failed to send (image|document|file|video|audio)")

# Harmless background noise (NOT a health signal — observed on every poll cycle
# even while real traffic flows fine): e.g.
#   ERROR gateway.platforms.weixin: [Weixin] poll error (1/3): iLink POST ilink/bot/getupdates HTTP 524:
POLL_NOISE = re.compile(r"poll error \(\d/\d\).*getupdates HTTP 5\d\d")

# Genuine session expiry (restart won't fix — needs QR re-scan by the user):
SESSION_EXPIRED = re.compile(r"Session expired|session timeout|errcode=-14")

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


def classify(lines):
    """Split journal lines into (send_failures, session_expiry_lines, noise_count)."""
    send_failures, session_lines, noise = [], [], 0
    for ln in lines:
        if POLL_NOISE.search(ln):
            noise += 1
        elif SEND_FAIL.search(ln):
            send_failures.append(ln.rstrip())
        elif SESSION_EXPIRED.search(ln):
            session_lines.append(ln.rstrip())
    return send_failures, session_lines, noise


def run(cmd, **kw):
    try:
        return subprocess.run(cmd, capture_output=True, text=True, **kw)
    except FileNotFoundError:
        # e.g. journalctl/systemctl missing (dev machine) — report cleanly, don't traceback
        return subprocess.CompletedProcess(cmd, 127, "", f"{cmd[0]}: command not found")


def journal_lines(unit, since):
    """Journal lines, or None if journalctl failed (bad --since etc.) — None vs []
    matters: a broken measurement must never read as "no failures = healthy"."""
    r = run(["journalctl", "--user", "-u", unit, "--since", since, "--no-pager", "-o", "cat"])
    if r.returncode != 0:
        print(f"[doctor] journalctl failed: {r.stderr.strip()}", file=sys.stderr)
        return None
    return r.stdout.splitlines()


def unit_active(unit):
    r = run(["systemctl", "--user", "is-active", unit])
    return r.stdout.strip() or f"unknown ({r.stderr.strip()})"


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


def cmd_diagnose(args):
    state = unit_active(args.unit)
    lines = journal_lines(args.unit, args.since)
    if lines is None:
        print(f"VERDICT: cannot read journal (bad --since {args.since!r}? journalctl missing?) "
              "— no health claim possible.")
        return 4
    send_failures, session_lines, noise = classify(lines)

    print(f"service: {state}")
    print(f"window:  since {args.since!r}, {len(lines)} log lines")
    print(f"noise:   {noise} getupdates-poll 5xx lines (IGNORE — not a health signal)")

    if state != "active":
        print("\nVERDICT: service not running -> start it: "
              f"systemctl --user start {args.unit}")
        return 2
    if send_failures:
        print(f"\n{len(send_failures)} real send failure(s):")
        for ln in send_failures[-5:]:
            print(f"  {ln}")
        if session_lines:
            print("\nSession-expiry evidence found (restart will NOT fix this):")
            for ln in session_lines[-3:]:
                print(f"  {ln}")
            print(f"\nVERDICT: session expired -> {ESCALATE}")
            return 3
        print("\nruled-out causes (do not re-investigate): " + "; ".join(EXCLUDED_CAUSES))
        print("VERDICT: stale gateway state -> restart recommended.")
        print(f"next: reply to the user in TEXT first (text still works), e.g. \"{SUGGESTED_REPLY}\", "
              "then: doctor.py restart")
        return 1
    print("\nVERDICT: healthy (real sends OK; poll noise is expected).")
    return 0


def cmd_restart(args):
    n = recent_restarts(args.state_dir)
    if n >= 2 and not args.force:
        print(f"[doctor] {n} doctor restarts within the last hour — another restart is "
              f"unlikely to help. Escalate instead: {ESCALATE}")
        print("(--force restarts anyway)")
        return 3
    if pending_restart():
        print("a doctor restart is already scheduled (pending timer) — not stacking another.")
        return 0
    self_kill = inside_unit(args.unit)
    if self_kill:
        print(f"[doctor] running INSIDE {args.unit}.service — the restart will kill this "
              f"process too. Reply to the user BEFORE this fires, e.g. \"{SUGGESTED_REPLY}\".")
    tname = f"gateway-doctor-restart-{int(time.time())}"
    r = run(["systemd-run", "--user", "--collect", f"--on-active={args.delay}s",
             "--unit", tname,
             "systemctl", "--user", "restart", args.unit])
    if r.returncode != 0:
        print(f"[doctor] systemd-run failed: {r.stderr.strip()}", file=sys.stderr)
        if not self_kill:
            print("[doctor] falling back to direct restart (safe: not inside the unit)")
            r2 = run(["systemctl", "--user", "restart", args.unit])
            if r2.returncode != 0:
                print(f"[doctor] direct restart failed: {r2.stderr.strip()}", file=sys.stderr)
                return 1
            note_restart(args.state_dir)
            print("restarted.")
            return 0
        return 1
    note_restart(args.state_dir)
    print(f"restart of {args.unit} scheduled in {args.delay}s (transient unit {tname}).")
    print("next: after ~30s run `doctor.py verify`, then ask the user to actually re-send "
          "an image (end-to-end proof) and run verify once more.")
    print("include in the reply: if the bot stays silent for ~2 min, the gateway did not "
          f"come back — someone must SSH in and run `systemctl --user status {args.unit}`.")
    return 0


def cmd_verify(args):
    state = unit_active(args.unit)
    since = args.since or since_last_start(args.unit) or "5 min ago"
    lines = journal_lines(args.unit, since)
    if lines is None:
        print(f"VERDICT: cannot read journal (bad --since {since!r}? journalctl missing?) "
              "— cannot verify.")
        return 4
    send_failures, session_lines, _ = classify(lines)
    print(f"service: {state}")
    print(f"window:  since {since!r} (bounded at last unit start when --since not given)")
    if state != "active":
        print("VERDICT: service NOT active after restart — inspect: "
              f"journalctl --user -u {args.unit} -n 50")
        return 2
    if send_failures:
        print(f"VERDICT: still {len(send_failures)} send failure(s) since {since!r} — "
              f"escalate: {ESCALATE}")
        return 1
    print(f"VERDICT: no send failures since {since!r}.")
    print("next: ask the user to actually re-send an image (end-to-end proof), then run "
          "verify once more; only then consider it fixed.")
    return 0


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--unit", default=DEFAULT_UNIT, type=unit_name,
                   help=f"systemd user unit (default: {DEFAULT_UNIT})")
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
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
