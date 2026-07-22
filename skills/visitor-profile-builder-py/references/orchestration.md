# 編排層：策略柔性、執行剛性

這份 `-py` skill 和原版 `visitor-profile-builder` 產出的檔案完全相同，差別
只在**中段的執行方式**。原版把「產檔 → 確認檔案在 → 放到對的資料夾 → 收工」
這一段交給 agent 照 `SKILL.md` 的散文去做；這一版把整段收進一支
`scripts/build.py`，讓它變成不管哪個模型來跑、行為都一樣的確定性流程。

## 一句話的設計主張

> **策略保持柔性，執行保持剛性。**
>
> LLM 做軟的認知判斷，Python 做硬的執行與驗證，交界處讓 LLM 產生、Python 驗證。

對應到這個 skill：

| 分工 | 誰負責 | 落點 |
|---|---|---|
| 需求理解、上網查證、語意抽取、同名消歧、寫 note | **LLM／Skill（柔性）** | 由模型讀 `SKILL.md` 執行 |
| Job 目錄、Schema 驗證、產檔、圖片驗證、原子改名、Manifest | **Python（剛性）** | `build.py` 一次做完 |
| 交界：把查到的事實變成 `profile.json` | **LLM 產出＋Python 驗證** | 模型填 JSON，`validate_profile.py` 擋錯 |

## 三個原版靠散文、這版靠程式的環節

原版 `SKILL.md` 裡有三段是「請 agent 記得要做」的指令。它們只有在模型讀到、
且願意照做時才生效。這版把三段都變成 `build.py` 每次必跑的程式：

1. **「產檔後看一眼確認沒壞」→ `verify_output.py`。**
   截圖會無聲失敗（截斷、字型沒載、圖片路徑壞掉）。這版對每個產出跑結構化
   檢查：PNG 檢查檔頭是不是真的 PNG、尺寸夠不夠大、是不是整張單一顏色；
   HTML 檢查有沒有姓名、版型容器、有沒有收尾標籤；xlsx 檢查 openpyxl 開得開、
   A2 是不是「個人信息登記表」。沒通過就不會被回報成「完成」。

2. **「Linux 上先確認有中文字型」→ `cjk_font_check()`（PNG 前置檢查）。**
   乾淨的 Linux server 沒有 CJK 字型，Chrome 會把每個中文烤成空心方框且不報錯。
   這版在啟動瀏覽器**之前**先跑 `fc-list :lang=zh`，沒有字型就直接擋下並教你
   怎麼裝，而不是產出一張壞圖再期待有人去看。

3. **「檔案放對資料夾、PNG 放在 HTML 旁邊」→ Job 目錄＋Manifest。**
   一個 job = 一個人 = 一個資料夾。所有產出寫進去，並登記在 `manifest.json`。

## 查資料階段也能少幾步

上面三條是「產檔」階段。填 `profile.json` 之前的幾個機械步驟同樣收進程式，
讓模型只留下真正需要判斷的部分：

- **入口 A 一行搞定。**`build.py` 直接吃來源 xlsx（副檔名是 `.xlsx` 就在行程內
  呼叫 `xlsx_to_profile_json.extract()`），不必先抽成 json、再記得跑驗證。
- **`normalize()`：填機器決定得了的欄位。**`build.py` 在驗證前先跑：
  `timestamp` 空白就填今天；照片的 `source_url` 自動併進 `sources`（原本只是
  驗證器的一條警告，要模型自己去補）。這兩件都不需要判斷，就不該佔模型的注意力。
- **照片下載＋檢查 → `fetch_image.py`。**破 `.edu.tw` 的 403（瀏覽器 UA＋
  Referer）、確認收到的真的是圖片而不是被存成 `.jpg` 的 HTML 錯誤頁、解碼抓
  截斷、回報尺寸——全部是程式。模型只留下「這是不是本人」這個判斷。

## Artifact Manifest 與 Artifact ID

`build.py` 跑完會在 job 目錄寫一份 `manifest.json`。每個產出登記為一筆
**artifact**，帶一個穩定的 **artifact id**、真實路徑、位元組大小、sha256、
以及驗證結果：

| artifact id | 內容 |
|---|---|
| `profile-json` | 這批產出所依據的 `profile.json` 副本（出處存證） |
| `card-html` | HTML 個人檔案卡片 |
| `registry-xlsx` | 個人信息登記表 xlsx |
| `card-png` | HTML 的手機版截圖（只有要求 png 時才有） |

**為什麼要 id、不要自由路徑：**原版最根本的問題是「agent 宣稱產出，實際
沒有」——它憑推理報一條它以為存在的路徑。Manifest 是這件事的解方：後續步驟
要引用某個產出時，不要自己用姓名＋資料夾慣例拼路徑，而是問 manifest。

```bash
python3 scripts/job.py list  <job_dir>                 # 這個 job 有哪些 artifact、各自驗證過沒
python3 scripts/job.py path  <job_dir> card-png        # 印出 card-png 的真實絕對路徑
python3 scripts/job.py verify <job_dir>                # 重新雜湊所有檔案，比對 manifest（偵測被刪/被改）
```

`manifest.record()` 是先確認檔案存在、當場算 sha256 才登記，所以 manifest 裡
不可能有一筆指向「宣稱有、其實不存在」的檔案。這是「消除幻覺、每步有明確
狀態」在這個 skill 裡的具體形狀。

## 原子改名：為什麼不直接寫到最終路徑

`build.py` 產每個檔都先寫進 job 的 `.tmp/`，通過驗證後才用 `os.replace` 搬到
最終位置（同一個檔案系統，`os.replace` 是原子操作）。好處：讀檔的人或重跑一次
時，最終路徑上要嘛是舊的完整檔、要嘛是新的完整檔，**永遠不會讀到寫到一半的
html 或截斷的 xlsx**。驗證沒過的 xlsx 根本不會被搬進去；驗證沒過但已產出的
PNG（例如字型有疑慮）會被搬進去但在 manifest 裡標記為未通過，方便你進去看。

## 退場條件

`build.py` 的離開碼就是誠實的「到底成功沒」：只有每個被要求的 artifact 都
產出且通過驗證，才回傳 0。加 `--json` 會在 stdout 印出機器可讀的結果摘要，
讓 agent 讀回真實狀態，而不是從自己的散文猜。

實作細節見 `scripts/build.py`、`scripts/job.py`、`scripts/verify_output.py`
三支的檔頭說明。要改欄位契約仍然是改 `assets/profile.schema.json`，與原版
一致（見 `field-contract.md`）——編排層不碰欄位規則。
