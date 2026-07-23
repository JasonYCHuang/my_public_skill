#!/usr/bin/env python3
"""測試用假 rclone：把 remote 當本機路徑，實作 backup.py/check.py 用到的子指令。
行為對齊真 rclone：sync 是鏡像（會刪目的地多出的檔）。
故障注入：FAKE_RCLONE_FAIL=<cmd> 讓該子指令失敗；
FAKE_RCLONE_FAIL_MSG 自訂失敗 stderr（測 check.py 的 auth 分類）。"""

import os
import shutil
import sys
from pathlib import Path


def main() -> int:
    cmd = sys.argv[1]
    if os.environ.get("FAKE_RCLONE_FAIL") == cmd:
        print(os.environ.get("FAKE_RCLONE_FAIL_MSG", f"fake rclone: forced {cmd} failure"),
              file=sys.stderr)
        return 1
    args = [a for a in sys.argv[2:] if not a.startswith("--")]

    if cmd == "listremotes":
        print("icloud:")
        return 0

    if cmd == "lsd":
        d = Path(args[0].rstrip(":"))  # 測試裡 "icloud:" 不存在 → 視為根，直接成功
        if args[0].endswith(":") or d.is_dir():
            return 0
        print("directory not found", file=sys.stderr)
        return 3

    if cmd == "sync":
        src, dst = Path(args[0]), Path(args[1])
        dst.mkdir(parents=True, exist_ok=True)
        for p in sorted(dst.rglob("*"), reverse=True):  # 先深後淺，安全刪
            rel = p.relative_to(dst)
            if not (src / rel).exists():
                shutil.rmtree(p) if p.is_dir() else p.unlink()
        for p in src.rglob("*"):
            rel = p.relative_to(src)
            if p.is_dir():
                (dst / rel).mkdir(parents=True, exist_ok=True)
            else:
                (dst / rel).parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(p, dst / rel)
        return 0

    if cmd == "copyto":
        src, dst = Path(args[0]), Path(args[1])
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
        return 0

    print(f"fake rclone: unknown cmd {cmd}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
