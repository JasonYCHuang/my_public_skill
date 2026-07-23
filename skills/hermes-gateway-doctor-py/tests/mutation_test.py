#!/usr/bin/env python3
"""Targeted mutation testing for doctor.py: break each safety property on
purpose; the pytest suite MUST turn red. A surviving mutant = a decorative
test (this once caught the journal_lines producer-side gap).

Run:  python3 tests/mutation_test.py     (exit 0 = all mutants killed)
Not collected by pytest (filename does not match test_*.py) — it runs pytest
itself against mutated sources.
"""
import pathlib
import subprocess
import sys

SKILL = pathlib.Path(__file__).resolve().parent.parent
DOCTOR = SKILL / "scripts/doctor.py"

MUTANTS = [
    ("M1 拔掉自殺守衛（在 unit 內也 fallback 直接 restart）",
     "if not self_kill:", "if True:"),
    ("M2 journal 讀不到改回傳 []（假 healthy 復活）",
     'return None\n    return r.stdout.splitlines()', 'return []\n    return r.stdout.splitlines()'),
    ("M3 噪音 regex 改過寬（吞掉真送信失敗）",
     r'poll error \(\d/\d\)', r'ERROR'),
    ("M4 verify 窗口不再從本次啟動起算",
     'since = args.since or since_last_start(args.unit) or "5 min ago"',
     'since = args.since or "5 min ago"'),
    ("M5 頻率守衛門檻 2→99（重啟循環復活）",
     "if n >= 2 and not args.force:", "if n >= 99 and not args.force:"),
    ("M6 拔掉 pending timer 去重（疊排重啟復活）",
     "if pending_restart():", "if False:"),
    ("M7 unit 名驗證錨點拔掉（-n 之類混得進去）",
     "^[A-Za-z0-9][A-Za-z0-9:_.@-]*$", "[A-Za-z0-9]"),
    ("M8 拔掉未知錯誤 catch-all（沒見過的 ERROR 靜默流失）",
     "elif UNKNOWN_ERR.search(ln):", "elif False:"),
    ("M9 session 判斷退回 v1（單獨過期證據被當 healthy）",
     "if c.session_lines:", "if c.session_lines and c.send_failures:"),
    ("M10 噪音 regex 改過窄（connect 失敗掉進 catch-all 誤觸重啟）",
     "POLL_NOISE = re.compile(r\"poll error \\(\\d/\\d\\)\")",
     "POLL_NOISE = re.compile(r\"poll error \\(\\d/\\d\\).*getupdates HTTP 5\\d\\d\")"),
]


def main():
    orig = DOCTOR.read_text()
    survivors = []
    try:
        for name, old, new in MUTANTS:
            assert old in orig, f"mutation target not found (doctor.py drifted?): {name}"
            DOCTOR.write_text(orig.replace(old, new, 1))
            r = subprocess.run(
                [sys.executable, "-m", "pytest", "tests/", "-q", "--tb=no", "-p", "no:cacheprovider"],
                cwd=SKILL, capture_output=True, text=True)
            killed = r.returncode != 0
            tail = r.stdout.strip().splitlines()[-1] if r.stdout.strip() else "?"
            print(f"{'✅ 殺死' if killed else '🚨 存活'}  {name}   [{tail}]")
            if not killed:
                survivors.append(name)
    finally:
        DOCTOR.write_text(orig)  # always restore the real source

    print(f"\n{len(MUTANTS) - len(survivors)}/{len(MUTANTS)} mutants killed" +
          (f"; SURVIVORS: {survivors}" if survivors else " — 每條防護都有測試在看守"))
    return 1 if survivors else 0


if __name__ == "__main__":
    sys.exit(main())
