#!/usr/bin/env python3
"""check.py — 備份健康檢查：印一個 verdict，不用眼睛讀 report/journal。

    python3 scripts/check.py [--dest DIR] [--rclone-remote R] \
        [--max-age-hours 7] [--json]

檢查（全剛性）：
  1. report   dest/backup-report.json 存在、ok:true、finished_at 在 max-age 內
  2. staging  dest/current/ 存在且非空
  3. remote   （有 --rclone-remote 時）remote 已設定、lsd 連得上；
              stderr 出現 401/unauthorized/token/2fa 等字樣 → 判 session 過期

Verdict（stdout 第一行；--json 給機器可讀契約）：
  OK             一切正常（唯一 exit 0）
  NO_REPORT      從沒跑過或 report 不見 → 先 run-now
  BACKUP_FAILED  上次備份 ok:false → 讀 report 的 rclone/rsync 欄位轉達
  STALE          report 過舊 → timer 沒在跑（linger？systemctl --user status）
  AUTH_EXPIRED   iCloud session 過期 → rclone config reconnect <remote>:（要使用者 2FA）
  NOT_CONFIGURED remote 未設定 → rclone config（見 SKILL.md）
  REMOTE_ERROR   連不上遠端（非 auth）→ 轉達 stderr 原文
  LOCAL_ERROR    staging 目錄異常 → 檢查 --dest 路徑
"""

from __future__ import annotations

import argparse
import datetime
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import backup as B  # noqa: E402  共用 DEFAULT_DEST 與 rclone()

AUTH_MARKERS = ("401", "unauthorized", "unauthenticated", "2fa",
                "login", "token", "authentication")

REMEDY = {
    "OK": None,
    "NO_REPORT": "還沒有任何備份報告；先跑 install_*.py run-now 產生第一份",
    "BACKUP_FAILED": "上次備份失敗；讀 backup-report.json 的 rclone/rsync 欄位，轉達原文給使用者",
    "STALE": "report 過舊，排程沒在跑；查 timer 狀態與 linger（loginctl enable-linger）",
    "AUTH_EXPIRED": "iCloud session 過期；跑 rclone config reconnect {remote}: 重新 2FA（需要使用者提供驗證碼）",
    "NOT_CONFIGURED": "rclone remote 未設定；跑 rclone config 建立（見 SKILL.md Linux 段）",
    "REMOTE_ERROR": "遠端連不上（非認證問題）；轉達 stderr 原文給使用者",
    "LOCAL_ERROR": "本地備份目錄異常；確認 --dest 路徑與磁碟空間",
}


def check_report(dest: Path, max_age_hours: float, now: datetime.datetime):
    """回傳 (check dict, verdict or None)。"""
    path = dest / "backup-report.json"
    if not path.is_file():
        return {"name": "report", "ok": False, "detail": f"{path} 不存在"}, "NO_REPORT"
    try:
        report = json.loads(path.read_text())
        finished = datetime.datetime.fromisoformat(report["finished_at"])
    except (json.JSONDecodeError, KeyError, ValueError) as e:
        return {"name": "report", "ok": False, "detail": f"report 壞了：{e}"}, "BACKUP_FAILED"
    age_h = (now - finished).total_seconds() / 3600
    if not report.get("ok"):
        return {"name": "report", "ok": False,
                "detail": f"上次備份 ok:false（{report['finished_at']}）"}, "BACKUP_FAILED"
    if age_h > max_age_hours:
        return {"name": "report", "ok": False,
                "detail": f"report 已 {age_h:.1f}h 未更新（上限 {max_age_hours}h）"}, "STALE"
    return {"name": "report", "ok": True,
            "detail": f"上次成功於 {report['finished_at']}（{age_h:.1f}h 前）"}, None


def check_staging(dest: Path):
    current = dest / "current"
    if not current.is_dir() or not any(current.iterdir()):
        return {"name": "staging", "ok": False,
                "detail": f"{current} 不存在或為空"}, "LOCAL_ERROR"
    return {"name": "staging", "ok": True, "detail": f"{current} 非空"}, None


def check_remote(bin_: str, remote: str):
    name = remote.split(":", 1)[0]
    proc = B.rclone(bin_, "listremotes")
    if proc.returncode != 0 or f"{name}:" not in proc.stdout.split():
        return {"name": "remote", "ok": False,
                "detail": f"remote「{name}:」未設定"}, "NOT_CONFIGURED"
    proc = B.rclone(bin_, "lsd", f"{name}:")
    if proc.returncode != 0:
        err = proc.stderr.strip()
        low = err.lower()
        if any(m in low for m in AUTH_MARKERS):
            return {"name": "remote", "ok": False,
                    "detail": f"認證失敗：{err[:200]}"}, "AUTH_EXPIRED"
        return {"name": "remote", "ok": False,
                "detail": f"lsd 失敗：{err[:200]}"}, "REMOTE_ERROR"
    return {"name": "remote", "ok": True, "detail": f"{name}: 連線正常"}, None


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--dest", type=Path, default=None,
                    help="備份目的地（macOS 預設 iCloud Drive；Linux 必填，同 backup.py）")
    ap.add_argument("--rclone-remote", default=None,
                    help="有設 rclone 上傳腿時一併檢查（如 icloud:Backups/mein-agent-storage）")
    ap.add_argument("--max-age-hours", type=float, default=7.0,
                    help="report 超過幾小時算 STALE（預設 7 = 6h 班距 + 1h 寬限）")
    ap.add_argument("--rclone", default="rclone", help=argparse.SUPPRESS)
    ap.add_argument("--now", default=None, help=argparse.SUPPRESS)  # 測試用 ISO 時間
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    dest = args.dest
    if dest is None:
        if sys.platform != "darwin":
            B.die("本平台沒有預設備份路徑，請帶 --dest（同 backup.py）")
        dest = B.DEFAULT_DEST
    now = (datetime.datetime.fromisoformat(args.now) if args.now
           else datetime.datetime.now().astimezone())

    checks, verdict = [], None
    for c, v in (check_report(dest, args.max_age_hours, now),
                 check_staging(dest),
                 (check_remote(args.rclone, args.rclone_remote)
                  if args.rclone_remote else (None, None))):
        if c:
            checks.append(c)
        verdict = verdict or v  # 第一個失敗的 check 決定 verdict

    verdict = verdict or "OK"
    remedy = REMEDY[verdict]
    if remedy and args.rclone_remote:
        remedy = remedy.format(remote=args.rclone_remote.split(":", 1)[0])

    if args.json:
        print(json.dumps({"verdict": verdict, "ok": verdict == "OK",
                          "checks": checks, "remedy": remedy}, ensure_ascii=False))
    else:
        print(verdict)
        for c in checks:
            print(f"  {'✓' if c['ok'] else '✗'} {c['name']}: {c['detail']}")
        if remedy:
            print(f"  → {remedy}")
    sys.exit(0 if verdict == "OK" else 1)


if __name__ == "__main__":
    main()
