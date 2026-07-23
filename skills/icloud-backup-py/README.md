# icloud-backup-py

每 6 小時（00:30、06:30、12:30、18:30 本機時間）把 `~/mein-agent-storage/` 備份到
Apple iCloud Drive（macOS）或任意 `--dest`（Linux）。Python 3 標準庫 + 系統 rsync，
零第三方依賴。

## 備份策略：鏡像＋每日快照

```
iCloud Drive/Backups/mein-agent-storage/
  current/                  # 最新鏡像（rsync -a --delete）
  snapshots/20260722.tar.gz # 每日第一次備份留一份，保留 14 天
  backup-report.json        # 每次執行的證據
```

- **鏡像**讓 iCloud 上永遠有一份最新版，空間 ≈ 來源大小。
- **每日快照**保護誤刪：來源刪掉的檔案下一次鏡像就消失，但 14 天內的快照還在。

## 安裝

```bash
python3 scripts/install_launchd.py install   # 寫 ~/Library/LaunchAgents plist + 載入
python3 scripts/install_launchd.py run-now   # 立刻跑一次驗證
python3 scripts/install_launchd.py status    # 檢查狀態
```

用 launchd 而非 cron：Mac 睡眠時錯過的班次，醒來會補跑一次；cron 直接跳過。

### Linux（如 Ubuntu 上的 hermes agent）

Linux 沒有 iCloud 客戶端，`--dest` 必填（本機 staging）；要真正落在 iCloud，
加 `--rclone-remote`（rclone ≥ 1.68 的 `iclouddrive` backend；ADP 須關、
session 約 1–2 個月要 reconnect）：

```bash
python3 scripts/install_systemd.py install --dest ~/backups/icloud-staging \
    --rclone-remote icloud:Backups/mein-agent-storage
loginctl enable-linger $USER   # 無人值守機器必開，否則沒登入時 timer 不跑
```

健康檢查（一個 verdict，不用讀 report/journal）：

```bash
python3 scripts/check.py --dest ~/backups/icloud-staging --rclone-remote icloud:... --json
```

systemd user timer + `Persistent=true`，語意對應 launchd（停機錯過開機補跑）。

## 測試

```bash
pytest tests/ -q    # 全走 tmp 目錄，不碰 iCloud，不需網路
```

## 還原

```bash
# 最新版
rsync -a "$HOME/Library/Mobile Documents/com~apple~CloudDocs/Backups/mein-agent-storage/current/" ~/mein-agent-storage/
# 回到某天（解到暫存區挑檔案，別直接覆蓋）
tar -xzf ".../snapshots/YYYYMMDD.tar.gz" -C /tmp/restore/
```

## 檔案

| 檔案 | 用途 |
|---|---|
| `scripts/backup.py` | 單次備份：鏡像 + 每日快照 + 修剪 + 報告 |
| `scripts/install_launchd.py` | macOS launchd 排程 install / status / run-now / uninstall |
| `scripts/install_systemd.py` | Linux systemd user timer，同一組子指令，`--dest` 必填、`--rclone-remote` 選配 |
| `scripts/check.py` | 健康檢查 verdict 機器（OK/STALE/AUTH_EXPIRED/... + remedy），`--json` 契約 |
| `tests/test_backup.py` | 自動測試（鏡像、刪除傳播、快照冪等、修剪、鎖、rclone 上傳腿、check verdicts、systemd unit 內容） |
| `tests/fake_rclone.py` | 測試用假 rclone（sync/copyto/lsd/listremotes + 故障注入） |
