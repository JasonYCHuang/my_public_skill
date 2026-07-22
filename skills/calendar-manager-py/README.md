# Calendar Manager（Python 編排版）— 給行事曆主人的說明

這個工具包讓你的 AI 助理幫你管一本行事曆（Google Calendar 或 iCloud 皆可），
並隨時把它印成漂亮的**月曆／週曆網頁和圖片**發到群組裡。

你只要用平常的方式交代事項——「8/2 09:00 部門月會，地點A」——剩下的事助理
和程式會分工完成：助理負責聽懂你的話（聽不懂、缺地點會回頭問你，不會亂猜），
程式負責把事件寫進行事曆、**寫完立刻從伺服器讀回來核對**、產生頁面、檢查
頁面沒壞，最後告訴你檔案在哪。每一步都有存證，助理不可能「說做完了其實沒做」。

## 與原版 calendar-manager 的差別

產出一模一樣。差別是中段——寫入、核對、產檔、驗證——從「助理照說明書做」
變成「一支程式一次做完」，換模型、換平台行為都相同。設計原則：
**策略保持柔性，執行保持剛性**（詳見 `references/orchestration.md`）。

## 一次性安裝

```bash
# iCloud 後端（建議：不需要任何 MCP server）
pip install -r scripts/icloud/requirements.txt
cp scripts/icloud/.credentials.example scripts/icloud/.credentials
# 編輯 .credentials，填入 Apple ID 與「App 專用密碼」（appleid.apple.com 產生）
# 詳細步驟：references/apple-calendar-setup.md

# 建議安裝（寫入計畫的 schema 驗證與圖片空白檢查）
pip install jsonschema Pillow

# 只有需要 PNG 圖片時才要
cd scripts && npm install
```

Google Calendar 後端的設定見 `references/hermes-setup.md`（Hermes）或
你的 agent 平台的 Google Calendar connector 文件。

## 日常使用（跟助理說就好）

- 「幫我加：8/2 09:00 部門月會，地點A」→ 助理整理成計畫檔、程式寫入並讀回
  核對，有疑似打錯的（同一章連排三天之類）會先提醒你。
- 「產 8 月的月曆和週曆」→ 一個指令產出全部頁面，並附驗證結果。
- 「傳圖給我」→ 產 PNG 並直接傳到聊天視窗。

產出檔案預設收在 `~/mein-agent-storage/cal-out/<年月>/` 底下，一次產出一個
資料夾，內含 `manifest.json`（產了什麼、驗證過沒的完整紀錄）。

## 常見問題

- **圖片裡的中文變成方框？** Linux 主機沒裝中文字型。程式會在產圖前擋下並
  提示 `sudo apt install -y fonts-noto-cjk`。
- **產圖失敗說找不到 Chrome？** 執行 `npx puppeteer browsers install chrome`
  （不需要 root）再重試。
- **想改顏色或版面？** 改 `assets/` 裡的兩個模板檔，然後請助理重產——不要
  直接改產出的 HTML，下個月會被蓋掉。
- **地點顏色怎麼決定？** 你常用的地點在 `scripts/generate_calendar.py` 的
  `LOC_CLASS` 裡固定配色（顏色會讓你習慣，不會變動）；新出現的地點自動拿
  粉／黃／紫／紅四個備用色。

## 給要改這個工具包的人

先讀 `references/orchestration.md`，改完跑 `python3 -m pytest tests/ -q`。
