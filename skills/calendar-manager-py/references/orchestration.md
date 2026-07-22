# 編排層：策略柔性、執行剛性

> **策略保持柔性，執行保持剛性。**
>
> LLM 做軟的認知判斷，Python 做硬的執行與驗證，交界處讓 LLM 產生、Python 驗證。

與原版 `calendar-manager` 產出相同、寫入相同；差別是中段從「agent 照散文做」
變成確定性程式——換模型、換平台行為一致。

| 分工 | 誰 | 落點 |
|---|---|---|
| 缺欄位問人、消歧、後端選擇 | LLM（柔性） | `SKILL.md` 的四件判斷 |
| 解析、寫入、讀回覆核、typo 偵測、產檔、驗證、Manifest | Python（剛性） | 下表 |
| 交界：使用者的話 → `plan.json` | LLM 補缺口＋Python 驗證 | `assets/plan.schema.json` |

## 原版散文 → 這版程式

寫入側：

0. **terse 格式判讀** → `parse_entries.py`。M/D 補年、`1930`＝19:30、晚上+12、
   地點切分——全是機械規則。解析不了的行逐行點名，模型只處理缺口。
1. **「寫完跑 list_events 確認——non-negotiable」** → 逐筆讀回覆核。
   `apply apply` 每筆寫完即從伺服器讀回逐欄比對，結果進 `apply-report.json`；
   Google 後端用 `check plan.json events.json` 補同一套覆核。
2. **「iCloud update 全欄位覆寫，帶上沒改的欄位」** → patch 語意：程式讀現值
   合併，改時間不再默默清空地點。
3. **「批次後自查跨日 typo」** → 寫入**前**偵測：完全重複＝錯誤擋下；同摘要
   跨日、編號重複/亂序（「連三天同一章」）＝警告，須轉達。
4. **「只給開始就用預設時長」** → `normalize()` 自動填；全天展開 00:00–23:59。

產出側：

5. **「抓比整月稍寬的區間」** → `fetch_range_for_month()` 精確算術；
   `build.py --from-icloud` 收成一行。
6. **「產 PNG 後自己看一眼」** → `verify_output.py`：HTML 查 `<title>`/日格數/
   收尾，PNG 查檔頭/尺寸/單色。沒過不會被報成完成。（視覺裁切仍留人眼——柔性。）
7. **「Linux 先確認中文字型」** → 瀏覽器啟動前 `cjk_font_check()`，沒字型
   直接擋下附安裝指令。
8. **「檔案放對資料夾」** → 一個 job＝一個渲染月份＝一個資料夾＋manifest。

周邊：

- 安裝散文 → `doctor.py`（✗ 附修復指令）。
- Google 該抓的區間 → `build.py --print-range`、`apply_plan.py range`。
- MEDIA: 行、月曆在前 → `job.py media`（重試階梯仍是柔性判斷）。
- onboard 改 LOC_CLASS → `assets/loc-class.json` 資料檔。

## Artifact Manifest 與 Artifact ID

`build.py` 在 job 目錄寫 `manifest.json`：每個 artifact 有穩定 id、真實路徑、
大小、sha256、驗證結果。

| artifact id | 內容 |
|---|---|
| `events-json` | 視圖所依據的事件副本（出處存證） |
| `month-html` / `month-png` | 月曆 |
| `week-1-html` / `week-1-png` … | 各週 |

**要 id 不要自由路徑**：原版最根本的風險是「宣稱產出、實際沒有」。引用產出
一律問 manifest：

```bash
python3 scripts/job.py list   <job_dir>
python3 scripts/job.py path   <job_dir> month-png
python3 scripts/job.py verify <job_dir>     # 重雜湊，偵測被刪/被改
python3 scripts/job.py media  <job_dir>     # 已驗證 PNG 的 MEDIA: 行
```

`manifest.record()` 先確認檔案存在、當場算 sha256 才登記——manifest 裡不可能
有「宣稱有、其實不存在」的檔案。寫入側對應物是 plan 旁的 `apply-report.json`。

## 原子寫入與退場條件

產出先寫 job 的 `.tmp/`，驗證後 `os.replace`（同檔案系統＝原子）搬到最終
位置——讀者永遠看不到寫一半的檔。字型預檢沒過仍硬產的 PNG 會搬入但標記未
驗證。`build.py`／`apply_plan.py` 離開碼＝誠實的成敗：全部通過才 0；`--json`
印機器可讀摘要，agent 讀回真實狀態而非從散文猜。

## 檔案契約總表

進出這個 skill 的每種 JSON 檔都有 schema，檔案內帶 `"schema"` 自我標識：

| 檔案 | schema id | 契約檔 | 驗證時機 |
|---|---|---|---|
| `plan.json`（輸入） | `plan@1` | `assets/plan.schema.json` | `validate_plan.py`／apply 前 |
| `events.json`（輸入） | `events@1` | `assets/events.schema.json` | `validate_events.py`／build 進場 |
| `manifest.json`（輸出） | `manifest@1` | `assets/manifest.schema.json` | tests 拿真實產出驗 |
| `apply-report.json`（輸出） | `apply-report@1` | `assets/apply-report.schema.json` | tests |

所有工具的 `--json` stdout 也統一信封：`{"schema": "calendar-manager-py/
<名稱>@1", "ok": bool, …}`——錯誤一律 `errors`、警告一律 `warnings`
（`parse_entries` 另有 `issues`＝待人／模型補的缺口）。

改欄位規則 → `assets/plan.schema.json`；改配色 → `assets/loc-class.json`。
編排層不碰規則本身。實作細節見各 script 檔頭。
