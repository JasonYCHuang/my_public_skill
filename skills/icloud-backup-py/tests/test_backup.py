"""backup.py 的自動測試：鏡像、刪除傳播、每日快照冪等、修剪、報告。全部走 tmp 目錄，不碰 iCloud。"""

import json
import subprocess
import sys
import tarfile
from pathlib import Path

BACKUP = Path(__file__).parent.parent / "scripts" / "backup.py"


def run_backup(source: Path, dest: Path, today: str, keep_days: int = 14):
    return subprocess.run(
        [sys.executable, str(BACKUP), "--source", str(source), "--dest", str(dest),
         "--today", today, "--keep-days", str(keep_days)],
        capture_output=True, text=True,
    )


def make_source(tmp_path: Path) -> Path:
    src = tmp_path / "mein-agent-storage"
    (src / "sub").mkdir(parents=True)
    (src / "a.txt").write_text("aaa")
    (src / "sub" / "b.txt").write_text("bbb")
    return src


def test_mirror_and_snapshot(tmp_path):
    src, dest = make_source(tmp_path), tmp_path / "dest"
    proc = run_backup(src, dest, "20260722")
    assert proc.returncode == 0, proc.stderr
    assert (dest / "current" / "a.txt").read_text() == "aaa"
    assert (dest / "current" / "sub" / "b.txt").read_text() == "bbb"
    snap = dest / "snapshots" / "20260722.tar.gz"
    assert snap.exists()
    with tarfile.open(snap) as tar:
        names = tar.getnames()
    assert any(n.endswith("a.txt") for n in names)


def test_delete_propagates_but_snapshot_keeps(tmp_path):
    src, dest = make_source(tmp_path), tmp_path / "dest"
    run_backup(src, dest, "20260722")
    (src / "a.txt").unlink()
    proc = run_backup(src, dest, "20260722")
    assert proc.returncode == 0, proc.stderr
    assert not (dest / "current" / "a.txt").exists()  # 鏡像跟著刪
    with tarfile.open(dest / "snapshots" / "20260722.tar.gz") as tar:
        assert any(n.endswith("a.txt") for n in tar.getnames())  # 快照仍留著


def test_snapshot_idempotent_per_day(tmp_path):
    src, dest = make_source(tmp_path), tmp_path / "dest"
    run_backup(src, dest, "20260722")
    proc = run_backup(src, dest, "20260722")
    assert proc.returncode == 0
    report = json.loads((dest / "backup-report.json").read_text())
    assert report["snapshot"]["status"] == "exists"
    assert len(list((dest / "snapshots").glob("*.tar.gz"))) == 1


def test_prune_old_snapshots(tmp_path):
    src, dest = make_source(tmp_path), tmp_path / "dest"
    snaps = dest / "snapshots"
    snaps.mkdir(parents=True)
    (snaps / "20260101.tar.gz").write_bytes(b"old")   # 超過 14 天 → 刪
    (snaps / "20260715.tar.gz").write_bytes(b"keep")  # 14 天內 → 留
    (snaps / "not-a-date.tar.gz").write_bytes(b"x")   # 非本工具命名 → 不動
    proc = run_backup(src, dest, "20260722")
    assert proc.returncode == 0, proc.stderr
    assert not (snaps / "20260101.tar.gz").exists()
    assert (snaps / "20260715.tar.gz").exists()
    assert (snaps / "not-a-date.tar.gz").exists()
    report = json.loads((dest / "backup-report.json").read_text())
    assert report["pruned"] == ["20260101.tar.gz"]


def test_missing_source_fails(tmp_path):
    proc = run_backup(tmp_path / "nope", tmp_path / "dest", "20260722")
    assert proc.returncode == 1
    assert "來源不存在" in proc.stderr


def test_lock_blocks_concurrent_run(tmp_path):
    src, dest = make_source(tmp_path), tmp_path / "dest"
    (dest / ".lock").mkdir(parents=True)  # 模擬另一份正在跑（mtime 是現在，非 stale）
    proc = run_backup(src, dest, "20260722")
    assert proc.returncode == 1
    assert "正在執行" in proc.stderr


def test_no_dest_on_linux_requires_flag(tmp_path, monkeypatch):
    """非 macOS 平台沒帶 --dest 必須報錯，不能默默用 iCloud 路徑。
    （backup.py 讀 sys.platform；用子行程跑不好 patch，改為單元測試 import 檢查邏輯。）"""
    import importlib.util
    spec = importlib.util.spec_from_file_location("backup", BACKUP)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    src = make_source(tmp_path)
    monkeypatch.setattr(mod.sys, "platform", "linux")
    monkeypatch.setattr(mod.sys, "argv", ["backup.py", "--source", str(src), "--today", "20260722"])
    with __import__("pytest").raises(SystemExit) as exc:
        mod.main()
    assert exc.value.code == 1


def test_systemd_units_content():
    """build_units 是純函式：驗排程時刻、Persistent、ExecStart。"""
    import importlib.util
    path = BACKUP.parent / "install_systemd.py"
    spec = importlib.util.spec_from_file_location("install_systemd", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    service, timer = mod.build_units(
        ["/usr/bin/python3", "/x/backup.py", "--dest", "/backups"],
        mod.parse_times("0:30,6:30,12:30,18:30"),
    )
    assert "ExecStart=/usr/bin/python3 /x/backup.py --dest /backups" in service
    for line in ("OnCalendar=*-*-* 00:30:00", "OnCalendar=*-*-* 06:30:00",
                 "OnCalendar=*-*-* 12:30:00", "OnCalendar=*-*-* 18:30:00"):
        assert line in timer
    assert "Persistent=true" in timer
