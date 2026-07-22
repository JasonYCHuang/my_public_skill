#!/usr/bin/env python3
"""安裝／管理 launchd 排程：每 6 小時（00:30、06:30、12:30、18:30 本機時間）跑 backup.py。

    python3 install_launchd.py install [--times 0:30,6:30,12:30,18:30] [--source P] [--dest P] [--keep-days N]
    python3 install_launchd.py status      # 排程是否載入、上次退出碼
    python3 install_launchd.py run-now     # 立刻手動觸發一次
    python3 install_launchd.py uninstall

選 launchd 而非 cron：Mac 睡眠時錯過的排程，醒來會補跑一次；cron 直接跳過。
"""

from __future__ import annotations

import argparse
import os
import plistlib
import subprocess
import sys
from pathlib import Path

LABEL = "local.icloud-backup.mein-agent-storage"
PLIST = Path.home() / f"Library/LaunchAgents/{LABEL}.plist"
LOG = Path.home() / "Library/Logs/icloud-backup-mein-agent-storage.log"
BACKUP_PY = (Path(__file__).parent / "backup.py").resolve()
DOMAIN = f"gui/{os.getuid()}"


def sh(*cmd: str, check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True, check=check)


def parse_times(spec: str) -> list[dict[str, int]]:
    out = []
    for t in spec.split(","):
        h, m = t.strip().split(":")
        out.append({"Hour": int(h), "Minute": int(m)})
    if not out:
        raise ValueError("至少要有一個時間")
    return out


def install(args: argparse.Namespace) -> None:
    prog = [sys.executable, str(BACKUP_PY)]
    if args.source:
        prog += ["--source", str(Path(args.source).expanduser().resolve())]
    if args.dest:
        prog += ["--dest", str(Path(args.dest).expanduser().resolve())]
    if args.keep_days is not None:
        prog += ["--keep-days", str(args.keep_days)]

    plist = {
        "Label": LABEL,
        "ProgramArguments": prog,
        "StartCalendarInterval": parse_times(args.times),
        "RunAtLoad": False,
        "StandardOutPath": str(LOG),
        "StandardErrorPath": str(LOG),
    }
    PLIST.parent.mkdir(parents=True, exist_ok=True)
    with open(PLIST, "wb") as f:
        plistlib.dump(plist, f)

    sh("launchctl", "bootout", f"{DOMAIN}/{LABEL}", check=False)  # 舊版先卸載，冪等
    sh("launchctl", "bootstrap", DOMAIN, str(PLIST))
    print(f"✓ 已安裝並載入 {LABEL}")
    print(f"  排程（本機時間）：{args.times}")
    print(f"  plist：{PLIST}")
    print(f"  log：{LOG}")


def status() -> None:
    proc = sh("launchctl", "print", f"{DOMAIN}/{LABEL}", check=False)
    if proc.returncode != 0:
        print(f"✗ 未載入（{LABEL}）；先跑 install")
        sys.exit(1)
    for line in proc.stdout.splitlines():
        if any(k in line for k in ("state =", "last exit code", "program =", "run interval")):
            print(line.strip())
    report = Path.home() / "Library/Mobile Documents/com~apple~CloudDocs/Backups/mein-agent-storage/backup-report.json"
    if report.exists():
        print(f"上次報告：{report}")
        print(report.read_text())


def run_now() -> None:
    sh("launchctl", "kickstart", f"{DOMAIN}/{LABEL}")
    print(f"✓ 已觸發；結果看 {LOG} 與 backup-report.json")


def uninstall() -> None:
    sh("launchctl", "bootout", f"{DOMAIN}/{LABEL}", check=False)
    PLIST.unlink(missing_ok=True)
    print(f"✓ 已卸載並移除 {PLIST}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    p_install = sub.add_parser("install")
    p_install.add_argument("--times", default="0:30,6:30,12:30,18:30")
    p_install.add_argument("--source", default=None)
    p_install.add_argument("--dest", default=None)
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
