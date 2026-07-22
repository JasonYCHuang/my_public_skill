---
name: gdrive-backup-py
description: Back up a local folder (default ~/mein-agent-storage) to Google Drive via rclone on a fixed schedule - every 6 hours at 00:45/06:45/12:45/18:45 local time via a systemd user timer (built for a headless Ubuntu agent host, e.g. hermes). Strategy is mirror + daily snapshot - scripts/backup.py rclone-syncs the latest state into Drive (current/), keeps one tar.gz snapshot per day (snapshots/YYYYMMDD.tar.gz, pruned after 14 days), and writes a backup-report.json locally and to Drive proving what happened. Use whenever the user asks to 備份 mein-agent-storage 到 Google Drive, set up/check/change the gdrive 備份排程, or 還原 (restore) files from a Drive backup.
compatibility: Linux with systemd (primary; scheduling via systemd user timer). backup.py itself runs anywhere with Python 3 + rclone (manual runs on macOS fine). Requires rclone with a configured Google Drive remote; one-time OAuth needs a browser on some machine (headless flow below). Python 3 stdlib only; no third-party deps.
metadata:
  built-for: "periodic Google Drive backup of ~/mein-agent-storage on a headless Ubuntu agent host (public, path/remote-configurable)"
  origin: "Claude Code"
  variant: "python-orchestrated (backup.py + rclone + systemd installer + backup-report.json)"
---

# Google Drive Backup（mein-agent-storage）

> 排程與備份全是程式，剛性執行；你只做兩件柔性判斷：**還原時選哪個版本**、
> **報錯時轉達使用者裁決**。其餘照指令跑。

- 目的地：rclone remote `gdrive:Backups/mein-agent-storage/`（`--remote` 可改）
  - `current/` —— 最新鏡像（rclone sync，誤刪會跟著消失）
  - `snapshots/YYYYMMDD.tar.gz` —— 每日第一次備份留一份，保留 14 天（誤刪從這救）
  - `backup-report.json` —— 每次執行的證據（本機 `~/.local/state/gdrive-backup-mein-agent-storage/` 也有一份）
- 排程時間為**系統本機時間**。雲端 Ubuntu 常是 UTC——使用者預期 Asia/Taipei，
  install 會印出目前時區，不對就先 `timedatectl set-timezone Asia/Taipei`。
  `Persistent=true`：停機錯過的班次開機後補跑。

## Setup（一次性）

**1. rclone remote**（沒裝 rclone：`curl https://rclone.org/install.sh | sudo bash`）

```bash
rclone config        # n → name: gdrive → storage: drive → scope: drive.file（最小權限）
```

headless 機器（如 hermes）在 auto config 一步答 **n**，然後到任何有瀏覽器的機器跑
`rclone authorize "drive"`，把產出的 token 貼回去。驗證：`rclone lsd gdrive:` 能列目錄。

**2. 排程**

```bash
python3 scripts/install_systemd.py install     # 00:45/06:45/12:45/18:45，印時區與 linger 檢查
python3 scripts/install_systemd.py run-now     # 立刻跑一次驗證
python3 scripts/install_systemd.py status      # timer 是否啟用、上次執行
loginctl enable-linger $USER                   # 無人值守必開；install 檢查到沒開會印 ⚠️
```

改排程：`install --times "0:45,6:45,12:45,18:45"`（重跑 install 即覆蓋，冪等）。
改來源／remote／保留天數：`install --source P --remote R --keep-days N`。移除：`uninstall`。

## 手動備份一次

```bash
python3 scripts/backup.py            # 成功印 ✓ 並更新 backup-report.json（本機＋Drive）
```

失敗時 stderr 有 `✗` 與原因（來源不見、remote 未設定、rclone sync／上傳失敗、鎖被占用）。
**轉達原文給使用者**，不要自行猜測修復；鎖 stale（>2h）會自動清，不用手動處理。
rclone token 失效（Google 撤銷／久未用）會反映成 sync 失敗——這需要使用者重新
`rclone config reconnect gdrive:`，你不能替他做 OAuth。

## 還原

1. 只是要最新版：`rclone copy gdrive:Backups/mein-agent-storage/current ~/mein-agent-storage/`
2. 要救誤刪／回到某天：先列 `rclone lsf gdrive:Backups/mein-agent-storage/snapshots/`，
   **問使用者要哪一天**，再
   `rclone copyto gdrive:.../snapshots/YYYYMMDD.tar.gz /tmp/restore.tar.gz && tar -xzf /tmp/restore.tar.gz -C /tmp/restore/`
   讓使用者挑檔案，不要直接整包覆蓋回去。

## 驗證備份有沒有在跑

看本機 `~/.local/state/gdrive-backup-mein-agent-storage/backup-report.json` 的
`finished_at` 是否在 6 小時內；再看 `journalctl --user -u gdrive-backup-mein-agent-storage.service -n 20`。
兩者其一異常就跑 `status` 取得 timer 狀態回報使用者。
