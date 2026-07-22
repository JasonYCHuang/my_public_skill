# icloud-backup-py

每 6 小時（00:30、06:30、12:30、18:30 本機時間）把 `~/mein-agent-storage/` 備份到
Apple iCloud Drive。macOS 專用，Python 3 標準庫 + 系統 rsync，零第三方依賴。

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
| `scripts/install_launchd.py` | launchd 排程 install / status / run-now / uninstall |
| `tests/test_backup.py` | 自動測試（鏡像、刪除傳播、快照冪等、修剪、鎖） |
