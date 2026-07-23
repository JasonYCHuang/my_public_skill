"""backup.py 的自動測試：鏡像、刪除傳播、每日快照冪等、修剪、報告、rclone 上傳腿。
全部走 tmp 目錄 + 假 rclone，不碰 iCloud。"""

import json
import os
import subprocess
import sys
import tarfile
from pathlib import Path

BACKUP = Path(__file__).parent.parent / "scripts" / "backup.py"
FAKE_RCLONE = Path(__file__).parent / "fake_rclone.py"


def run_backup(source: Path, dest: Path, today: str, keep_days: int = 14,
               rclone_remote: str | None = None, env_extra: dict | None = None):
    cmd = [sys.executable, str(BACKUP), "--source", str(source), "--dest", str(dest),
           "--today", today, "--keep-days", str(keep_days)]
    if rclone_remote:
        cmd += ["--rclone-remote", rclone_remote, "--rclone", str(FAKE_RCLONE)]
    env = {**os.environ, **(env_extra or {})}
    return subprocess.run(cmd, capture_output=True, text=True, env=env)


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


def test_rclone_upload_mirrors_current_and_snapshots(tmp_path):
    """--rclone-remote：current 與 snapshots 都同步上遠端，report 也 copyto 一份。"""
    src, dest = make_source(tmp_path), tmp_path / "dest"
    remote = tmp_path / "remote"  # 不含 ":" → 跳過 listremotes 檢查
    proc = run_backup(src, dest, "20260722", rclone_remote=str(remote))
    assert proc.returncode == 0, proc.stderr
    assert (remote / "current" / "a.txt").read_text() == "aaa"
    assert (remote / "snapshots" / "20260722.tar.gz").exists()
    assert (remote / "backup-report.json").exists()
    report = json.loads((dest / "backup-report.json").read_text())
    assert report["ok"] is True
    assert report["rclone"]["sync_exit"] == {"current": 0, "snapshots": 0}


def test_rclone_prune_propagates_to_remote(tmp_path):
    """本地修剪掉的舊快照，sync 後遠端也要消失（sync 是鏡像）。"""
    src, dest = make_source(tmp_path), tmp_path / "dest"
    remote = tmp_path / "remote"
    old = remote / "snapshots" / "20260101.tar.gz"
    old.parent.mkdir(parents=True)
    old.write_bytes(b"old-remote-only")
    proc = run_backup(src, dest, "20260722", rclone_remote=str(remote))
    assert proc.returncode == 0, proc.stderr
    assert not old.exists()  # 本地沒有 → 遠端跟著刪
    assert (remote / "snapshots" / "20260722.tar.gz").exists()


def test_rclone_upload_failure_reports_and_exits_nonzero(tmp_path):
    """上傳失敗：本地備份仍完整、report ok:false、非零退出讓 systemd 看見。"""
    src, dest = make_source(tmp_path), tmp_path / "dest"
    remote = tmp_path / "remote"
    proc = run_backup(src, dest, "20260722", rclone_remote=str(remote),
                      env_extra={"FAKE_RCLONE_FAIL": "sync"})
    assert proc.returncode == 1
    assert "上傳失敗" in proc.stderr
    assert (dest / "current" / "a.txt").exists()  # 本地腿不受影響
    report = json.loads((dest / "backup-report.json").read_text())
    assert report["ok"] is False
    assert not (remote / "backup-report.json").exists()  # 失敗不上傳 report


def test_rclone_unconfigured_remote_dies_early(tmp_path):
    """remote 含 ':' 且未設定 → 開跑前就報錯，不動任何檔案。"""
    src, dest = make_source(tmp_path), tmp_path / "dest"
    proc = run_backup(src, dest, "20260722", rclone_remote="gdrive:whatever")
    assert proc.returncode == 1  # 假 rclone 的 listremotes 只有 icloud:
    assert "未設定" in proc.stderr
    assert not dest.exists()


def test_no_rclone_flag_keeps_report_shape(tmp_path):
    """不帶 --rclone-remote：report 沒有 rclone 欄位，行為與舊版完全相同。"""
    src, dest = make_source(tmp_path), tmp_path / "dest"
    proc = run_backup(src, dest, "20260722")
    assert proc.returncode == 0, proc.stderr
    report = json.loads((dest / "backup-report.json").read_text())
    assert "rclone" not in report and report["ok"] is True


def test_stale_lock_auto_clears(tmp_path):
    """docstring 承諾：鎖 mtime 超過 2 小時視為 stale 自動清——鎖住這個語意。"""
    src, dest = make_source(tmp_path), tmp_path / "dest"
    lock = dest / ".lock"
    lock.mkdir(parents=True)
    stale = (os.stat(lock).st_mtime - 3 * 60 * 60)
    os.utime(lock, (stale, stale))
    proc = run_backup(src, dest, "20260722")
    assert proc.returncode == 0, proc.stderr  # stale 鎖不擋路
    assert (dest / "current" / "a.txt").exists()


def test_rclone_report_copyto_failure_is_best_effort(tmp_path):
    """report 上傳是盡力而為：copyto 失敗不影響結果（exit 0、ok:true）。"""
    src, dest = make_source(tmp_path), tmp_path / "dest"
    remote = tmp_path / "remote"
    proc = run_backup(src, dest, "20260722", rclone_remote=str(remote),
                      env_extra={"FAKE_RCLONE_FAIL": "copyto"})
    assert proc.returncode == 0, proc.stderr
    report = json.loads((dest / "backup-report.json").read_text())
    assert report["ok"] is True
    assert (remote / "current" / "a.txt").exists()  # sync 腿不受影響
    assert not (remote / "backup-report.json").exists()  # 只有 report 沒上去


