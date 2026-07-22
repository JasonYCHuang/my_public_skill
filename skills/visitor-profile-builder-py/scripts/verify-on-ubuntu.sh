#!/usr/bin/env bash
#
# verify-on-ubuntu.sh — 在雲端 Linux／Ubuntu 純 CLI 環境上驗證
# visitor-profile-builder 這個 skill 能不能正常產出 PNG。
#
# 為什麼需要這支腳本：有三個修正只會在 Linux 上發作，在 macOS 上開發時
# 測不到，必須在目標機器上實跑一次：
#
#   [A] 中文字型   乾淨的 Ubuntu 沒有任何 CJK 字型，Chrome 會退回沒有中文
#                  字符的字型，PNG 裡每個中文字變成空心方框。全程不報錯。
#   [B] ARM64 快取 puppeteer 下載的 Chrome，其快取目錄在 arm64 上叫
#                  linux_arm-<版本>（含底線），不是 linux-<版本>。
#   [C] --no-sandbox
#                  Chrome 拒絕以 root 執行，而容器／雲端 VM 正是 root 常態。
#
# 用法：
#   ./verify-on-ubuntu.sh [skill 目錄]
#
#   這支腳本住在 skill 的 scripts/ 底下，不給參數時會自己往上找到 skill 根目錄：
#       cd ~/.claude/skills/visitor-profile-builder && ./scripts/verify-on-ubuntu.sh
#   也可以明確指定：
#       ./verify-on-ubuntu.sh ~/.claude/skills/visitor-profile-builder
#
# 這支腳本會安裝套件（python3-venv、nodejs、npm、fonts-noto-cjk）並下載
# 一份 Chrome 到 ~/.cache/puppeteer。純讀取的檢查請加 --dry-run 先看它要做什麼。
#
set -uo pipefail

DRY_RUN=0
[[ "${1:-}" == "--dry-run" ]] && { DRY_RUN=1; shift; }

# 沒給參數時自己找：這支腳本住在 skill 的 scripts/ 底下，所以先試上一層，
# 再退回腳本自己所在的目錄（腳本被單獨複製到 skill 根目錄時適用）。
_self_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [[ -z "${1:-}" ]]; then
  if   [[ -f "$_self_dir/../scripts/html_to_png.js" ]]; then SKILL_DIR="$(cd "$_self_dir/.." && pwd)"
  else SKILL_DIR="$_self_dir"; fi
else
  SKILL_DIR="$1"
fi
# 刻意「不」預設寫進當前目錄：從 skill 資料夾內執行時，那會把產出留在
# skill 裡，而這個 skill 明訂產出不得放在自己的資料夾內（它會被整包複製散布）。
OUT_DIR="${OUT_DIR:-$HOME/vpb-verify-out}"
VENV=/tmp/vpb-venv

# root 就直接跑，否則透過 sudo
SUDO=""
[[ "$(id -u)" -ne 0 ]] && SUDO="sudo"

pass=0; fail=0; warn=0
ok()   { echo "  ✅ $*"; pass=$((pass+1)); }
bad()  { echo "  ❌ $*"; fail=$((fail+1)); }
note() { echo "  ⚠️  $*"; warn=$((warn+1)); }
step() { echo; echo "──────── $* ────────"; }

step "0. 環境"
echo "  skill 目錄 : $SKILL_DIR"
echo "  產出目錄   : $OUT_DIR"
echo "  架構       : $(uname -m)"
echo "  使用者     : $(whoami)$([[ -z "$SUDO" ]] && echo ' (root)')"
[[ -r /etc/os-release ]] && { . /etc/os-release; echo "  發行版     : ${PRETTY_NAME:-unknown}"; }

if [[ ! -f "$SKILL_DIR/scripts/html_to_png.js" ]]; then
  echo; echo "找不到 $SKILL_DIR/scripts/html_to_png.js —— 請把 skill 目錄當參數傳入。"; exit 1
fi

if [[ $DRY_RUN -eq 1 ]]; then
  cat <<EOF

