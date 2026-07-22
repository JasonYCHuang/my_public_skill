#!/usr/bin/env python3
"""測試用假 rclone：把 remote 當本機路徑，實作 backup.py 用到的五個子指令。
行為對齊真 rclone：sync 會刪目的地多出的檔；lsf 對不存在的目錄以非零退出。"""

import os
import shutil
import sys
from pathlib import Path


def main() -> int:
    cmd = sys.argv[1]
    args = [a for a in sys.argv[2:] if not a.startswith("--")]

    if cmd == "listremotes":
        print("gdrive:")
        return 0

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

    if cmd == "lsf":
        d = Path(args[0])
        if not d.is_dir():
            print("directory not found", file=sys.stderr)
            return 3
        for n in sorted(os.listdir(d)):
            print(n + ("/" if (d / n).is_dir() else ""))
        return 0

    if cmd == "copyto":
        src, dst = Path(args[0]), Path(args[1])
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
        return 0

    if cmd == "deletefile":
        Path(args[0]).unlink()
        return 0

    print(f"fake_rclone: unknown command {cmd}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