# ---------- check.py：健康檢查 verdict 機器 ----------

CHECK = Path(__file__).parent.parent / "scripts" / "check.py"


def run_check(dest: Path, rclone_remote: str | None = None,
              now: str | None = None, env_extra: dict | None = None):
    cmd = [sys.executable, str(CHECK), "--dest", str(dest), "--json"]
    if rclone_remote:
        cmd += ["--rclone-remote", rclone_remote, "--rclone", str(FAKE_RCLONE)]
    if now:
        cmd += ["--now", now]
    env = {**os.environ, **(env_extra or {})}
    proc = subprocess.run(cmd, capture_output=True, text=True, env=env)
    return proc, (json.loads(proc.stdout) if proc.stdout.strip().startswith("{") else None)


def test_check_ok_after_fresh_backup(tmp_path):
    src, dest = make_source(tmp_path), tmp_path / "dest"
    run_backup(src, dest, "20260722")
    proc, out = run_check(dest)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert out["verdict"] == "OK" and out["ok"] is True and out["remedy"] is None


def test_check_no_report(tmp_path):
    proc, out = run_check(tmp_path / "empty-dest")
    assert proc.returncode == 1
    assert out["verdict"] == "NO_REPORT" and "run-now" in out["remedy"]


def test_check_stale_report(tmp_path):
    src, dest = make_source(tmp_path), tmp_path / "dest"
    run_backup(src, dest, "20260722")
    report = json.loads((dest / "backup-report.json").read_text())
    # 用 --now 把「現在」推到 finished_at 的 8 小時後（上限 7h）
    finished = report["finished_at"]
    import datetime
    late = (datetime.datetime.fromisoformat(finished)
            + datetime.timedelta(hours=8)).isoformat()
    proc, out = run_check(dest, now=late)
    assert proc.returncode == 1
    assert out["verdict"] == "STALE" and "linger" in out["remedy"]


def test_check_backup_failed_report(tmp_path):
    src, dest = make_source(tmp_path), tmp_path / "dest"
    run_backup(src, dest, "20260722")
    report = json.loads((dest / "backup-report.json").read_text())
    report["ok"] = False
    (dest / "backup-report.json").write_text(json.dumps(report))
    proc, out = run_check(dest)
    assert out["verdict"] == "BACKUP_FAILED"


def test_check_auth_expired_classified(tmp_path):
    """lsd 回 401 → AUTH_EXPIRED，remedy 給出 reconnect 指令。"""
    src, dest = make_source(tmp_path), tmp_path / "dest"
    run_backup(src, dest, "20260722")
    proc, out = run_check(dest, rclone_remote="icloud:Backups/x",
                          env_extra={"FAKE_RCLONE_FAIL": "lsd",
                                     "FAKE_RCLONE_FAIL_MSG": "401 Unauthorized: token expired"})
    assert proc.returncode == 1
    assert out["verdict"] == "AUTH_EXPIRED"
    assert "rclone config reconnect icloud:" in out["remedy"]


def test_check_remote_not_configured(tmp_path):
    src, dest = make_source(tmp_path), tmp_path / "dest"
    run_backup(src, dest, "20260722")
    proc, out = run_check(dest, rclone_remote="gdrive:x")  # 假 rclone 只有 icloud:
    assert out["verdict"] == "NOT_CONFIGURED"


def test_check_remote_error_non_auth(tmp_path):
    src, dest = make_source(tmp_path), tmp_path / "dest"
    run_backup(src, dest, "20260722")
    proc, out = run_check(dest, rclone_remote="icloud:Backups/x",
                          env_extra={"FAKE_RCLONE_FAIL": "lsd",
                                     "FAKE_RCLONE_FAIL_MSG": "connection reset by peer"})
    assert out["verdict"] == "REMOTE_ERROR"


def test_check_local_error_when_staging_gone(tmp_path):
    """report 正常但 current/ 被清空 → LOCAL_ERROR。"""
    src, dest = make_source(tmp_path), tmp_path / "dest"
    run_backup(src, dest, "20260722")
    import shutil
    shutil.rmtree(dest / "current")
    proc, out = run_check(dest)
    assert proc.returncode == 1
    assert out["verdict"] == "LOCAL_ERROR"


def test_check_corrupted_report_is_backup_failed(tmp_path):
    """report 不是合法 JSON → BACKUP_FAILED，不 crash。"""
    dest = tmp_path / "dest"
    dest.mkdir()
    (dest / "backup-report.json").write_text("{not json")
    proc, out = run_check(dest)
    assert proc.returncode == 1
    assert out["verdict"] == "BACKUP_FAILED"


def test_install_prog_passthrough_rclone_remote():
    """install 組出的 ExecStart 必須帶 --rclone-remote（新功能的 passthrough 回歸鎖）。"""
    import argparse
    import importlib.util
    path = BACKUP.parent / "install_systemd.py"
    spec = importlib.util.spec_from_file_location("install_systemd", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    args = argparse.Namespace(dest="/backups", source=None, keep_days=None,
                              rclone_remote="icloud:Backups/x")
    prog = mod.build_prog(args)
    assert prog[-2:] == ["--rclone-remote", "icloud:Backups/x"]
    args.rclone_remote = None
    assert "--rclone-remote" not in mod.build_prog(args)


def test_check_remote_ok_end_to_end(tmp_path):
    src, dest = make_source(tmp_path), tmp_path / "dest"
    run_backup(src, dest, "20260722")
    proc, out = run_check(dest, rclone_remote="icloud:Backups/x")
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert out["verdict"] == "OK"
    assert [c["name"] for c in out["checks"]] == ["report", "staging", "remote"]


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
