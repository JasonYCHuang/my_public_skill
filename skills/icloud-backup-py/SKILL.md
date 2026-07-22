---
name: icloud-backup-py
description: Back up a local folder (default ~/mein-agent-storage) to Apple iCloud Drive on a fixed schedule - every 6 hours at 00:30/06:30/12:30/18:30 local time via a macOS launchd LaunchAgent. Strategy is mirror + daily snapshot - scripts/backup.py rsync-mirrors the latest state into iCloud (current/), keeps one tar.gz snapshot per day (snapshots/YYYYMMDD.tar.gz, pruned after 14 days), and writes a backup-report.json proving what happened. Use whenever the user asks to 備份 mein-agent-storage, set up/check/change the iCloud 備份排程, or 還原 (restore) files from a backup.
compatibility: macOS only (launchd + iCloud Drive). Python 3 stdlib + system rsync; no third-party deps. Scheduling via ~/Library/LaunchAgents; needs iCloud Drive enabled in System Settings.
metadata:
  built-for: "periodic iCloud backup of ~/mein-agent-storage (public, path-configurable)"
  origin: "Claude Code"
  variant: "python-orchestrated (backup.py + launchd installer + backup-report.json)"
---

# iCloud Backup（mein-agent-storage）

> 排程與備份全是程式，剛性執行；你只做兩件柔性判斷：**還原時選哪個版本**、
> **報錯時轉達使用者裁決**。其餘照指令跑。

- 目的地：`~/Library/Mobile Documents/com~apple~CloudDocs/Backups/mein-agent-storage/`
  - `current/` —— 最新鏡像（rsync -a --delete，誤刪會跟著消失）
  - `snapshots/YYYYMMDD.tar.gz` —— 每日第一次備份留一份，保留 14 天（誤刪從這救）
  - `backup-report.json` —— 每次執行的證據（時間、rsync 退出碼、快照、修剪清單）
- 排程時間為 **Mac 本機時間**（使用者環境即 Asia/Taipei）。睡眠中錯過的班次，
  醒來 launchd 會補跑一次；關機錯過則跳過。

## Setup（一次性）

```bash
python3 scripts/install_launchd.py install        # 寫 plist + 載入，00:30/06:30/12:30/18:30
python3 scripts/install_launchd.py run-now        # 立刻跑一次驗證
python3 scripts/install_launchd.py status         # 是否載入、上次退出碼、上次報告
```

改排程：`install --times "0:30,6:30,12:30,18:30"`（重跑 install 即覆蓋，冪等）。
改來源／目的地／保留天數：`install --source P --dest P --keep-days N`。
移除：`uninstall`。

## 手動備份一次

```bash
python3 scripts/backup.py            # 用預設路徑；成功會印 ✓ 並更新 backup-report.json
```

失敗時 stderr 有 `✗` 與原因（來源不見、iCloud Drive 未啟用、rsync 錯誤、鎖被占用）。
**轉達原文給使用者**，不要自行猜測修復；鎖 stale（>2h）會自動清，不用手動處理。

## 還原

1. 只是要最新版：`rsync -a "<dest>/current/" ~/mein-agent-storage/`
2. 要救誤刪／回到某天：先列 `ls <dest>/snapshots/`，**問使用者要哪一天**，再
   `tar -xzf <dest>/snapshots/YYYYMMDD.tar.gz -C /tmp/restore/` 讓使用者挑檔案，
   不要直接整包覆蓋回去。

## 驗證備份有沒有在跑

看 `backup-report.json` 的 `finished_at` 是否在 6 小時內；再看
`~/Library/Logs/icloud-backup-mein-agent-storage.log` 尾端。兩者其一異常就跑
`status` 取得 launchd 狀態回報使用者。
