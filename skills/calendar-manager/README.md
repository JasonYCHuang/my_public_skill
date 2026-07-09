# 行事曆管理法 — 給同事的使用說明

這份文件說明我們現在怎麼管理主管行事曆：**日曆本身（Google Calendar 或 iCloud，你選一種）
是唯一的真實資料來源**，月曆／週曆的 HTML 網頁、PNG 圖檔都是「照著日曆上的資料自動產生」出來的
——不用再手動維護 Excel 或 Word 檔，也不會有兩邊資料對不上的問題。

你只需要用打字告訴你的 AI agent（Claude Code 或 Hermes agent 都可以）時間、地點、事項，
其餘（寫進日曆、產生好看的月曆網頁、轉成圖片）都由它幫你完成。

這份「使用說明」是給人看的；同一個資料夾裡還有一份 `SKILL.md`，
是寫給 agent 看的技術指令，兩份搭配使用，你不需要去讀 `SKILL.md`。

---

## 這是什麼、為什麼這樣做

以前的作法是拿 Excel 或一份「流水帳」文字檔手動登記行程，再手動轉成月曆。問題是：
資料存在兩個地方，很容易忘記同步、越改越亂。

現在只有**一個地方**要維護：一個專屬的日曆（例如「XX董行事曆」），放在 Google Calendar
或 iCloud 都可以。你把行程講給 agent 聽，它直接寫進日曆；要看漂亮的月曆／週曆時，
agent 再從日曆讀出目前的資料，套上固定的版型，產生 HTML 網頁跟 PNG 圖檔。

**Google 還是 iCloud，選哪個？** 兩種都是「單一資料來源、agent 跟人改的是同一份」，
沒有孰優孰劣，純粹看習慣：
- 同事平常就用 Gmail/Google 生態系 → 選 Google Calendar
- 同事平常用 iPhone/Mac、習慣 Apple 內建的行事曆 App → 選 iCloud

兩邊甚至可以並存——不同人負責的日曆用不同後端都沒問題，只要同一份日曆的 agent
設定跟人都指向同一個後端就好。

