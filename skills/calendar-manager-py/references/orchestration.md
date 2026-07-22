# 編排層：策略柔性、執行剛性

這份 `-py` skill 和原版 `calendar-manager` 產出的檔案、寫入的行事曆完全相同，
差別只在**中段的執行方式**。原版把「寫入後確認有存進去」「產檔後看一眼沒壞」
「檔案放對資料夾」這些環節交給 agent 照 `SKILL.md` 的散文去做；這一版把兩條
工作流的中段各收進一支程式，讓它變成不管哪個模型來跑、行為都一樣的確定性流程。

## 一句話的設計主張

> **策略保持柔性，執行保持剛性。**
>
> LLM 做軟的認知判斷，Python 做硬的執行與驗證，交界處讓 LLM 產生、Python 驗證。

對應到這個 skill 的兩條工作流：

| 分工 | 誰負責 | 落點 |
|---|---|---|
| 判讀「時間、地點、事項」、缺欄位問人、消歧、後端選擇 | **LLM／Skill（柔性）** | 由模型讀 `SKILL.md` 執行 |
| 寫入行事曆、讀回覆核、typo 偵測、產檔、驗證、Manifest | **Python（剛性）** | `apply_plan.py`、`build.py` |
| 交界：把使用者的話變成 `plan.json` | **LLM 產出＋Python 驗證** | 契約在 `assets/plan.schema.json`，`validate_plan.py` 擋錯 |

## 原版靠散文、這版靠程式的環節

### 寫入側（entries → calendar）

1. **「新增後跑 list_events 確認有寫進去——non-negotiable」→ 逐筆讀回覆核。**
   `apply_plan.py apply` 對每筆 create/update 寫完立刻從伺服器讀回、逐欄比對
   （summary/location/start/end），delete 則讀回確認已不存在。結果寫進
   `apply-report.json`，離開碼非零就是沒全過。Google 後端由 agent 用自己的工具
   寫入，但同一套覆核以 `apply_plan.py check plan.json events.json` 補上——
   「相信工具呼叫成功了」被換成「把伺服器現況抓回來比對」。

2. **「iCloud update 是全欄位覆寫，記得帶上沒改的欄位」→ patch 語意。**
   plan 的 update op 只列想改的欄位；程式先讀事件現值、合併、再寫回。
   「改個時間結果地點被清空」這個陷阱由程式扛，不佔模型的注意力。

3. **「批次相似事件要檢查跨日 typo」→ 機械偵測。**
   原版要模型在批次寫入後自己「叫出來看看有沒有可疑的重複」。這版在**寫入前**
   就跑：完全重複（同摘要同開始時間）是錯誤直接擋下；同摘要跨多日、編號系列
   重複或未隨日期遞增（「連三天同一章」模式）是警告，模型必須轉達使用者確認。

4. **「只給開始時間就用預設時長算結束」→ `normalize()`。**
   缺 `end` 由 `default_duration_minutes` 填；全天事件展開成 00:00–23:59 慣例。
   機器決定得了的欄位不該佔模型的注意力。

### 產出側（calendar → HTML/PNG）

5. **「抓比整月稍寬的區間」→ `fetch_range_for_month()`。**
   週曆會溢進鄰月，該抓多寬是週次規則的算術，不是模型的判斷。
   `build.py --from-icloud` 更把「算區間→抓→產檔」收成一行。

6. **「產 PNG 後自己看一眼確認沒壞」→ `verify_output.py`。**
   截圖會無聲失敗。這版對每個 HTML 檢查 `<title>`、日格數、收尾標籤；對每個
   PNG 檢查檔頭、尺寸、是不是整張單一顏色。沒通過就不會被回報成「完成」。
   （結構檢查看不出「最後一欄徽章被裁掉」這種視覺問題——模型自己看一眼 PNG
   這步仍保留，這是柔性判斷。）

7. **「Linux 上先確認有中文字型」→ `cjk_font_check()`。**
   乾淨的 Linux server 沒有 CJK 字型，Chrome 會把中文烤成空心方框且不報錯。
   這版在啟動瀏覽器**之前**跑 `fc-list :lang=zh`，沒字型直接擋下並教你怎麼裝。

8. **「檔案放對資料夾」→ Job 目錄＋Manifest。**
   一個 job = 一個渲染月份 = 一個資料夾，產出全部登記在 `manifest.json`。

## Artifact Manifest 與 Artifact ID

`build.py` 跑完會在 job 目錄寫一份 `manifest.json`。每個產出登記為一筆
**artifact**，帶穩定的 **artifact id**、真實路徑、位元組大小、sha256、驗證結果：

| artifact id | 內容 |
|---|---|
| `events-json` | 這批視圖所依據的事件陣列副本（出處存證） |
| `month-html` | 月曆 HTML |
| `week-1-html` … | 每個 Monday-start 週的週曆 HTML |
| `month-png`、`week-1-png` … | 對應截圖（只有要求 png 時才有） |

**為什麼要 id、不要自由路徑：**原版最根本的風險是「agent 宣稱產出，實際沒有」
——憑推理報一條它以為存在的路徑。後續要引用產出時，問 manifest：

```bash
python3 scripts/job.py list   <job_dir>            # 有哪些 artifact、各自驗證過沒
python3 scripts/job.py path   <job_dir> month-png  # 真實絕對路徑
python3 scripts/job.py verify <job_dir>            # 重新雜湊比對（偵測被刪/被改）
```

`manifest.record()` 先確認檔案存在、當場算 sha256 才登記，所以 manifest 裡
不可能有一筆指向「宣稱有、其實不存在」的檔案。寫入側的對應物是
`apply-report.json`：每筆操作的讀回覆核結果，放在 plan.json 旁。

## 原子改名：為什麼不直接寫到最終路徑

`build.py` 所有產出先寫進 job 的 `.tmp/`，驗證後才用 `os.replace` 搬到最終
位置（同一檔案系統內是原子操作）。讀檔的人或重跑一次時，最終路徑上要嘛是舊的
完整檔、要嘛是新的完整檔，永遠不會讀到寫一半的 html 或截斷的 png。字型預檢
沒過但仍要求產出的 PNG 會被搬進去方便查看，但在 manifest 裡標記未通過。

## 退場條件

`build.py` 與 `apply_plan.py` 的離開碼就是誠實的「到底成功沒」：只有每個被
要求的 artifact／每筆操作都通過驗證才回傳 0。`--json` 在 stdout 印機器可讀
摘要，讓 agent 讀回真實狀態，而不是從自己的散文猜。

實作細節見 `scripts/build.py`、`scripts/apply_plan.py`、`scripts/job.py`、
`scripts/verify_output.py` 的檔頭說明。要改寫入欄位規則是改
`assets/plan.schema.json`——編排層不碰欄位規則。
