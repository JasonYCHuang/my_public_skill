---
name: icloud-backup-py
description: Back up a local folder (default ~/mein-agent-storage) to Apple iCloud Drive on a fixed schedule - every 6 hours at 00:30/06:30/12:30/18:30 local time via a macOS launchd LaunchAgent, or a systemd user timer on Linux, where --dest is a local staging path and --rclone-remote pushes it to real iCloud via rclone's iclouddrive backend (needs ADP off; session re-auth every 1-2 months). Strategy is mirror + daily snapshot - scripts/backup.py rsync-mirrors the latest state into iCloud (current/), keeps one tar.gz snapshot per day (snapshots/YYYYMMDD.tar.gz, pruned after 14 days), and writes a backup-report.json proving what happened; scripts/check.py turns health checking into ONE verdict (OK/STALE/AUTH_EXPIRED/... with a remedy) instead of eyeballing reports and journals. Use whenever the user asks to 備份 mein-agent-storage, set up/check/change the iCloud 備份排程, 檢查備份有沒有在跑, or 還原 (restore) files from a backup.
compatibility: macOS (launchd + iCloud Drive, the default) and Linux (systemd user timer; no iCloud client exists on Linux - either --dest to a plain local path/mount, or --dest staging + --rclone-remote with an rclone >= 1.68 iclouddrive remote for real iCloud). Python 3 stdlib + system rsync; rclone only for the Linux iCloud leg.
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

## Setup on Linux（如 Ubuntu 上的 hermes agent）

Linux 沒有 iCloud 客戶端，`--dest` **必填**（本機路徑或掛載點；backup.py 不帶
`--dest` 會以 ✗ 拒跑，不會默默寫錯地方）。要讓備份**真正落在 iCloud**，
再加 `--rclone-remote`——本地 mirror+snapshot 完成後 rclone sync 上
iCloud（快照修剪自動傳播；上傳失敗 report 記 ok:false 並非零退出，本地備份
仍完整）：

```bash
python3 scripts/install_systemd.py install --dest ~/backups/icloud-staging \
    --rclone-remote icloud:Backups/mein-agent-storage
python3 scripts/install_systemd.py run-now && python3 scripts/install_systemd.py status
```

**rclone iCloud remote 一次性設定**（rclone ≥ 1.68 的 `iclouddrive` backend）：

1. **先關 Apple ID 的「進階資料保護（ADP）」**——開著 rclone 進不去，這是
   Apple 端的硬限制，要使用者自己在 iPhone/Mac 設定裡關。
2. `rclone config` → `n` → name `icloud` → storage `iclouddrive` → 輸入
   Apple ID 與密碼 → 互動輸入 2FA 驗證碼（純文字流程，ssh 可完成）。
3. 驗證與日後的健康檢查都是同一支：
   ```bash
   python3 scripts/check.py --dest ~/backups/icloud-staging \
       --rclone-remote icloud:Backups/mein-agent-storage --json
   ```

**已知維護負擔：session/信任 token 約 1–2 個月過期。** 不用讀 journal 判斷
——`check.py` 會把認證失敗分類成 `AUTH_EXPIRED` 並印出修復指令
（`rclone config reconnect icloud:`，重新 2FA 需要使用者提供驗證碼，**轉達**）。

同樣 00:30/06:30/12:30/18:30 本機時間；`Persistent=true` 讓停機錯過的班次開機
補跑（對應 launchd 語意）。無人值守機器要 `loginctl enable-linger $USER`，
installer 檢查到沒開會印 ⚠️——**轉達給使用者**，這需要他自己執行。
log 用 `journalctl --user -u icloud-backup-mein-agent-storage.service`。

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
3. 本地 `<dest>` 也沒了（主機掛了）、只剩 iCloud：先
   `rclone copy icloud:Backups/mein-agent-storage/snapshots/YYYYMMDD.tar.gz /tmp/restore/`
   （或 `.../current/` 整層），之後同上。

## 驗證備份有沒有在跑

不要用眼睛讀 report 和 log——跑 verdict 機器：

```bash
python3 scripts/check.py [--dest DIR] [--rclone-remote R] --json
```

stdout 第一行（或 `--json` 的 `verdict`）就是結論，每個 verdict 附帶
`remedy` 告訴你下一步（唯一 exit 0 的是 `OK`）：

| verdict | 意義 → 你的動作 |
|---|---|
| `OK` | 正常，回報即可 |
| `NO_REPORT` / `STALE` | 沒跑過／排程停了 → 照 remedy 查 timer 與 linger |
| `BACKUP_FAILED` | 上次失敗 → 轉達 report 內 rclone/rsync 欄位原文 |
| `AUTH_EXPIRED` | iCloud session 過期 → remedy 給了 reconnect 指令，要使用者 2FA |
| `NOT_CONFIGURED` / `REMOTE_ERROR` / `LOCAL_ERROR` | 照 remedy 處理或轉達 |

你的柔性判斷只剩：轉達什麼、問使用者什麼。健康與否由程式判。
