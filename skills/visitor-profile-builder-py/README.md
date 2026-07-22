# 個人檔案產生器（Python 編排版）— 給同事的使用說明

這是 `visitor-profile-builder` 的姊妹版本。**產出的檔案一模一樣**（好看的
HTML 個人檔案、格式一致的 xlsx、可選的 PNG），差別在**中間的產檔過程被收進
一支 Python 程式**，讓每一步都有明確狀態、每個檔案都經過驗證，agent 不會
「說產好了、結果檔案根本不在」。

用途跟原版相同：

- 手上已經有一份 xlsx 格式的個人信息表，想轉成方便閱讀分享的網頁版。
- 只有一個人名（例如某位訪客、某位教授），想請 agent 上網查資料，整理成跟
  公司既有格式一致的個人信息表（同時給 HTML 網頁版與 xlsx 版）。

這份說明是給人看的；同一個資料夾裡的 `SKILL.md` 是寫給 agent 看的技術指令，
你不需要去讀它。

---

## 這一版跟原版差在哪

原版把「產檔 → 確認檔案在 → 放到對的資料夾 → 收工」交給 agent 照文字指令
去做。這一版把整段收進 `scripts/build.py`，它一次做完：

1. **驗證**資料格式（欄位、上限、空值寫法），有錯就停，不產任何檔。
2. **產檔**：HTML／xlsx／（選用）PNG。
3. **檢查每個產出沒壞**：PNG 是不是真的圖、尺寸夠不夠、會不會整張空白；
   HTML 有沒有姓名、有沒有截斷；xlsx 開不開得起來。
4. **原子寫入**：先寫暫存檔、驗過才搬到定位，你永遠不會拿到一個寫到一半的檔。
5. **記帳**：在 job 資料夾裡留一份 `manifest.json`，逐筆記下每個檔案的真實
   路徑、大小、雜湊值、驗證結果。

另外幾個原本要 agent 手動處理的機械小事，這一版也交給程式：資料彙整時間
（`timestamp`）自動填今天、照片來源網址自動併進來源清單、給它一份 xlsx 就能
直接產檔（不用先轉成中繼檔）、下載照片時自動處理機構網站的擋圖（403）並確認
下載到的真的是圖片。

設計理念一句話：**策略保持柔性，執行保持剛性**——查資料、做判斷這種「軟」的
事交給 AI；產檔、驗證、記帳這種「硬」的事交給 Python。

---

## 開始使用前（每個人只需要做一次）

### 第一步：把資料夾放到你的 agent 找得到的地方

- **Claude Code**：複製（或 symlink）整個 `visitor-profile-builder-py/` 到
  專案底下的 `.claude/skills/visitor-profile-builder-py/`。
- **Hermes agent**：複製到 `~/.hermes/skills/visitor-profile-builder-py/`。
- **其他支援 agentskills.io 格式的 agent**：查該 agent 的 skill 目錄慣例。

### 第二步：確認 Python 環境有需要的套件

```bash
python3 -m pip install openpyxl jsonschema Pillow
```

（刻意寫 `python3 -m pip` 而非 `pip`：兩者常指向不同的 Python，裝錯環境會
出現「裝好了卻說找不到套件」。`Pillow` 用於把照片嵌進 xlsx、以及 PNG 的
空白檢查；`jsonschema` 用來檢查資料格式，建議裝。）

如果跳出「externally-managed-environment」之類錯誤（macOS Homebrew 版 Python
很常見），改建一個一次性虛擬環境，不影響系統 Python：

```bash
python3 -m venv /tmp/vpb-venv && /tmp/vpb-venv/bin/pip install openpyxl jsonschema Pillow
```

之後請 agent 用 `/tmp/vpb-venv/bin/python3` 執行 `scripts/` 裡的程式即可。

### 第三步（選用）：只有需要 PNG 圖檔才要做

這步需要 **Node.js**（HTML 跟 xlsx 都不用）。沒裝過先到
[nodejs.org](https://nodejs.org) 或 `brew install node`，然後在
`scripts/` 資料夾裡跑一次 `npm install`（會裝好 `puppeteer-core`）。截圖程式
會先試著用你電腦上已裝好的 Chrome。

**部署在雲端 Linux／純 CLI 環境**要多裝中文字型（**必要，不是選用**）：

```bash
sudo apt install -y fonts-noto-cjk        # 中文字型
npx puppeteer browsers install chrome     # 這種機器通常沒有系統 Chrome
```

乾淨的 Ubuntu server 完全不含中文字型，PNG 裡的中文會變成空心方框。這一版
**會在產 PNG 前先自動檢查有沒有中文字型**，沒有就直接擋下並告訴你要裝什麼，
而不是產出一張壞圖。懶得逐項確認的話，`scripts/verify-on-ubuntu.sh` 會把上面
全部做完並自我檢查。

---

## 日常怎麼用

跟 agent 講人話就好，它會在背後呼叫 `scripts/build.py`。

### 情境一：我手上已經有一份 xlsx，想轉成網頁

把檔案路徑給 agent：「把這份 xlsx 轉成 HTML 個人檔案」。

### 情境二：我只有一個人名，想請 agent 查資料建檔

「請網路搜尋，建立 XX大學 XX系 XX教授 的個人檔案」。agent 會確認身分、整理
學經歷（查不到的欄位誠實標「-」）、順便找照片（會先問你要用哪張）、產出
HTML 並列出資料來源。想同時要 xlsx 就說「也做一份 xlsx」。

### 情境三：想要 PNG 圖檔（貼到聊天室或簡報）

「幫我轉成 PNG」。這一版會在截圖前先檢查中文字型、截圖後自動檢查圖沒壞。

---

## 你會得到什麼

每次產檔會建立一個 **job 資料夾**，裡面有：

- **HTML 個人檔案**：卡片式版面，可直接用瀏覽器打開或轉寄。
- **xlsx 個人信息表**：版面對齊公司原本的「個人信息登記表」範本。
- **PNG 圖檔**（選用）：手機閱讀版型，直式、字大，方便貼聊天室。
- **manifest.json**：這份 job 的「帳本」，記下每個檔案的真實路徑與驗證結果。

**想先看看長什麼樣子**：用瀏覽器打開 `assets/profile.example.html`（虛構人物
「王小明」的完整範例）。

---

## 常見狀況

- **agent 說「驗證失敗，未產生檔案」**：這是刻意的保護。欄位有固定規格
  （教育經歷≤5、現任職位≤3、主要履歷≤10、照片≤2、來源≥1），違反時會擋下來
  而不是產出壞檔。請 agent 依訊息修正即可。
- **agent 說某個產出「未通過驗證」**：代表檔案產出了但檢查沒過（例如 PNG 疑似
  空白、或 Linux 上沒中文字型）。詳情在 job 資料夾的 `manifest.json` 裡。
- **看到 ⚠️「jsonschema 未安裝」**：檔案照樣產出，但少跑了結構驗證。把
  `jsonschema` 裝起來就會消失（macOS 內建 python3 常常沒有它）。
- **有些欄位寫「-」**：代表查不到這項資料。這是刻意設計——寧可誠實留空，也不
  用猜的。個人檔案固定就是 10 個欄位，查無資料一律顯示「-」。
- **備註欄提到「依新聞報導推估」**：代表這項不是官方公告，是合理推斷，需要更
  精確資訊建議自行查證。
- **想調整資料夾名稱／版型顏色**：直接跟 agent 說，它可以改 `scripts/` 裡的
  版型設定。

---

有任何問題，或想調整版面／欄位，直接跟你的 agent 說即可。
