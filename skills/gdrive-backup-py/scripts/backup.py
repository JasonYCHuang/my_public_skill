#!/usr/bin/env python3
"""gdrive-backup：透過 rclone 把 SOURCE 鏡像到 Google Drive，並每日保留一份 tar.gz 快照。

流程（全剛性，任一步失敗即非零退出）：
  1. 檢查 source 存在；remote 含 ":" 時確認 rclone 已設定該 remote
  2. 取鎖（state dir 下 .lock 目錄；mtime 超過 2 小時視為 stale 自動清除）
  3. rclone sync source → remote/current   （鏡像最新版，遠端多出的檔會刪）
  4. 當日尚無快照 → 本機打包 tar.gz → rclone copyto remote/snapshots/YYYYMMDD.tar.gz
  5. 依 --keep-days 修剪遠端舊快照（依檔名日期，非 mtime）
  6. 寫 backup-report.json（本機 state dir 一份、rclone copyto 遠端一份）

rclone remote 一次性設定（headless 見 SKILL.md）：rclone config → storage=drive。
測試時 --remote 可給本機路徑（不含 ":"，跳過 remote 檢查）、--rclone 可指向假 rclone。
"""

from __future__ import annotations

import argparse
import datetime
import json
import os
import shutil
import subprocess
import sys
import tarfile
from pathlib import Path

DEFAULT_SOURCE = Path.home() / "mein-agent-storage"
DEFAULT_REMOTE = "gdrive:Backups/mein-agent-storage"
DEFAULT_STATE = Path.home() / ".local/state/gdrive-backup-mein-agent-storage"
LOCK_STALE_SECONDS = 2 * 60 * 60


def die(msg: str) -> "None":
    print(f"✗ {msg}", file=sys.stderr)
    sys.exit(1)


def acquire_lock(state: Path) -> Path:
    lock = state / ".lock"
    try:
        lock.mkdir()
    except FileExistsError:
        age = datetime.datetime.now().timestamp() - lock.stat().st_mtime
        if age > LOCK_STALE_SECONDS:
            shutil.rmtree(lock)
            lock.mkdir()
        else:
            die(f"另一份備份正在執行（{lock} 存在，{int(age)}s 前建立）；若確定沒有，刪掉它再重試")
    (lock / "pid").write_text(str(os.getpid()))
    return lock


def rclone(bin_: str, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run([bin_, *args], capture_output=True, text=True)


def check_remote_configured(bin_: str, remote: str) -> None:
    name = remote.split(":", 1)[0] + ":"
    proc = rclone(bin_, "listremotes")
    if proc.returncode != 0:
        die(f"rclone 執行失敗：{proc.stderr.strip()}；未安裝的話 https://rclone.org/install/")
    if name not in proc.stdout.split():
        die(f"rclone remote「{name}」未設定；跑 rclone config 建立（headless 認證見 SKILL.md）")


def sync_mirror(bin_: str, source: Path, remote: str) -> None:
    proc = rclone(bin_, "sync", str(source), f"{remote}/current", "--exclude", ".DS_Store")
    if proc.returncode != 0:
        print(proc.stderr, file=sys.stderr)
        die(f"rclone sync 失敗（exit {proc.returncode}）")


def list_snapshots(bin_: str, remote: str) -> list[str]:
    proc = rclone(bin_, "lsf", f"{remote}/snapshots")
    if proc.returncode != 0:  # 目錄尚不存在（第一次跑）
        return []
    return [line.strip().rstrip("/") for line in proc.stdout.splitlines() if line.strip()]


def ensure_daily_snapshot(bin_: str, source: Path, remote: str, state: Path,
                          today: str, existing: list[str]) -> str:
    """回傳 'created' 或 'exists'。tar 打包本機 source，經 copyto 原子上傳。"""
    name = f"{today}.tar.gz"
    if name in existing:
        return "exists"
    tmp = state / f".{name}.tmp"
    try:
        with tarfile.open(tmp, "w:gz") as tar:
            tar.add(source, arcname=source.name)
        proc = rclone(bin_, "copyto", str(tmp), f"{remote}/snapshots/{name}")
        if proc.returncode != 0:
            print(proc.stderr, file=sys.stderr)
            die(f"快照上傳失敗（exit {proc.returncode}）")
    finally:
        tmp.unlink(missing_ok=True)
    return "created"


def prune_snapshots(bin_: str, remote: str, today: str, keep_days: int,
                    existing: list[str]) -> list[str]:
    cutoff = datetime.datetime.strptime(today, "%Y%m%d").date() - datetime.timedelta(days=keep_days)
    pruned = []
    for name in sorted(existing):
        try:
            d = datetime.datetime.strptime(name[:8], "%Y%m%d").date()
        except ValueError:
            continue  # 非本工具命名的檔案不動
        if d < cutoff:
            proc = rclone(bin_, "deletefile", f"{remote}/snapshots/{name}")
            if proc.returncode == 0:
                pruned.append(name)
            else:
                print(f"⚠️  修剪 {name} 失敗：{proc.stderr.strip()}", file=sys.stderr)
    return pruned


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    ap.add_argument("--remote", default=DEFAULT_REMOTE,
                    help='rclone 目的地，如 "gdrive:Backups/mein-agent-storage"')
    ap.add_argument("--keep-days", type=int, default=14)
    ap.add_argument("--rclone", default="rclone", help=argparse.SUPPRESS)  # 測試用：假 rclone
    ap.add_argument("--state-dir", type=Path, default=DEFAULT_STATE, help=argparse.SUPPRESS)
    ap.add_argument("--today", default=None, help=argparse.SUPPRESS)  # 測試用：覆寫日期 YYYYMMDD
    args = ap.parse_args()

    started = datetime.datetime.now().astimezone()
    today = args.today or started.strftime("%Y%m%d")
    remote = args.remote.rstrip("/")

    if not args.source.is_dir():
        die(f"來源不存在：{args.source}")
    if ":" in remote:
        check_remote_configured(args.rclone, remote)
    args.state_dir.mkdir(parents=True, exist_ok=True)

    lock = acquire_lock(args.state_dir)
    try:
        sync_mirror(args.rclone, args.source, remote)
        existing = list_snapshots(args.rclone, remote)
        snap_status = ensure_daily_snapshot(args.rclone, args.source, remote,
                                            args.state_dir, today, existing)
        pruned = prune_snapshots(args.rclone, remote, today, args.keep_days, existing)
    finally:
        shutil.rmtree(lock, ignore_errors=True)

    finished = datetime.datetime.now().astimezone()
    report = {
        "ok": True,
        "started_at": started.isoformat(timespec="seconds"),
        "finished_at": finished.isoformat(timespec="seconds"),
        "source": str(args.source),
        "remote": remote,
        "snapshot": {"status": snap_status, "file": f"{today}.tar.gz"},
        "pruned": pruned,
        "keep_days": args.keep_days,
    }
    report_path = args.state_dir / "backup-report.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2))
    up = rclone(args.rclone, "copyto", str(report_path), f"{remote}/backup-report.json")
    if up.returncode != 0:  # 資料已備妥，報告上傳失敗只警告不判死
        print(f"⚠️  backup-report.json 上傳失敗：{up.stderr.strip()}", file=sys.stderr)

    print(f"✓ 鏡像完成 → {remote}/current")
    print(f"✓ 快照 {today}.tar.gz：{'新建' if snap_status == 'created' else '今日已有，略過'}"
          + (f"；修剪 {len(pruned)} 份舊快照" if pruned else ""))


if __name__ == "__main__":
    main()
