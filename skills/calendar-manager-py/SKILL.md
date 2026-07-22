---
name: calendar-manager-py
description: Manage an executive/team calendar (Google Calendar or iCloud) and publish it as styled month/week HTML/PNG. Python-orchestrated variant of calendar-manager - terse entries are parsed by scripts/parse_entries.py into a validated plan.json that scripts/apply_plan.py executes and reads back from the server; views come from one command (scripts/build.py) that renders, verifies, atomically writes, and records every output in an Artifact Manifest. Use whenever the user gives calendar entries as "時間、地點、事項" to add, asks to (re)generate a 月曆/週曆 HTML/PNG, or mentions 行事曆 for a specific person's schedule (e.g. "OO董行事曆").
compatibility: Agent-agnostic Agent Skills package (agentskills.io format). Backend - iCloud (plain Python/CalDAV in scripts/icloud/) or Google Calendar (agent's own MCP/connector). Python 3 for scripts; Node.js + Chrome only for PNG. Run scripts/doctor.py to check; install steps in README.md.
metadata:
  built-for: "a company chairman's schedule (anonymized in this public package)"
  origin: "Claude Code"
  variant: "python-orchestrated (parse_entries + plan.json + build.py + Artifact Manifest)"
---

# Calendar Manager（Python 編排版）

> **策略保持柔性，執行保持剛性。** LLM 做軟的認知判斷，Python 做硬的執行與
> 驗證，交界處讓 LLM 產生、Python 驗證。

產出與原版 `calendar-manager` 相同；中段（寫入並證明持久化、產檔並證明完好）
全是程式。設計依據與 artifact-id 參考：`references/orchestration.md`。

**你的柔性判斷只有四件事**，其餘都是指令：

1. **解析器點名的缺口** —— 缺時間/地點/事項就**問使用者**，不猜、不沿用鄰近
   事件的值（行事曆主人明確要求）。例外：使用者說過「以後都用 X」則直接套用，
   但換成*不同*值前仍要確認。
2. **轉達 ⚠️ 警告**（跨日 typo、空地點）並取得裁決。
3. **對話式指涉消歧**（「改 7/16 那個」是哪個 uid）—— 見
   `references/event-input-formats.md`。
4. **出貨前人眼看一張 PNG**（Read 工具可渲染）—— 結構檢查看不出裁切/重疊。

## Setup

```bash
python3 scripts/doctor.py [--backend icloud|google] [--png]   # ✗ 附修復指令
```

每個人／團隊一次性：建**專用行事曆**（勿用主行事曆；iCloud 勿用 On My Mac
本機行事曆），確認識別名（`scripts/icloud/list_calendars.py` / Google
calendarId）、時區（`scripts/icloud/_common.py` 的 `TZ`）、預設時長
（`default_duration_minutes`，通常 60）。地點配色在 `assets/loc-class.json`
（資料檔）。答案存進 project memory，別每次重問。

## 寫入：時間、地點、事項 → calendar

```bash
printf '%s\n' "7/15 1930 深圳 印度文A1 chap 04" \
  | python3 scripts/parse_entries.py - --calendar 測試行事曆 --out plan.json
# 補完缺口（判斷 #1、#2）後：
python3 scripts/apply_plan.py apply plan.json     # iCloud：驗證→寫入→逐筆讀回；產 apply-report.json
```

契約：`assets/plan.schema.json`。程式已扛（不用你管）：結束時間預設、全天
展開、重複/typo 偵測、iCloud 全欄位覆寫陷阱（`update` 是 patch 語意，只列
要改的欄位）。

**Google/其他後端**：`apply` 會拒跑。用你的行事曆工具執行 plan 的操作，然後
同樣剛性覆核：

```bash
python3 scripts/apply_plan.py range plan.json     # 該抓回的區間
python3 scripts/apply_plan.py check plan.json events.json
```

已知 Google connector 的 create 可能丟失 `location`——check 會以 ✗ 報出並附
修法（update event 補一次，重抓再 check）。

## 產出：calendar → 月曆/週曆 HTML（＋PNG）

```bash
python3 scripts/build.py --from-icloud "行事曆名" --year 2026 --month 8 --title-prefix 範例
# Google：先 --print-range 拿區間，抓回 events.json 再 build
python3 scripts/build.py --year 2026 --month 8 --print-range
python3 scripts/build.py events.json --year 2026 --month 8 --title-prefix 範例
# 要圖片加 --formats html,png（Chrome 啟動前自動跑 CJK 字型預檢）
```

離開碼非零＝有東西沒過驗證；`--json` 給機器可讀摘要。之後**問 manifest，
不要憑記憶報路徑**：

```bash
python3 scripts/job.py list  <job_dir>    # artifacts + 驗證狀態
python3 scripts/job.py media <job_dir>    # 可直接貼的 MEDIA: 行（月曆在前）
```

Artifact id 固定：`events-json`、`month-html`、`week-1-html`…、`month-png`、
`week-1-png`…。輸出預設在
`~/mein-agent-storage/cal-out/<目標年月>/<時間戳>-<前綴>/`，含 `manifest.json`
與所依據事件的副本。

**傳圖**：判斷 #4 看過後，貼 `job.py media` 的 `MEDIA:` 行。沒渲染出來就先
重試（單獨訊息→縮小→重產），2-3 次後才退回給路徑——**不要第一次失敗就說
傳不了**。

**模板**：產出逐位元組重用 `assets/模板_月曆.html`／`模板_週曆.html` 的
CSS。要改就改模板重跑，**不要手改產出 HTML**。週次：週一起算，第一週＝
週一落在該月的第一週，相鄰兩月共用一個邊界週檔是設計行為。

## Pitfalls

- **離開碼非零／任何 ✗ ＝ 沒完成。**讀 `manifest.json` 的 `verify`／
  `apply-report.json` 的該筆，修好重跑。有 ✗ 不准報成功。
- **CJK 字型預檢失敗（Linux）**：`sudo apt install -y fonts-noto-cjk`，或
  `--allow-missing-font` 硬產（PNG 標記未驗證）。
- **勿混用 sibling `icloud-calendar` skill**（CLI 形狀、憑證格式都不同）。
  使用者或 memory 排除過它，就所有行事曆請求都走本 skill 的 `scripts/`。
- **iCloud 在部分 Linux kernel** 的 CalDAV 連線錯誤：見
  `references/apple-calendar-setup.md` Known quirks。
- **格式選擇等不到回覆（約 60 分鐘）**→ 用安全預設（只產 HTML）並說明。

## Files in this skill

```
calendar-manager-py/
├── SKILL.md
├── README.md               -- 給行事曆主人的白話說明
├── assets/
│   ├── 模板_月曆.html       -- 月曆模板（改這個，別改產出）
│   ├── 模板_週曆.html       -- 週曆模板
│   ├── plan.schema.json    -- 輸入契約：寫入計畫
│   ├── events.schema.json  -- 輸入契約：渲染事件（兩後端共用樞紐）
│   ├── manifest.schema.json      -- 輸出契約：job 產出紀錄
│   ├── apply-report.schema.json  -- 輸出契約：寫入覆核紀錄
│   ├── loc-class.json      -- 地點→顏色（每團隊改資料檔，不改程式）
│   └── hermes-mcp-config.example.yaml
├── references/
│   ├── orchestration.md    -- 為何中段是 Python；manifest/artifact-id 參考
│   ├── apple-calendar-setup.md
│   ├── hermes-setup.md
│   └── event-input-formats.md -- 解析器管什麼、你判斷什麼
├── scripts/
│   ├── doctor.py           -- 環境體檢，✗ 附修復指令
│   ├── parse_entries.py    -- terse 行 → plan.json 草稿＋缺口清單
│   ├── apply_plan.py       -- 執行＋讀回覆核（apply/check/range）
│   ├── validate_plan.py    -- plan 的 normalize + validate
│   ├── validate_events.py  -- events 的進場驗證（build.py 自動跑）
│   ├── build.py            -- events → 驗證過的月/週曆 HTML(+PNG)＋manifest（--print-range）
│   ├── generate_calendar.py -- 渲染器（多地點日、備用配色）
│   ├── verify_output.py    -- 結構檢查：HTML 格線/標題、PNG 檔頭/空白、CJK 預檢
│   ├── job.py              -- job 目錄、原子寫入、Manifest（list/path/verify/media）
│   ├── screenshot.js       -- HTML → PNG（系統 Chrome，退 puppeteer 快取）
│   ├── verify-live-icloud.sh -- 實機驗證：pytest 蓋不到的 CalDAV/Chrome 環節（用測試行事曆）
│   ├── package.json
│   └── icloud/             -- iCloud CalDAV 後端（純 Python）
│       ├── _common.py          -- 共用 helpers；TZ 常數在此
│       ├── list_calendars.py / list_events.py / create_event.py / update_event.py / delete_event.py
│       ├── requirements.txt
│       └── .credentials.example -- 複製成 .credentials 填入（已 gitignore）
└── tests/                  -- pytest；動 scripts/ 或 assets/ 前後都要跑
```

## Editing this skill

先讀 `references/orchestration.md`，改完跑 `python3 -m pytest tests/ -q`；
動到 CalDAV 寫入或 screenshot 相關的，再用測試行事曆跑
`scripts/verify-live-icloud.sh "測試行事曆名"` 實機驗證。
欄位規則在 `assets/plan.schema.json`、地點配色在 `assets/loc-class.json`，
別在別處硬編。`tests/test_docs_consistency.py` 讓文件-程式漂移直接紅燈。
