---
name: hermes-gateway-doctor-py
description: Generalized self-healing triage for the hermes-gateway systemd user service. Use on ANY vague WeChat/微信 bot complaint - 沒收到, 沒反應, 已讀不回, 等很久沒回, 沒回應, image/file sends fail (CDN upload HTTP 500) - or when asked to 重啟 gateway / check gateway 健康狀態. scripts/doctor.py classifies the journal against a known-error library and prints ONE verdict - session expiry needs a user QR re-scan (restart useless); hang, send failures (text too), and unknown errors get a self-restart-safe restart via detached systemd-run (the agent runs INSIDE hermes-gateway.service). Poll errors of ANY flavor (getupdates 524/554, cannot-connect, reset) are NOT a health signal - calibrated on production journal. Restarts are rate-limited (>=3/hr escalates); never uses `hermes gateway restart`.
compatibility: Linux + systemd user services (headless Ubuntu hermes-agent host). Python 3 stdlib only. diagnose needs journalctl; restart needs systemd-run + user D-Bus (XDG_RUNTIME_DIR set).
metadata:
  built-for: "generalized self-healing of the hermes WeChat gateway (v2 2026-07-23; calibrated on 72h production journal; grew out of the 2026-07-22 CDN-500 incident playbook)"
  origin: "Claude Code"
  variant: "python-orchestrated (doctor.py: diagnose / restart / verify / auto + selfcheck timer)"
---

# Hermes Gateway Doctor（微信 bot 泛用自癒）

**照 verdict 欄位行動**：stdout 走 pipe 時自動輸出 JSON——讀 `verdict`／`next`／
`suggested_reply`／`evidence` 分流，別自己 grep log 下判斷。判斷順序、護欄、
禁令全在 doctor.py（46 tests＋10 突變防護釘住）；你只做三件柔性動作：

1. **重啟前先試文字回覆**（句子在 `suggested_reply` 欄位，別自己編）。
2. **QR 重掃永不代跑**（互動式＋含 secret）。
3. **升級路由給機主**、安撫句給抱怨的訪客（`next` 欄位會標明 OPERATOR）。

```bash
python3 scripts/doctor.py diagnose             # 另有 restart / verify；exit code 見 --help
python3 scripts/install_selfcheck.py install   # 每 15 分鐘 auto 自檢 timer；status / run-now / uninstall
```

未知錯誤入庫（`next` 會指示時機）：pattern＋對應測試一起加進 doctor.py，
`python3 -m pytest tests/ -q` 全綠才算入庫。
