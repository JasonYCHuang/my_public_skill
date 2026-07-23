---
name: hermes-gateway-doctor-py
description: Generalized self-healing triage for the hermes-gateway systemd user service. Use on ANY vague WeChat/微信 bot complaint - 沒收到, 沒反應, 已讀不回, 等很久沒回, 沒回應, image/file sends fail (CDN upload HTTP 500) - or when asked to 重啟 gateway / check gateway 健康狀態. scripts/doctor.py classifies the journal against a known-error library and prints ONE verdict - session expiry needs a user QR re-scan (restart useless); hang, send failures (text too), broken inbound, and unknown errors get a self-restart-safe restart via detached systemd-run (the agent runs INSIDE hermes-gateway.service). getupdates HTTP 524/5xx poll noise is NOT a health signal. Restarts are rate-limited (>=3/hr escalates); never uses `hermes gateway restart`.
compatibility: Linux + systemd user services (headless Ubuntu hermes-agent host). Python 3 stdlib only. diagnose needs journalctl; restart needs systemd-run + user D-Bus (XDG_RUNTIME_DIR set).
metadata:
  built-for: "generalized self-healing of the hermes WeChat gateway (v2 2026-07-23; grew out of the 2026-07-22 CDN-500 incident playbook)"
  origin: "Claude Code"
  variant: "python-orchestrated (doctor.py: diagnose / restart / verify)"
---

# Hermes Gateway Doctor（微信 bot 泛用自癒）

**照 `doctor.py` 印出的 `VERDICT:`／`next:` 行動作**，別自己 grep log 下判斷。
你只做兩件柔性判斷：

1. **重啟前先試著用文字回覆使用者**（建議句 `restart` 會印出）。
2. **重掃 QR 交回使用者本人**（互動式＋含 secret，永不代跑；指示在 verdict 裡）。

```bash
python3 scripts/doctor.py --json diagnose   # exit 0 健康 / 1 建議重啟（send 失敗、hang、inbound 斷、未知錯誤）/ 2 沒在跑 / 3 session 過期 / 4 journal 讀不到
python3 scripts/doctor.py --json restart    # 脫離式延遲重啟（自我重啟安全）；已排程去重＋1hr≥3 次改回 exit 3 建議升級
python3 scripts/doctor.py --json verify     # 重啟後驗證；窗口自動從本次啟動時刻起算（不撈重啟前失敗）
```

- **一律帶 `--json`**：讀 `verdict`／`next`／`suggested_reply`／`evidence` 欄位行動，
  不要從散文猜（人工除錯才用無 `--json` 的散文模式）。
- **觸發不限傳圖失敗**：沒收到／沒反應／已讀不回／等很久沒回，一律先跑 `diagnose`。
- 重啟一律走 systemctl 路徑（doctor.py 內建）；**永遠不要用 `hermes gateway restart`**
  ——它靠 SIGUSR1 進 asyncio loop，gateway 越壞越叫不動（上游 issue #12438）。
- `verdict: unknown-error-survived` → 升級給使用者，並把該錯誤 pattern 加進 doctor.py
  已知錯誤庫（**每個新錯誤只盲修一次**）。入庫有閘門：pattern＋對應測試一起加，
  `python3 -m pytest tests/ -q` 全綠才算入庫，紅燈不得留在檔案裡。

原理、判斷順序、護欄：見 doctor.py docstring／常數／verdict（有測試釘住）。