--dry-run：以下是這支腳本「會做」的事，現在不會執行。

  $SUDO apt-get install -y python3-venv nodejs npm fontconfig
  python3 -m venv $VENV && $VENV/bin/pip install openpyxl jsonschema Pillow
  (cd $SKILL_DIR/scripts && npm install)
  npx puppeteer browsers install chrome        # 下載約 150MB 到 ~/.cache/puppeteer
  $SUDO apt-get install -y fonts-noto-cjk      # 中文字型（[A] 的修正）
  產出兩張 PNG 到 $OUT_DIR/

EOF
  exit 0
fi

mkdir -p "$OUT_DIR"

step "1. 系統套件"
export DEBIAN_FRONTEND=noninteractive
# apt 的 http method 預設沒有逾時：連線一旦被靜默中斷就會無限期等待。
$SUDO tee /etc/apt/apt.conf.d/99vpb-timeout >/dev/null <<'EOF'
Acquire::http::Timeout "30";
Acquire::https::Timeout "30";
Acquire::Retries "3";
EOF
$SUDO apt-get update -qq
$SUDO apt-get install -y -qq python3 python3-venv nodejs npm fontconfig
echo "  python3 $(python3 -V 2>&1 | cut -d' ' -f2) / node $(node -v 2>/dev/null) / npm $(npm -v 2>/dev/null)"

step "2. Python 依賴"
# Ubuntu 的系統 python3 是 externally-managed，一律用 venv。
[[ -d "$VENV" ]] || python3 -m venv "$VENV"
"$VENV/bin/pip" install -q openpyxl jsonschema Pillow && ok "openpyxl / jsonschema / Pillow"

step "3. 產生 HTML 與 xlsx（不需要 Chrome，也不需要字型）"
cd "$SKILL_DIR"
"$VENV/bin/python3" scripts/profile_json_to_html.py \
    assets/profile.example.json -o /tmp/vpb.html >/dev/null && ok "HTML" || bad "HTML"
"$VENV/bin/python3" scripts/profile_json_to_xlsx.py \
    assets/profile.example.json -o /tmp/vpb.xlsx >/dev/null && ok "xlsx" || bad "xlsx"
"$VENV/bin/python3" scripts/xlsx_to_profile_json.py \
    /tmp/vpb.xlsx -o /tmp/vpb.json >/dev/null 2>&1 && ok "xlsx → json 來回轉換" || bad "來回轉換"

step "4. npm install"
(cd scripts && npm install --silent 2>&1 | tail -3)
PC_VER=$(node -p "require('$SKILL_DIR/scripts/node_modules/puppeteer-core/package.json').version" 2>/dev/null)
[[ -n "$PC_VER" ]] && ok "puppeteer-core $PC_VER" || bad "puppeteer-core 沒裝起來"

step "5. 尚無 Chrome：確認錯誤訊息可行動"
if node scripts/html_to_png.js /tmp/vpb.html >/tmp/vpb-nochrome.log 2>&1; then
  note "此機器已有系統 Chrome，跳過「找不到 Chrome」的情境"
  HAD_SYSTEM_CHROME=1
else
  HAD_SYSTEM_CHROME=0
  if grep -q "npx puppeteer browsers install chrome" /tmp/vpb-nochrome.log; then
    ok "錯誤訊息有指出下一步該做什麼"
  else
    bad "錯誤訊息沒有可行動的指示："; sed 's/^/      /' /tmp/vpb-nochrome.log | head -4
  fi
fi

step "6. 下載 Chrome　→ 驗證 [B] ARM64 快取路徑"
(cd scripts && npx --yes puppeteer browsers install chrome 2>&1 | tail -3)
CACHE=~/.cache/puppeteer/chrome
if [[ -d "$CACHE" ]]; then
  echo "  快取目錄內容：$(ls -1 "$CACHE" | tr '\n' ' ')"
  ENTRY=$(ls -1 "$CACHE" | head -1)
  case "$(uname -m)" in
    aarch64|arm64)
      if [[ "$ENTRY" == linux_arm-* ]]; then
        ok "[B] arm64 快取前綴為 linux_arm- —— 與 html_to_png.js 相符"
      else
        bad "[B] 預期 linux_arm-，實際是 '$ENTRY' —— html_to_png.js 的 CHROME_CACHE_PREFIX 要改"
      fi;;
    *)
      [[ "$ENTRY" == linux-* ]] && ok "[B] x64 快取前綴為 linux-" \
                                || bad "[B] 預期 linux-，實際是 '$ENTRY'";;
  esac
