#!/usr/bin/env python3
"""Ubuntu（hermes agent）用：systemd user timer，每小時跑 cleanup.py 刪過期分享。

    python3 install_systemd.py install [--root DIR]
    python3 install_systemd.py status
    python3 install_systemd.py run-now
    python3 install_systemd.py uninstall

Persistent=true：停機錯過的班次開機後補跑。無人值守機器記得開 linger，
否則沒登入 session 時 user timer 不會跑：
    loginctl enable-linger $USER
"""

from __future__ import annotations

import argparse
import getpass
import subprocess
import sys
from pathlib import Path

UNIT = "share-link-cleanup"
UNIT_DIR = Path.home() / ".config/systemd/user"
CLEANUP_PY = (Path(__file__).parent / "cleanup.py").resolve()


def sh(*cmd: str, check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True, check=check)


def build_units(prog: list[str]) -> tuple[str, str]:
    """回傳 (service 內容, timer 內容)。抽成純函式讓沒有 systemd 的機器也測得到。"""
    service = f"""[Unit]
Description=Delete expired share-link publishes

[Service]
Type=oneshot
ExecStart={" ".join(prog)}
"""
    timer = f"""[Unit]
Description=Run {UNIT} hourly

[Timer]
OnCalendar=*-*-* *:15:00
Persistent=true

[Install]
WantedBy=timers.target
"""
    return service, timer


def install(args: argparse.Namespace) -> None:
    prog = [sys.executable, str(CLEANUP_PY)]
    if args.root:
        prog += ["--root", str(Path(args.root).expanduser().resolve())]

    service, timer = build_units(prog)
    UNIT_DIR.mkdir(parents=True, exist_ok=True)
    (UNIT_DIR / f"{UNIT}.service").write_text(service)
    (UNIT_DIR / f"{UNIT}.timer").write_text(timer)

    sh("systemctl", "--user", "daemon-reload")
    sh("systemctl", "--user", "enable", "--now", f"{UNIT}.timer")
    print(f"✓ 已安裝並啟用 {UNIT}.timer（每小時 :15 清一次過期分享）")
    print(f"  units：{UNIT_DIR}/{UNIT}.{{service,timer}}")
    user = getpass.getuser()
    linger = sh("loginctl", "show-user", user, "--property=Linger", check=False)
    if "Linger=yes" not in linger.stdout:
        print(f"⚠️  linger 未開，無登入 session 時 timer 不會跑：loginctl enable-linger {user}")


def status() -> None:
    proc = sh("systemctl", "--user", "list-timers", f"{UNIT}.timer", "--no-pager", check=False)
    print(proc.stdout.strip() or f"✗ 未安裝（{UNIT}.timer）；先跑 install")
    last = sh("systemctl", "--user", "status", f"{UNIT}.service", "--no-pager", "-n", "5", check=False)
    print(last.stdout.strip())


def run_now() -> None:
    sh("systemctl", "--user", "start", f"{UNIT}.service")
    print(f"✓ 已觸發；結果看 journalctl --user -u {UNIT}.service")


def uninstall() -> None:
    sh("systemctl", "--user", "disable", "--now", f"{UNIT}.timer", check=False)
    for suffix in (".service", ".timer"):
        (UNIT_DIR / f"{UNIT}{suffix}").unlink(missing_ok=True)
    sh("systemctl", "--user", "daemon-reload", check=False)
    print(f"✓ 已停用並移除 {UNIT}.service / .timer")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    p_install = sub.add_parser("install")
    p_install.add_argument("--root", default=None)
    sub.add_parser("status")
    sub.add_parser("run-now")
    sub.add_parser("uninstall")
    args = ap.parse_args()

    if args.cmd == "install":
        install(args)
    elif args.cmd == "status":
        status()
    elif args.cmd == "run-now":
        run_now()
    elif args.cmd == "uninstall":
        uninstall()


if __name__ == "__main__":
    main()
