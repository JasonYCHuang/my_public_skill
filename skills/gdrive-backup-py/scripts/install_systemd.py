#!/usr/bin/env python3
"""Ubuntu（hermes agent）用：systemd user timer，每 6 小時（00:45/06:45/12:45/18:45 本機時間）跑 backup.py。

    python3 install_systemd.py install [--remote gdrive:Backups/mein-agent-storage] \\
        [--times 0:45,6:45,12:45,18:45] [--source P] [--keep-days N]
    python3 install_systemd.py status
    python3 install_systemd.py run-now
    python3 install_systemd.py uninstall

Persistent=true：停機錯過的班次開機後補跑。無人值守機器記得開 linger，
否則沒登入 session 時 user timer 不會跑：
    loginctl enable-linger $USER

排程用「系統本機時間」——雲端 Ubuntu 常是 UTC，install 會印出目前時區，
不是預期的話先 timedatectl set-timezone Asia/Taipei 再裝。
"""

from __future__ import annotations

import argparse
import datetime
import getpass
import subprocess
import sys
from pathlib import Path

UNIT = "gdrive-backup-mein-agent-storage"
UNIT_DIR = Path.home() / ".config/systemd/user"
BACKUP_PY = (Path(__file__).parent / "backup.py").resolve()


def sh(*cmd: str, check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True, check=check)


def parse_times(spec: str) -> list[tuple[int, int]]:
    out = []
    for t in spec.split(","):
        h, m = t.strip().split(":")
        out.append((int(h), int(m)))
    if not out:
        raise ValueError("至少要有一個時間")
    return out


def build_units(prog: list[str], times: list[tuple[int, int]]) -> tuple[str, str]:
    """回傳 (service 內容, timer 內容)。抽成純函式讓沒有 systemd 的機器也測得到。"""
    service = f"""[Unit]
Description=Mirror + daily snapshot backup of mein-agent-storage to Google Drive

[Service]
Type=oneshot
ExecStart={" ".join(prog)}
"""
    calendars = "\n".join(f"OnCalendar=*-*-* {h:02d}:{m:02d}:00" for h, m in times)
    timer = f"""[Unit]
Description=Run {UNIT} every 6 hours

[Timer]
{calendars}
Persistent=true

[Install]
WantedBy=timers.target
"""
    return service, timer


def install(args: argparse.Namespace) -> None:
    prog = [sys.executable, str(BACKUP_PY), "--remote", args.remote]
    if args.source:
        prog += ["--source", str(Path(args.source).expanduser().resolve())]
    if args.keep_days is not None:
        prog += ["--keep-days", str(args.keep_days)]

    service, timer = build_units(prog, parse_times(args.times))
    UNIT_DIR.mkdir(parents=True, exist_ok=True)
    (UNIT_DIR / f"{UNIT}.service").write_text(service)
    (UNIT_DIR / f"{UNIT}.timer").write_text(timer)

    sh("systemctl", "--user", "daemon-reload")
    sh("systemctl", "--user", "enable", "--now", f"{UNIT}.timer")
    tz = datetime.datetime.now().astimezone().tzname()
    print(f"✓ 已安裝並啟用 {UNIT}.timer")
    print(f"  排程（本機時間）：{args.times}；目前系統時區：{tz}（Persistent=true，停機錯過會補跑）")
    print(f"  units：{UNIT_DIR}/{UNIT}.{{service,timer}}")
    print(f"  remote：{args.remote}")
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
    print(f"✓ 已觸發；結果看 journalctl --user -u {UNIT}.service 與 state dir 的 backup-report.json")


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
    p_install.add_argument("--remote", default="gdrive:Backups/mein-agent-storage")
    p_install.add_argument("--times", default="0:45,6:45,12:45,18:45")
    p_install.add_argument("--source", default=None)
    p_install.add_argument("--keep-days", type=int, default=None)
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