else
  note "[B] 沒有快取目錄 —— Chrome for Testing 可能不提供此架構的版本。"
  note "     若如此，改用系統套件：$SUDO apt-get install -y chromium-browser"
fi

step "7. 截圖：字型「尚未」安裝（[A] 的失敗情境）"
echo "  fc-list :lang=zh 筆數 = $(fc-list :lang=zh 2>/dev/null | wc -l)"
rm -f /tmp/vpb.png
if node scripts/html_to_png.js /tmp/vpb.html >/tmp/vpb-nofont.log 2>&1; then
  cp /tmp/vpb.png "$OUT_DIR/1-before-fonts.png" 2>/dev/null
  ok "截圖成功（→ $OUT_DIR/1-before-fonts.png）"
  echo "     注意：這張圖裡的中文「預期」是空心方框。這是要對照用的。"
else
  bad "截圖失敗："; sed 's/^/      /' /tmp/vpb-nofont.log | grep -v "^ *at " | head -4
fi

step "8. 安裝中文字型後重截　→ 驗證 [A]"
$SUDO apt-get install -y -qq fonts-noto-cjk
$SUDO fc-cache -f >/dev/null 2>&1
ZH=$(fc-list :lang=zh | wc -l)
echo "  fc-list :lang=zh 筆數 = $ZH"
if [[ "$ZH" -gt 0 ]]; then
  ok "[A] 系統已有中文字型"
  fc-list :lang=zh family 2>/dev/null | tr ',' '\n' | grep -i "noto sans cjk" | head -2 | sed 's/^/     /'
  if fc-list :lang=zh family 2>/dev/null | grep -qi "Noto Sans CJK TC"; then
    ok "[A] 有 'Noto Sans CJK TC' —— 與 HTML 的 font-family 相符"
  else
    note "[A] 找不到 'Noto Sans CJK TC' 這個家族名；有其他中文字型，Chrome 仍可能"
    note "     透過 sans-serif 的 fontconfig 替換正常顯示。務必看圖確認。"
  fi
else
  bad "[A] 裝完仍無中文字型 —— PNG 的中文一定是空心方框"
fi
rm -f /tmp/vpb.png
if node scripts/html_to_png.js /tmp/vpb.html >/tmp/vpb-font.log 2>&1; then
  cp /tmp/vpb.png "$OUT_DIR/2-after-fonts.png" 2>/dev/null
  ok "截圖成功（→ $OUT_DIR/2-after-fonts.png）"
else
  bad "截圖失敗："; sed 's/^/      /' /tmp/vpb-font.log | grep -v "^ *at " | head -4
fi

step "9. [C] --no-sandbox（以 root 執行時才有意義）"
if [[ -z "$SUDO" ]]; then
  if grep -q "系統 Chrome 不可用" /tmp/vpb-font.log 2>/dev/null; then
    note "[C] 走的是「已下載的 Chrome」這條 fallback；系統 Chrome 那條沒被驗到"
  else
    ok "[C] 以 root 執行且截圖成功 —— Chrome 沒有因缺少 --no-sandbox 而拒絕啟動"
  fi
else
  note "[C] 目前非 root，這條測不到。要驗的話用 sudo 重跑一次。"
fi

step "結果"
echo "  通過 $pass　失敗 $fail　提醒 $warn"
echo
echo "  最後一步請務必自己做 —— 把兩張圖打開比對："
echo "     $OUT_DIR/1-before-fonts.png   （中文預期為空心方框）"
echo "     $OUT_DIR/2-after-fonts.png    （中文預期正常顯示）"
echo
echo "  沒有任何自動檢查能取代看圖：字型失敗時不會有錯誤訊息、exit code 也是 0。"
echo "  在本機看的話："
echo "     scp <這台>:$OUT_DIR/*.png ."
echo
[[ $fail -eq 0 ]] && echo "  自動檢查全數通過。" || echo "  有 $fail 項失敗，見上方 ❌。"
exit $(( fail > 0 ? 1 : 0 ))