這套方法不綁定特定產品——它是照著 [agentskills.io](https://agentskills.io)
這個開放格式寫的，Claude Code、Hermes agent，或其他支援同一種格式的 agent 都能用同一份
`calendar-manager/` 資料夾。差別只在「這個資料夾要放在哪裡」，見下方。

---

## 開始使用前（每個人只需要做一次）

### 第一步：把 `calendar-manager/` 資料夾放到你的 agent 找得到的地方

- **用 Claude Code 的人**：把整個 `calendar-manager/` 資料夾複製到你專案底下的
  `.claude/skills/calendar-manager/`。
- **用 Hermes agent 的人**：把整個 `calendar-manager/` 資料夾複製到
  `~/.hermes/skills/calendar-manager/`。

### 第二步：確認你的 agent 能讀寫日曆

先決定要用 **Google Calendar** 還是 **iCloud**（見上面「選哪個」），再照對應的步驟設定：

**用 Google Calendar：**
- **Claude Code**：到 claude.ai 網頁版 → 設定（Settings）
  → 連接器（Connectors）→ 找到 Google Calendar → 授權連接。（如果之後 agent
  說「需要重新授權 / token 過期」，回這裡重新連接一次即可）
- **Hermes agent**：Hermes 沒有內建 Google Calendar 連接器，
  需要自己設定一次。照著 `references/hermes-setup.md` 的步驟做（用
  `@cocal/google-calendar-mcp` 這個現成的開源 MCP 伺服器），
  `assets/hermes-mcp-config.example.yaml` 裡有可以直接複製貼上的設定範例。
  設定好之後，記得用 `hermes tools` 確認一下實際註冊出來的工具名稱，再開始使用。

**用 iCloud：**
- 不管 Claude Code 還是 Hermes、不管 agent 跑在你自己的電腦還是公司伺服器上都可以
  ——跟 Google Calendar 一樣是連到雲端，不是連到某一台特定的 Mac。
- 需要先去 appleid.apple.com 產生一組「App 專屬密碼」，再跑一次
  `pip install -r scripts/icloud/requirements.txt`。完整步驟（含常見錯誤排除）在
  `references/apple-calendar-setup.md`。

### 第三步：建立一個專屬日曆

不要用你的個人主要日曆，另外建一個專門放這份行事曆的日曆（例如「XX董行事曆」）。
- Google：Google Calendar 網頁左側「其他日曆」旁的「＋」→ 建立新日曆。
- iCloud：Calendar.app 裡「檔案 → 新增行事曆」，位置選你的 iCloud 帳號（**不要**選
  「On My Mac」本機專屬，那樣的話 agent 連不到）；或直接在 icloud.com/calendar 建立。

建好後告訴 agent 日曆名稱，Google 的話它會幫你找到對應的 ID 並記住；iCloud 的話
它會直接用這個名稱去對應。

### 第四步：跟 agent 確認兩件事

- 時區（一般預設 `Asia/Taipei`）
- 如果只給開始時間、沒給結束時間，預設要抓多久（目前用的慣例是 1 小時）

### 第五步（只有要轉 PNG 圖檔才需要）

在 `calendar-manager/scripts/` 資料夾跑一次 `npm install`。只需要做一次。

---

## 日常怎麼用

以下對話範例不管你用 Claude Code 還是 Hermes agent、不管用 Google 還是 iCloud，講法都一樣。

### 新增行程

直接跟 agent 說「時間、地點、事項」三件事，例如：

> 加入行事曆：2026.08.01 12:00 地點D 供應商會議

agent 會直接把它寫進日曆，不會再經過任何文字檔。

**如果你漏講了時間、地點或事項其中一項，agent 會先問你，不會自己亂猜**
（例如你只給了事項跟時間，沒給地點，它會停下來問，而不是隨便套用前一筆的地點）。

### 產生月曆／週曆網頁

跟 agent 說類似這樣的話：

> 8 月的月曆/週曆 HTML 也重新產生一次

agent 會讀取日曆上該月份的資料，套用固定版型（`assets/` 裡的兩個模板），
產生月曆（一整月）跟週曆（每週一份）的 HTML 檔案。

### 轉成圖片

如果需要圖片檔（例如要貼到聊天室或簡報），跟 agent 說：

> 請把 8 月的 html 轉為 png 圖檔

---

## 你會得到什麼樣的檔案

- **月曆網頁**：一整個月的格狀行事曆，每天顯示地點徽章（顏色區分不同地點／城市）跟當天行程
- **週曆網頁**：一週一份，格式跟月曆一致，方便單獨列印或傳送某一週的行程
- **PNG 圖檔**：跟網頁長得一模一樣，但是圖片格式，方便直接分享

月曆／週曆網頁的視覺設計（顏色、字體、地點徽章）全部來自 `assets/` 裡的兩個模板檔，
所有月份產生出來的網頁風格都會保持一致，不管是誰、用哪個 agent、哪種日曆後端產生的。

---

## 常見狀況

- **agent 說「需要重新授權」**（Google）：回你自己 agent 的連接器/MCP 設定重新連接
  Google Calendar 即可，不會遺失任何資料。
- **加地點時 agent 又問我一次**：這是刻意設計的，避免地點被猜錯、寫錯進日曆。
  如果同一批行程的地點都一樣，可以一次跟 agent 說清楚（例如「這幾筆都是地點D」），
  它就不會每筆都問。
- **想換人使用（不同主管、不同團隊）**：重複「開始使用前」的步驟，
  用不同的日曆名稱建立一個新的專屬日曆即可，其餘流程完全一樣，Google/iCloud 都可以換人重來一次。
- **換了一個新的 agent 產品**：只要它支援 agentskills.io 這個開放格式，
  把 `calendar-manager/` 資料夾放到它的 skill 目錄下就能用，不用重寫任何東西。
- **想用 iCloud 但 agent 是架在公司伺服器上跑的 Hermes bot，行不行**：行，這點
  iCloud 跟 Google Calendar 一樣，都是連到雲端的日曆服務，agent 不需要在某一台特定
  的 Mac 上執行。只要伺服器上有 Python、也有那組 App 專屬密碼的設定檔就能用，見
  `references/apple-calendar-setup.md`。
- **iCloud 的 App 專屬密碼過期或要換一組**：去 appleid.apple.com 重新產生一組，
  更新 `scripts/icloud/.credentials` 裡的內容即可，不會遺失任何資料。

---

有任何問題，或想調整月曆的顏色／版面，直接跟你的 agent 說即可——它可以直接修改
`assets/` 裡的模板，之後產生的所有月份都會套用新樣式。
