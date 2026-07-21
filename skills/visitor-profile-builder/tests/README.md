# Tests

```bash
python3 -m pip install pytest openpyxl jsonschema Pillow
python3 -m pytest tests/ -q          # 從 skill 根目錄執行
```

不需要 Chrome、不需要網路，全部跑完不到一秒。

## 為什麼是這四支

| 檔案 | 守的是什麼 |
|---|---|
| `test_field_contract.py` | 10 欄位契約：必填、封閉集合、四個數量上限、空值只有 `-` 一種寫法 |
| `test_roundtrip.py` | `json → xlsx → json` 不掉資料、不變型別、不累加標籤 |
| `test_generators.py` | 產出的 HTML/xlsx 結構：meta 標籤、頁尾、佔位圖、跳脫 |
| `test_docs_consistency.py` | **文件是否還在描述程式真正的行為** |

第四支是這裡最不尋常、也最值得留著的一支。純人工 review 最容易漏掉的不是
邏輯錯誤，而是「程式改了、描述它的那段話沒改」——函式被刪了文件還在提、
上限改了表格沒動、範例檔過期。這類問題不會讓任何東西壞掉，只會讓下一個人
（或下一個 agent）照著錯的說明做事。

其中 `test_example_html_is_up_to_date` 直接把 `maintaining.md` 的規定變成
機械檢查：改了模板或範例 JSON 卻沒重產 `assets/profile.example.html`，測試
就會失敗並印出重產指令。

## 移植到別的環境或別的 LLM 時

跑這套只證明**確定性的那一半**沒問題。skill 還有另一半是 `SKILL.md` 裡給
agent 讀的自然語言指令，pytest 對它無能為力。

真正在約束那一半的是 `validate_profile.py`：不管哪個模型來填 `profile.json`，
欄位填錯、亂寫「不詳」、超過筆數上限，一律擋下不產檔。所以**驗證器本身就是
LLM 那一層的測試**，而這套 pytest 是在測「那個測試還有沒有效」。

要提高換模型的把握，最有效的做法不是加更多 pytest，而是把目前只寫在
`SKILL.md` 裡的規則，能移進驗證器的都移進去。

PNG 那條路徑只在 Linux 上才會出問題，測不到，見 `scripts/verify-on-ubuntu.sh`。

## 加測試時

以修過的 bug 為優先——每支測試的 docstring 都寫了它守著哪個具體失效，
`Regression:` 開頭的就是實際發生過的。
