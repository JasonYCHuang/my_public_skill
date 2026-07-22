---
name: hermes-gateway-doctor-py
description: Fix hermes-gateway "WeChat text works but image/file sends fail with CDN upload HTTP 500" via a self-restart-safe gateway restart (the agent runs inside hermes-gateway.service; restart is detached via systemd-run). getupdates HTTP 524/5xx poll noise is NOT a health signal. Use when the WeChat/微信 bot 沒回應／沒收到圖片檔案, logs show `CDN upload HTTP 500`, or asked to 重啟 gateway／check gateway 健康狀態.
compatibility: Linux + systemd user services (headless Ubuntu hermes-agent host). Python 3 stdlib only. diagnose needs journalctl; restart needs systemd-run + user D-Bus (XDG_RUNTIME_DIR set).
metadata:
  built-for: "self-healing the Weixin/iLink CDN-500 image-send failure on a hermes-agent Ubuntu host (2026-07-22 incident playbook)"
  origin: "Claude Code"
  variant: "python-orchestrated (doctor.py: diagnose / restart / verify)"
---

# Hermes Gateway Doctor（微信傳圖 CDN 500 自癒）

**照 `doctor.py` 印出的 `VERDICT:`／`next:` 行動作**，別自己 grep log 下判斷。
你只做兩件柔性判斷：

1. **重啟前先用文字回覆使用者**（文字通道是好的；建議句 `restart` 會印出）。
2. **重掃 QR 交回使用者本人**（互動式＋含 secret，永不代跑；指示在 verdict 裡）。

```bash
python3 scripts/doctor.py diagnose   # exit 0 健康 / 1 建議重啟 / 2 沒在跑 / 3 session 過期 / 4 journal 讀不到
python3 scripts/doctor.py restart    # 脫離式延遲重啟（自我重啟安全）；已排程去重＋1hr≥3 次改回 exit 3 建議升級
python3 scripts/doctor.py verify     # 重啟後驗證；窗口自動從本次啟動時刻起算（不撈重啟前失敗）
```

原理、假因排除、自我重啟陷阱：見 doctor.py docstring／常數／verdict（有測試釘住）。
