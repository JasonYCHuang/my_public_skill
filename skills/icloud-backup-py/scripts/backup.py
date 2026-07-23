#!/usr/bin/env python3
"""icloud-backup：把 SOURCE 鏡像到 iCloud Drive（macOS 預設；其他平台用 --dest 指定），並每日保留一份 tar.gz 快照。

流程（全剛性，任一步失敗即非零退出）：
  1. 檢查 source 存在；dest 若在 iCloud Drive 底下，先確認 iCloud Drive 已啟用
  2. 取鎖（dest/.lock 目錄，mkdir 原子性；mtime 超過 2 小時視為 stale 自動清除）
  3. rsync -a --delete source/ → dest/current/   （鏡像最新版）
  4. 當日尚無快照 → 打包 current/ → dest/snapshots/YYYYMMDD.tar.gz（tmp+rename 原子寫）
  5. 修剪超過 --keep-days 的舊快照
  6. （選配）--rclone-remote：把 current/ 與 snapshots/ rclone sync 上遠端——
     Linux 上通往真 iCloud 之路（rclone ≥1.68 的 iclouddrive backend，見 SKILL.md）；
     快照修剪經 sync 自動傳播到遠端
  7. 寫 dest/backup-report.json 並印出摘要（上傳成功時 copyto 遠端一份）

rsync 退出碼 0 視為成功、24（來源檔在傳輸中消失）視為警告但成功，其餘失敗。
rclone 上傳失敗：report 記 ok:false 並以非零退出（systemd 看得到），本地備份仍完整。
測試時 --rclone-remote 可給本機路徑（不含 ":"，跳過 remote 檢查）、--rclone 可指向假 rclone。
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

ICLOUD_ROOT = Path.home() / "Library/Mobile Documents/com~apple~CloudDocs"
DEFAULT_SOURCE = Path.home() / "mein-agent-storage"
DEFAULT_DEST = ICLOUD_ROOT / "Backups/mein-agent-storage"
LOCK_STALE_SECONDS = 2 * 60 * 60


def die(msg: str) -> "None":
    print(f"✗ {msg}", file=sys.stderr)
    sys.exit(1)


def acquire_lock(dest: Path) -> Path:
    lock = dest / ".lock"
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


def run_rsync(source: Path, current: Path) -> int:
    current.mkdir(parents=True, exist_ok=True)
    cmd = [
        "rsync", "-a", "--delete",
        "--exclude", ".DS_Store",
        "--exclude", ".lock",
        str(source) + "/",
        str(current) + "/",
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode not in (0, 24):
        print(proc.stderr, file=sys.stderr)
        die(f"rsync 失敗（exit {proc.returncode}）")
    return proc.returncode


def ensure_daily_snapshot(current: Path, snapshots: Path, today: str) -> tuple[str, Path]:
    """回傳 ('created'|'exists', 快照路徑)。原子寫：先寫 .tmp 再 rename。"""
    snapshots.mkdir(parents=True, exist_ok=True)
    snap = snapshots / f"{today}.tar.gz"
    if snap.exists():
        return "exists", snap
    tmp = snapshots / f".{today}.tar.gz.tmp"
    try:
        with tarfile.open(tmp, "w:gz") as tar:
            tar.add(current, arcname=current.parent.name)
        os.replace(tmp, snap)
    finally:
        tmp.unlink(missing_ok=True)
    return "created", snap


def prune_snapshots(snapshots: Path, today: str, keep_days: int) -> list[str]:
    cutoff = datetime.datetime.strptime(today, "%Y%m%d").date() - datetime.timedelta(days=keep_days)
    pruned = []
    for f in sorted(snapshots.glob("*.tar.gz")):
        try:
            d = datetime.datetime.strptime(f.name[:8], "%Y%m%d").date()
        except ValueError:
            continue  # 非本工具命名的檔案不動
        if d < cutoff:
            f.unlink()
            pruned.append(f.name)
    return pruned


def rclone(bin_: str, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run([bin_, *args], capture_output=True, text=True)


def check_remote_configured(bin_: str, remote: str) -> None:
    """remote 含 ":" 時確認 rclone 已設定；純本機路徑（測試）跳過。"""
    if ":" not in remote:
        return
    name = remote.split(":", 1)[0] + ":"
    proc = rclone(bin_, "listremotes")
    if proc.returncode != 0:
        die(f"rclone 執行失敗：{proc.stderr.strip()}；未安裝的話 https://rclone.org/install/")
    if name not in proc.stdout.split():
        die(f"rclone remote「{name}」未設定；跑 rclone config 建立"
            f"（iCloud 的 iclouddrive backend 設定與 ADP 限制見 SKILL.md）")


def upload_to_remote(bin_: str, dest: Path, remote: str) -> dict[str, int]:
    """current/ 與 snapshots/ sync 上遠端；回傳各自的 exit code。
    sync 是鏡像——本地修剪掉的舊快照，遠端會跟著刪。"""
    results = {}
    for sub in ("current", "snapshots"):
        proc = rclone(bin_, "sync", str(dest / sub), f"{remote}/{sub}",
                      "--exclude", ".DS_Store")
        results[sub] = proc.returncode
        if proc.returncode != 0:
            print(proc.stderr, file=sys.stderr)
    return results


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    ap.add_argument("--dest", type=Path, default=None,
                    help="macOS 預設 iCloud Drive；其他平台（如 Ubuntu 上的 hermes agent）必填")
    ap.add_argument("--keep-days", type=int, default=14)
    ap.add_argument("--rclone-remote", default=None,
                    help="再 rclone sync 一份到遠端（如 icloud:Backups/mein-agent-storage；"
                         "Linux 通往真 iCloud 之路，設定見 SKILL.md）")
    ap.add_argument("--rclone", default="rclone", help=argparse.SUPPRESS)  # 測試用：假 rclone
    ap.add_argument("--today", default=None, help=argparse.SUPPRESS)  # 測試用：覆寫日期 YYYYMMDD
    args = ap.parse_args()

    started = datetime.datetime.now().astimezone()
    today = args.today or started.strftime("%Y%m%d")

    if args.dest is None:
        if sys.platform != "darwin":
            die("本平台沒有 iCloud Drive 預設路徑，請用 --dest 指定目的地（本機路徑或掛載點）")
        args.dest = DEFAULT_DEST

    if not args.source.is_dir():
        die(f"來源不存在：{args.source}")
    if ICLOUD_ROOT in args.dest.parents and not ICLOUD_ROOT.is_dir():
        die(f"找不到 iCloud Drive（{ICLOUD_ROOT}）；請先在系統設定啟用 iCloud Drive")
    if args.rclone_remote:
        check_remote_configured(args.rclone, args.rclone_remote)
    args.dest.mkdir(parents=True, exist_ok=True)

    lock = acquire_lock(args.dest)
    try:
        rsync_rc = run_rsync(args.source, args.dest / "current")
        snap_status, snap = ensure_daily_snapshot(args.dest / "current", args.dest / "snapshots", today)
        pruned = prune_snapshots(args.dest / "snapshots", today, args.keep_days)
        upload = (upload_to_remote(args.rclone, args.dest, args.rclone_remote)
                  if args.rclone_remote else None)
    finally:
        shutil.rmtree(lock, ignore_errors=True)

    upload_ok = upload is None or all(rc == 0 for rc in upload.values())
    finished = datetime.datetime.now().astimezone()
    report = {
        "ok": upload_ok,
        "started_at": started.isoformat(timespec="seconds"),
        "finished_at": finished.isoformat(timespec="seconds"),
        "source": str(args.source),
        "dest": str(args.dest),
        "rsync_exit": rsync_rc,
        "snapshot": {"status": snap_status, "file": snap.name},
        "pruned": pruned,
        "keep_days": args.keep_days,
    }
    if upload is not None:
        report["rclone"] = {"remote": args.rclone_remote, "sync_exit": upload}
    report_path = args.dest / "backup-report.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2))

    warn = "（rsync 24：部分來源檔傳輸中消失）" if rsync_rc == 24 else ""
    print(f"✓ 鏡像完成 → {args.dest / 'current'}{warn}")
    print(f"✓ 快照 {snap.name}：{'新建' if snap_status == 'created' else '今日已有，略過'}"
          + (f"；修剪 {len(pruned)} 份舊快照" if pruned else ""))
    if upload is not None:
        if not upload_ok:
            die(f"rclone 上傳失敗（{upload}）——本地備份完整，遠端未同步；"
                f"session 過期的話跑 rclone config reconnect（見 SKILL.md）")
        rclone(args.rclone, "copyto", str(report_path),
               f"{args.rclone_remote}/backup-report.json")  # 盡力而為，不影響結果
        print(f"✓ 已同步到 {args.rclone_remote}（current + snapshots + report）")


if __name__ == "__main__":
    main()
