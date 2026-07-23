# hermes-gateway-doctor-py

hermes-gateway 微信 bot 的**泛用自癒 triage**（v2）。任何模糊抱怨——沒收到／
沒反應／已讀不回／傳圖 `CDN upload HTTP 500`——都先 `diagnose`：把 journal 比對
已知錯誤庫，只印一個 VERDICT。判斷順序：沒在跑→start；session 過期→重掃 QR
（重啟無用）；active 但全靜默→hang→重啟；任何 send 失敗（含文字）→重啟；
沒見過的 ERROR→**只盲修一次**（重啟後還在→升級＋把 pattern 入庫）；
全乾淨→指向 gateway 之外（agent 層／微信端）＋回報 WatchdogSec。

**poll error 不分型態一律噪音**（2026-07-23 以 72h 生產 journal 校準：~2,400 行
poll error、含 782 次 `(3/3)` 耗盡，全發生在流量正常時——任何基於 poll 的
inbound 訊號都是假的，v2 原有的耗盡偵測已據此移除）。

`install_selfcheck.py install` 加裝每 15 分鐘的 `auto` 自檢 timer——補上
「gateway 死透時微信通道本身失效、用戶抱怨傳不進來」的結構性盲區；hang 在
無人值守下只回報不重啟。

護欄：524 poll 噪音永不當訊號、1hr≥3 次重啟改升級、重啟一律 systemctl
（**永不用 `hermes gateway restart`**——SIGUSR1 進 asyncio loop，越壞越叫不動）。
自我重啟陷阱（agent 跑在 service 內）→ `systemd-run` 脫離式延遲重啟。
LLM 只負責：重啟前先試文字回覆使用者、把重掃 QR 交回使用者本人。

```bash
python3 scripts/doctor.py --json diagnose   # exit 0 健康 / 1 建議重啟 / 2 沒在跑 / 3 session 過期 / 4 journal 讀不到
python3 scripts/doctor.py --json restart    # 脫離式延遲重啟；pending 去重＋1hr 頻率守衛（state file 跨 agent 死亡記憶）
python3 scripts/doctor.py --json verify     # 重啟後驗證；窗口從本次啟動時刻起算
```

stdout 走 pipe（agent 的情況）時**自動**輸出結構化 verdict 契約（`verdict`／
`next`／`suggested_reply`／`evidence`／`exit`）——agent 讀欄位行動、想忘 `--json`
都忘不掉；人在終端機上才看到散文（`--prose` 可強制）。升級類 verdict 的 `next`
會標明路由對象是 OPERATOR（機主），不是抱怨的微信訪客。

需 systemd user service 環境（Ubuntu hermes-agent 主機）。

測試：`python3 -m pytest tests/ -q`（46 tests：單元／回歸／輸出契約含 JSON／auto）
突變測試：`python3 tests/mutation_test.py`——故意改壞 10 條防護，套件必須變紅
（exit 0 = 全殺死；曾抓到 journal_lines 只測消費端的裝飾性覆蓋）。
