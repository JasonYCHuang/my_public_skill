"""backup.py 的自動測試：鏡像、刪除傳播、每日快照冪等、修剪、報告上傳、鎖。
全走 tmp 目錄＋假 rclone（tests/fake_rclone.py），不需網路、不需真 rclone。"""

import json
import os
import stat
import subprocess
import sys
import tarfile
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).parent.parent / "scripts"
BACKUP = SCRIPTS / "backup.py"
FAKE_RCLONE = Path(__file__).parent / "fake_rclone.py"


@pytest.fixture(scope="session", autouse=True)
def _executable_fake_rclone():
    FAKE_RCLONE.chmod(FAKE_RCLONE.stat().st_mode | stat.S_IXUSR)


def run_backup(source: Path, remote: Path, state: Path, today: str, keep_days: int = 14):
    return subprocess.run(
        [sys.executable, str(BACKUP), "--source", str(source), "--remote", str(remote),
         "--state-dir", str(state), "--rclone", str(FAKE_RCLONE),
         "--today", today, "--keep-days", str(keep_days)],
        capture_output=True, text=True,
    )


def make_source(tmp_path: Path) -> Path:
    src = tmp_path / "mein-agent-storage"
    (src / "sub").mkdir(parents=True)
    (src / "a.txt").write_text("aaa")
    (src / "sub" / "b.txt").write_text("bbb")
    return src


def test_mirror_snapshot_and_report_upload(tmp_path):
    src, remote, state = make_source(tmp_path), tmp_path / "remote", tmp_path / "state"
    proc = run_backup(src, remote, state, "20260722")
    assert proc.returncode == 0, proc.stderr
    assert (remote / "current" / "a.txt").read_text() == "aaa"
    assert (remote / "current" / "sub" / "b.txt").read_text() == "bbb"
    snap = remote / "snapshots" / "20260722.tar.gz"
    assert snap.exists()
    with tarfile.open(snap) as tar:
        assert any(n.endswith("a.txt") for n in tar.getnames())
    # 報告：本機 state 一份、remote 一份
    local = json.loads((state / "backup-report.json").read_text())
    assert local["ok"] and local["snapshot"]["status"] == "created"
    assert (remote / "backup-report.json").exists()


def test_delete_propagates_but_snapshot_keeps(tmp_path):
    src, remote, state = make_source(tmp_path), tmp_path / "remote", tmp_path / "state"
    run_backup(src, remote, state, "20260722")
    (src / "a.txt").unlink()
    proc = run_backup(src, remote, state, "20260722")
    assert proc.returncode == 0, proc.stderr
    assert not (remote / "current" / "a.txt").exists()  # 鏡像跟著刪
    with tarfile.open(remote / "snapshots" / "20260722.tar.gz") as tar:
        assert any(n.endswith("a.txt") for n in tar.getnames())  # 快照仍留著


def test_snapshot_idempotent_per_day(tmp_path):
    src, remote, state = make_source(tmp_path), tmp_path / "remote", tmp_path / "state"
    run_backup(src, remote, state, "20260722")
    proc = run_backup(src, remote, state, "20260722")
    assert proc.returncode == 0
    report = json.loads((state / "backup-report.json").read_text())
    assert report["snapshot"]["status"] == "exists"
    assert len(list((remote / "snapshots").glob("*.tar.gz"))) == 1


def test_prune_old_snapshots(tmp_path):
    src, remote, state = make_source(tmp_path), tmp_path / "remote", tmp_path / "state"
    snaps = remote / "snapshots"
    snaps.mkdir(parents=True)
    (snaps / "20260101.tar.gz").write_bytes(b"old")   # 超過 14 天 → 刪
    (snaps / "20260715.tar.gz").write_bytes(b"keep")  # 14 天內 → 留
    (snaps / "not-a-date.tar.gz").write_bytes(b"x")   # 非本工具命名 → 不動
    proc = run_backup(src, remote, state, "20260722")
    assert proc.returncode == 0, proc.stderr
    assert not (snaps / "20260101.tar.gz").exists()
    assert (snaps / "20260715.tar.gz").exists()
    assert (snaps / "not-a-date.tar.gz").exists()
    report = json.loads((state / "backup-report.json").read_text())
    assert report["pruned"] == ["20260101.tar.gz"]


def test_missing_source_fails(tmp_path):
    proc = run_backup(tmp_path / "nope", tmp_path / "remote", tmp_path / "state", "20260722")
    assert proc.returncode == 1
    assert "來源不存在" in proc.stderr


def test_unconfigured_remote_fails(tmp_path):
    """remote 含 ':' 時要查 listremotes；假 rclone 只認 gdrive:，其他名稱必須被擋。"""
    src = make_source(tmp_path)
    proc = subprocess.run(
        [sys.executable, str(BACKUP), "--source", str(src), "--remote", "nosuch:x",
         "--state-dir", str(tmp_path / "state"), "--rclone", str(FAKE_RCLONE),
         "--today", "20260722"],
        capture_output=True, text=True,
    )
    assert proc.returncode == 1
    assert "未設定" in proc.stderr


def test_lock_blocks_concurrent_run(tmp_path):
    src, state = make_source(tmp_path), tmp_path / "state"
    (state / ".lock").mkdir(parents=True)  # 模擬另一份正在跑（mtime 是現在，非 stale）
    proc = run_backup(src, tmp_path / "remote", state, "20260722")
    assert proc.returncode == 1
    assert "正在執行" in proc.stderr


def test_systemd_units_content():
    """build_units 是純函式：驗排程時刻（00:45 系列）、Persistent、ExecStart。"""
    import importlib.util
    spec = importlib.util.spec_from_file_location("install_systemd", SCRIPTS / "install_systemd.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    service, timer = mod.build_units(
        ["/usr/bin/python3", "/x/backup.py", "--remote", "gdrive:Backups/x"],
        mod.parse_times("0:45,6:45,12:45,18:45"),
    )
    assert "ExecStart=/usr/bin/python3 /x/backup.py --remote gdrive:Backups/x" in service
    for line in ("OnCalendar=*-*-* 00:45:00", "OnCalendar=*-*-* 06:45:00",
                 "OnCalendar=*-*-* 12:45:00", "OnCalendar=*-*-* 18:45:00"):
        assert line in timer
    assert "Persistent=true" in timer
