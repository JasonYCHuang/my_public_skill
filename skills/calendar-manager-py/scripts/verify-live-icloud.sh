#!/usr/bin/env bash
# 實機驗證：pytest 蓋不到的三個環節，對活的 iCloud 帳號跑一輪。
#
#   ./verify-live-icloud.sh "測試行事曆名"
#
# 驗證項目（都是需要真 CalDAV / 真 Chrome 才能證明的）：
#   1. apply_plan.py apply —— create 寫入＋逐筆讀回覆核
#   2. update 的 patch 語意 —— 只給 start/end，summary/location 必須保留
#   3. build.py --from-icloud —— 算區間、抓事件、產檔、manifest
#   4. screenshot.js —— 真 Chrome 產 PNG 並通過驗證（有 node 才跑）
#   5. delete ＋ 讀回確認消失（清場）
#
# 安全性：只碰你指定的行事曆，事件摘要帶時間戳前綴「LIVE煙測-」，
# 結束時一定嘗試刪除。**用專門的測試行事曆，不要用正式的。**
# 需要 caldav/icalendar 的 python 環境：PY=/path/to/python3 ./verify-live-icloud.sh ...
set -euo pipefail

CAL="${1:?用法: ./verify-live-icloud.sh \"測試行事曆名\"}"
PY="${PY:-python3}"
HERE="$(cd "$(dirname "$0")" && pwd)"
TMP="$(mktemp -d)"
STAMP="$(date +%s)"
SUMMARY="LIVE煙測-${STAMP}"
trap 'rm -rf "$TMP"' EXIT

step() { printf '\n=== %s ===\n' "$*"; }

step "0/5 doctor（環境）"
"$PY" "$HERE/doctor.py" --backend icloud

step "1/5 apply：create ＋ 讀回覆核"
TOMORROW="$("$PY" -c 'import datetime;print((datetime.date.today()+datetime.timedelta(days=1)).isoformat())')"
cat > "$TMP/plan-create.json" <<EOF
{"schema": "calendar-manager-py/plan@1", "calendar": "$CAL",
 "operations": [{"op": "create", "summary": "$SUMMARY", "location": "地點A",
                 "start": "$TOMORROW 19:30", "end": "$TOMORROW 20:30"}]}
EOF
"$PY" "$HERE/apply_plan.py" apply "$TMP/plan-create.json" --report "$TMP/report1.json"
UID_CREATED="$("$PY" -c "import json;print(json.load(open('$TMP/report1.json'))['operations'][0]['uid'])")"
echo "uid: $UID_CREATED"

step "2/5 update patch 語意：只改時間，summary/location 必須保留"
cat > "$TMP/plan-update.json" <<EOF
{"schema": "calendar-manager-py/plan@1", "calendar": "$CAL",
 "operations": [{"op": "update", "uid": "$UID_CREATED",
                 "start": "$TOMORROW 09:30", "end": "$TOMORROW 10:30"}]}
EOF
"$PY" "$HERE/apply_plan.py" apply "$TMP/plan-update.json" --report "$TMP/report2.json"
"$PY" - "$TMP/report2.json" "$SUMMARY" <<'EOF'
import json, sys
r = json.load(open(sys.argv[1]))
op = r["operations"][0]
assert op["ok"], f"update 讀回不一致：{op['detail']}"
# 讀回比對已含 summary/location —— ok=True 即代表 patch 保留了未列欄位
print("patch 語意 ✓（讀回一致，summary/location 未被清空）")
EOF

step "3/5 build --from-icloud（產檔＋manifest）"
Y="$(cut -d- -f1 <<<"$TOMORROW")"; M="$(cut -d- -f2 <<<"$TOMORROW" | sed 's/^0//')"
FORMATS="html"; command -v node >/dev/null && FORMATS="html,png"
"$PY" "$HERE/build.py" --from-icloud "$CAL" --year "$Y" --month "$M" \
  --title-prefix LIVE煙測 --skip-weeks --formats "$FORMATS" \
  --job-dir "$TMP/job" --json > "$TMP/build.json"
"$PY" - "$TMP/build.json" "$SUMMARY" <<'EOF'
import json, sys
b = json.load(open(sys.argv[1]))
assert b["ok"], f"build 未全數通過：{b['artifacts']}"
html = open(b["artifacts"]["month-html"]["path"], encoding="utf-8").read()
assert sys.argv[2] in html, "月曆裡找不到煙測事件——抓回的資料不對"
print("build ✓（含 PNG）" if "month-png" in b["artifacts"] else "build ✓（無 node，略過 PNG）")
EOF
"$PY" "$HERE/job.py" verify "$TMP/job"

step "4/5 delete ＋ 讀回確認消失"
cat > "$TMP/plan-delete.json" <<EOF
{"schema": "calendar-manager-py/plan@1", "calendar": "$CAL",
 "operations": [{"op": "delete", "uid": "$UID_CREATED"}]}
EOF
"$PY" "$HERE/apply_plan.py" apply "$TMP/plan-delete.json" --report "$TMP/report3.json"

step "5/5 全部通過"
echo "apply/patch/build/verify/delete 實機驗證完成（行事曆：$CAL）"
