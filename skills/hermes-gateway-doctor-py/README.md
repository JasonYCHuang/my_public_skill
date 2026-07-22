# hermes-gateway-doctor-py

修復 hermes-gateway「微信文字正常、傳圖全 `CDN upload HTTP 500`」故障
（2026-07-22 playbook）。知識全在 `scripts/doctor.py`（Python 3 stdlib）：
根因、自我重啟陷阱（agent 跑在 service 內 → `systemd-run` 脫離式重啟）、
524 poll 噪音過濾、升級路徑——以常數／regex／verdict 輸出實作，測試釘住。
LLM 只負責：重啟前先文字回覆使用者、把重掃 QR 交回使用者本人。

```bash
python3 scripts/doctor.py diagnose   # exit 0 健康 / 1 建議重啟 / 2 沒在跑 / 3 session 過期 / 4 journal 讀不到
python3 scripts/doctor.py restart    # 脫離式延遲重啟；pending 去重＋1hr 頻率守衛（state file 跨 agent 死亡記憶）
python3 scripts/doctor.py verify     # 重啟後驗證；窗口從本次啟動時刻起算
```

需 systemd user service 環境（Ubuntu hermes-agent 主機）。

測試：`python3 -m pytest tests/ -q`（21 tests：單元／回歸／輸出契約）
突變測試：`python3 tests/mutation_test.py`——故意改壞 7 條防護，套件必須變紅
（exit 0 = 全殺死；曾抓到 journal_lines 只測消費端的裝飾性覆蓋）。
