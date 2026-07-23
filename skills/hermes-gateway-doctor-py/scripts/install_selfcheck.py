#!/usr/bin/env python3
"""安裝 gateway-doctor 自檢 timer：每 15 分鐘跑 `doctor.py auto`（無人值守自癒）。

    python3 install_selfcheck.py install [--interval-min 15] [--unit hermes-gateway]
    python3 install_selfcheck.py status
    python3 install_selfcheck.py run-now
    python3 install_selfcheck.py uninstall

為什麼需要它：最壞的故障（gateway 死透／hang）會讓微信通道本身失效——用戶的
「沒反應」根本傳不進來，唯一不經過微信的觸發源就是這個 timer。selfcheck 跑在
gateway 的 cgroup 之外，所以 not-running 可以直接 start、restart 不會殺到自己。
auto 的自癒範圍與護欄見 doctor.py cmd_auto docstring（hang 只回報不重啟）。

無人值守機器記得開 linger，否則沒登入 session 時 user timer 不會跑：
    loginctl enable-linger $USER
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

UNIT = "gateway-doctor-selfcheck"
UNIT_DIR = Path.home() / ".config/systemd/user"
DOCTOR_PY = (Path(__file__).parent / "doctor.py").resolve()


def sh(*cmd: str, check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True, check=check)


def build_units(prog: list[str], interval_min: int) -> tuple[str, str]:
    """回傳 (service 內容, timer 內容)。抽成純函式讓 macOS 上也測得到。"""
    service = f"""[Unit]
Description=Unattended selfcheck + safe self-heal for the hermes gateway

[Service]
Type=oneshot
ExecStart={" ".join(prog)}
"""
    timer = f"""[Unit]
Description=Run {UNIT} every {interval_min} minutes

[Timer]
OnCalendar=*:0/{interval_min}
Persistent=false

[Install]
WantedBy=timers.target
"""
    return service, timer


def install(args: argparse.Namespace) -> None:
    if args.interval_min < 5:
        # 自檢比重啟頻率守衛還密就沒有意義，而且會把 journal 洗成自己的噪音
        raise SystemExit("✗ --interval-min 最小 5 分鐘")
    prog = [sys.executable, str(DOCTOR_PY), "--unit", args.unit, "auto"]
    service, timer = build_units(prog, args.interval_min)
    UNIT_DIR.mkdir(parents=True, exist_ok=True)
    (UNIT_DIR / f"{UNIT}.service").write_text(service)
    (UNIT_DIR / f"{UNIT}.timer").write_text(timer)

    sh("systemctl", "--user", "daemon-reload")
    sh("systemctl", "--user", "enable", "--now", f"{UNIT}.timer")
    print(f"✓ 已安裝並啟用 {UNIT}.timer（每 {args.interval_min} 分鐘）")
    print(f"  units：{UNIT_DIR}/{UNIT}.{{service,timer}}")
    print(f"  監看對象：{args.unit}.service；log：journalctl --user -u {UNIT}.service")
    linger = sh("loginctl", "show-user", Path.home().name, "--property=Linger", check=False)
    if "Linger=yes" not in linger.stdout:
        print(f"⚠️  linger 未開，無登入 session 時 timer 不會跑：loginctl enable-linger {Path.home().name}")


def status() -> None:
    proc = sh("systemctl", "--user", "list-timers", f"{UNIT}.timer", "--no-pager", check=False)
    print(proc.stdout.strip() or f"✗ 未安裝（{UNIT}.timer）；先跑 install")
    last = sh("systemctl", "--user", "status", f"{UNIT}.service", "--no-pager", "-n", "10", check=False)
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
    p_install.add_argument("--interval-min", type=int, default=15)
    p_install.add_argument("--unit", default="hermes-gateway")
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
