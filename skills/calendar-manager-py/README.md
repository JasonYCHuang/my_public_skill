# Calendar Manager（Python 編排版）— 給行事曆主人的說明

讓 AI 助理幫你管一本行事曆（Google Calendar 或 iCloud），隨時印成漂亮的
**月曆／週曆網頁和圖片**發到群組。

你用平常的方式交代——「8/2 09:00 部門月會，地點A」——助理負責聽懂（缺地點
會回頭問你，不亂猜），程式負責寫進行事曆、**寫完立刻從伺服器讀回核對**、
產頁面、驗證沒壞。每步有存證，助理不可能「說做完了其實沒做」。

與原版 calendar-manager 產出相同；差別是中段從「助理照說明書做」變成
「一支程式做完」，換模型行為一致。原則：**策略保持柔性，執行保持剛性**
（詳見 `references/orchestration.md`）。

## 一次性安裝

```bash
python3 scripts/doctor.py --png   # 體檢；缺什麼直接給修復指令
```

典型修復：`pip install -r scripts/icloud/requirements.txt`、把
`.credentials.example` 複製成 `.credentials` 填 App 專用密碼（詳見
`references/apple-calendar-setup.md`）、`cd scripts && npm install`。
Google 後端見 `references/hermes-setup.md` 或你的平台的 connector 文件。

## 日常使用（跟助理說就好）

- 「幫我加：8/2 09:00 部門月會，地點A」→ 寫入並讀回核對；疑似打錯（同一章
  連排三天）會先提醒。
- 「產 8 月的月曆和週曆」→ 一個指令產出全部頁面＋驗證結果。
- 「傳圖給我」→ 產 PNG 直接傳進聊天視窗。

產出收在 `~/mein-agent-storage/cal-out/<年月>/`，每次一個資料夾，內含
`manifest.json`（產了什麼、驗證過沒的完整紀錄）。

## 常見問題

- **圖片中文變方框？** Linux 沒中文字型；產圖前會擋下並提示
  `sudo apt install -y fonts-noto-cjk`。
- **找不到 Chrome？** `npx puppeteer browsers install chrome`（免 root）。
- **想改顏色版面？** 改 `assets/` 兩個模板檔後請助理重產；別直接改產出的
  HTML，下個月會被蓋掉。
- **地點顏色怎麼定？** 常用地點寫在 `assets/loc-class.json`（改資料檔即可），
  配色固定不變；新地點自動拿粉／黃／紫／紅備用色。

改工具包本身：先讀 `references/orchestration.md`，改完跑
`python3 -m pytest tests/ -q`。
