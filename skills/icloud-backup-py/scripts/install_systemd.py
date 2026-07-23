#!/usr/bin/env python3
"""Linux（如 Ubuntu 上的 hermes agent）用：systemd user timer，每 6 小時跑 backup.py。

    python3 install_systemd.py install --dest /path/to/backup-target \\
        [--times 0:30,6:30,12:30,18:30] [--source P] [--keep-days N]
    python3 install_systemd.py status
    python3 install_systemd.py run-now
    python3 install_systemd.py uninstall

對應 macOS 的 install_launchd.py：Persistent=true 讓停機錯過的班次在開機後補跑
（同 launchd 醒來補跑的語意）。Linux 沒有 iCloud 客戶端，--dest 必填——指向你
要的本機路徑或掛載點（NFS、rclone mount、外接碟皆可）。

無人值守機器記得開 linger，否則沒登入 session 時 user timer 不會跑：
    loginctl enable-linger $USER
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

UNIT = "icloud-backup-mein-agent-storage"
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
    """回傳 (service 內容, timer 內容)。抽成純函式讓 macOS 上也測得到。"""
    service = f"""[Unit]
Description=Mirror + daily snapshot backup of mein-agent-storage

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


def build_prog(args: argparse.Namespace) -> list[str]:
    """組出 ExecStart 指令列。抽成純函式讓沒有 systemd 的機器也測得到。"""
    dest = Path(args.dest).expanduser().resolve()
    prog = [sys.executable, str(BACKUP_PY), "--dest", str(dest)]
    if args.source:
        prog += ["--source", str(Path(args.source).expanduser().resolve())]
    if args.keep_days is not None:
        prog += ["--keep-days", str(args.keep_days)]
    if args.rclone_remote:
        prog += ["--rclone-remote", args.rclone_remote]
    return prog


def install(args: argparse.Namespace) -> None:
    dest = Path(args.dest).expanduser().resolve()
    service, timer = build_units(build_prog(args), parse_times(args.times))
    UNIT_DIR.mkdir(parents=True, exist_ok=True)
    (UNIT_DIR / f"{UNIT}.service").write_text(service)
    (UNIT_DIR / f"{UNIT}.timer").write_text(timer)

    sh("systemctl", "--user", "daemon-reload")
    sh("systemctl", "--user", "enable", "--now", f"{UNIT}.timer")
    print(f"✓ 已安裝並啟用 {UNIT}.timer")
    print(f"  排程（本機時間）：{args.times}（Persistent=true，停機錯過會補跑）")
    print(f"  units：{UNIT_DIR}/{UNIT}.{{service,timer}}")
    print(f"  目的地：{dest}"
          + (f"，並 rclone sync 到 {args.rclone_remote}" if args.rclone_remote else ""))
    linger = sh("loginctl", "show-user", Path.home().name, "--property=Linger", check=False)
    if "Linger=yes" not in linger.stdout:
        print(f"⚠️  linger 未開，無登入 session 時 timer 不會跑：loginctl enable-linger {Path.home().name}")


def status() -> None:
    proc = sh("systemctl", "--user", "list-timers", f"{UNIT}.timer", "--no-pager", check=False)
    print(proc.stdout.strip() or f"✗ 未安裝（{UNIT}.timer）；先跑 install")
    last = sh("systemctl", "--user", "status", f"{UNIT}.service", "--no-pager", "-n", "5", check=False)
    print(last.stdout.strip())


def run_now() -> None:
    sh("systemctl", "--user", "start", f"{UNIT}.service")
    print(f"✓ 已觸發；結果看 journalctl --user -u {UNIT}.service 與 backup-report.json")


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
    p_install.add_argument("--dest", required=True, help="備份目的地（本機路徑或掛載點）")
    p_install.add_argument("--times", default="0:30,6:30,12:30,18:30")
    p_install.add_argument("--source", default=None)
    p_install.add_argument("--keep-days", type=int, default=None)
    p_install.add_argument("--rclone-remote", default=None,
                           help="再 rclone sync 到遠端（如 icloud:Backups/mein-agent-storage）")
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
