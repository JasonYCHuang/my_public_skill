# gdrive-backup-py

每 6 小時（00:45、06:45、12:45、18:45 本機時間）把 `~/mein-agent-storage/` 經
rclone 備份到 Google Drive。為 headless Ubuntu agent 主機（hermes）設計，
排程用 systemd user timer；Python 3 標準庫 + rclone，無其他依賴。

## 備份策略：鏡像＋每日快照

```
gdrive:Backups/mein-agent-storage/
  current/                  # 最新鏡像（rclone sync）
  snapshots/20260722.tar.gz # 每日第一次備份留一份，保留 14 天
  backup-report.json        # 每次執行的證據（本機 ~/.local/state/... 也有一份）
```

- **鏡像**讓 Drive 上永遠有一份最新版，空間 ≈ 來源大小。
- **每日快照**保護誤刪：來源刪掉的檔案下一次鏡像就消失，但 14 天內的快照還在。

與 `icloud-backup-py`（macOS→iCloud，00:30 系列）同一套策略，錯開 15 分鐘避免
兩邊同時打包同一個來源。

## 安裝

```bash
rclone config                                  # 一次性：name=gdrive, storage=drive, scope=drive.file
python3 scripts/install_systemd.py install     # systemd user timer
python3 scripts/install_systemd.py run-now && python3 scripts/install_systemd.py status
loginctl enable-linger $USER                   # 無人值守必開，否則沒登入時 timer 不跑
```

headless OAuth：`rclone config` 的 auto config 答 n，到有瀏覽器的機器跑
`rclone authorize "drive"` 貼回 token。時區：雲端機常是 UTC，
`timedatectl set-timezone Asia/Taipei` 後再裝。

## 測試

```bash
pytest tests/ -q    # 全走 tmp 目錄＋假 rclone（tests/fake_rclone.py），不需網路
```

## 還原

```bash
# 最新版
rclone copy gdrive:Backups/mein-agent-storage/current ~/mein-agent-storage/
# 回到某天（解到暫存區挑檔案，別直接覆蓋）
rclone copyto gdrive:Backups/mein-agent-storage/snapshots/YYYYMMDD.tar.gz /tmp/restore.tar.gz
tar -xzf /tmp/restore.tar.gz -C /tmp/restore/
```

## 檔案

| 檔案 | 用途 |
|---|---|
| `scripts/backup.py` | 單次備份：rclone sync 鏡像 + 每日快照上傳 + 遠端修剪 + 報告 |
| `scripts/install_systemd.py` | systemd user timer install / status / run-now / uninstall |
| `tests/test_backup.py` | 自動測試（鏡像、刪除傳播、快照冪等、修剪、remote 未設定、鎖、unit 內容） |
| `tests/fake_rclone.py` | 測試用假 rclone：remote 當本機路徑，行為對齊真 rclone |
