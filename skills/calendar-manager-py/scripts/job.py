#!/usr/bin/env python3
"""
Job directory, atomic writes, and the Artifact Manifest.

This is the -py skill's "剛性" core: the pieces of the workflow that used to
be natural-language instructions in SKILL.md ("put the html in 模板_html/",
"the png goes next to the html", "look at the file to confirm it exists")
are, here, deterministic Python that behaves the same no matter which model
drives it.

Three jobs live in this module:

1. **Job directory management.** One job = one rendered month = one output
   folder, with a `.tmp/` scratch area inside it. build.py creates it; nothing
   writes real calendar data anywhere else.

2. **Atomic writes.** Every output file is written to a temp file in the same
   directory and then `os.replace`d into place. A reader (or a re-run) never
   sees a half-written html or a truncated xlsx: the path either holds the
   old file or the complete new one, never a partial.

3. **The Artifact Manifest** (`manifest.json`). The single record of what the
   job actually produced: for each artifact, a stable **artifact id**, its
   real path, byte size, sha256, and whether verification passed. This is the
   answer to "the agent claimed it made a file that isn't there" — downstream
   steps refer to outputs by artifact id and read their real state from here,
   instead of trusting a path a model typed from memory.

Library use is via `Manifest`; the CLI (`list` / `path` / `verify`) lets the
agent or a human query a finished job.

    python3 job.py list   <job_dir>              # table of artifacts + state
    python3 job.py path    <job_dir> <artifact>   # print one artifact's real path
    python3 job.py verify  <job_dir>              # re-hash every artifact vs manifest
"""
import argparse
import hashlib
import json
import os
import re
import sys
import tempfile
from datetime import datetime

MANIFEST_NAME = "manifest.json"
MANIFEST_SCHEMA = "calendar-manager-py/manifest@1"
TMP_DIRNAME = ".tmp"


# ---------------------------------------------------------------------------
# time / naming
# ---------------------------------------------------------------------------

def now_iso():
    """Local, timezone-aware ISO 8601 — so a manifest read months later still
    says which wall-clock the job ran at, not a bare naive string."""
    return datetime.now().astimezone().isoformat(timespec="seconds")


def now_stamp():
    return datetime.now().strftime("%Y%m%d-%H%M%S")


_SLUG_STRIP = re.compile(r'[\\/:*?"<>|\s]+')


def slugify(name, fallback="calendar"):
    """A filesystem-safe token for a job id. CJK is kept (it's a valid folder
    name on every platform we target); only the characters that actually break
    a path — slashes, colons, wildcards, whitespace — are collapsed to '-'."""
    s = _SLUG_STRIP.sub("-", (name or "").strip()).strip("-")
    return s or fallback


# ---------------------------------------------------------------------------
# hashing
# ---------------------------------------------------------------------------

def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


# ---------------------------------------------------------------------------
# atomic writes / moves
# ---------------------------------------------------------------------------

def _atomic_replace_from_tmp(tmp_path, dst):
    """fsync the temp file, then os.replace it onto dst. os.replace is atomic
    within a filesystem, which is guaranteed here because the temp file is
    created in dst's own directory."""
    with open(tmp_path, "rb") as f:
        os.fsync(f.fileno())
    os.replace(tmp_path, dst)


def atomic_write_bytes(dst, data):
    os.makedirs(os.path.dirname(os.path.abspath(dst)), exist_ok=True)
    d = os.path.dirname(os.path.abspath(dst))
    fd, tmp = tempfile.mkstemp(dir=d, prefix=".tmp-", suffix=".part")
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
        _atomic_replace_from_tmp(tmp, dst)
    except BaseException:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise


def atomic_write_text(dst, text, encoding="utf-8"):
    atomic_write_bytes(dst, text.encode(encoding))


def atomic_move(src, dst):
    """Move a fully-written file (e.g. an xlsx openpyxl saved, or a png node
    produced) into its final home. src must already sit on dst's filesystem —
    build.py always stages in the job's own `.tmp/`, so it does."""
    os.makedirs(os.path.dirname(os.path.abspath(dst)), exist_ok=True)
    os.replace(src, dst)


# ---------------------------------------------------------------------------
# manifest
# ---------------------------------------------------------------------------

class Manifest:
    """The job's record of produced artifacts, keyed by stable artifact id."""

    def __init__(self, job_dir, data):
        self.job_dir = os.path.abspath(job_dir)
        self.data = data

    @property
    def path(self):
        return os.path.join(self.job_dir, MANIFEST_NAME)

    # -- construction -------------------------------------------------------

    @classmethod
    def create(cls, job_dir, subject, source=None):
        """subject: what this job renders — {"title", "year", "month",
        "calendar"} for a calendar job. Kept as a free dict so the manifest
        stays honest about what it was built from."""
        job_dir = os.path.abspath(job_dir)
        os.makedirs(os.path.join(job_dir, TMP_DIRNAME), exist_ok=True)
        data = {
            "schema": MANIFEST_SCHEMA,
            "job_id": f"{slugify(subject.get('title'))}-{now_stamp()}",
            "created_at": now_iso(),
            "job_dir": job_dir,
            "subject": dict(subject, source=source or ""),
            "artifacts": {},
        }
        return cls(job_dir, data)

    @classmethod
    def load(cls, job_dir):
        job_dir = os.path.abspath(job_dir)
        p = os.path.join(job_dir, MANIFEST_NAME)
        if not os.path.exists(p):
            raise FileNotFoundError(f"找不到 manifest：{p}（此資料夾還沒有跑過 build.py？）")
        with open(p, encoding="utf-8") as f:
            return cls(job_dir, json.load(f))

    # -- mutation -----------------------------------------------------------

    def record(self, artifact_id, path, kind, verify=None):
        """Register (or replace) an artifact. `path` must already exist —
        record hashes it now, so a manifest entry can never point at a file
        that was announced but never written."""
        abspath = os.path.abspath(path)
        entry = {
            "artifact_id": artifact_id,
            "kind": kind,
            "filename": os.path.basename(abspath),
            "path": abspath,
            "rel_path": os.path.relpath(abspath, self.job_dir),
            "bytes": os.path.getsize(abspath),
            "sha256": sha256_file(abspath),
            "created_at": now_iso(),
        }
        if verify is not None:
            entry["verified"] = bool(verify.get("ok"))
            entry["verify"] = verify
        self.data["artifacts"][artifact_id] = entry
        return entry

    def save(self):
        atomic_write_text(
            self.path,
            json.dumps(self.data, ensure_ascii=False, indent=2) + "\n",
        )
        return self.path

    # -- query --------------------------------------------------------------

    def get(self, artifact_id):
        try:
            return self.data["artifacts"][artifact_id]
        except KeyError:
            raise KeyError(
                f"manifest 沒有 artifact id '{artifact_id}'。"
                f"現有：{', '.join(self.data['artifacts']) or '(空)'}"
            )

    def resolve(self, artifact_id):
        """Artifact id -> real absolute path. This is the call that replaces
        'free path' referencing: never reconstruct an output path from the
        name and a folder convention, ask the manifest."""
        return self.get(artifact_id)["path"]

    def reverify_hashes(self):
        """Re-hash every recorded artifact and compare to what was stored.
        Catches a file deleted, truncated, or swapped after the job ran —
        the concrete way to check 'is what I promised still on disk?'."""
        results = {}
        for aid, entry in self.data["artifacts"].items():
            path = entry["path"]
            if not os.path.exists(path):
                results[aid] = {"ok": False, "reason": "檔案已不存在"}
                continue
            actual = sha256_file(path)
            ok = actual == entry.get("sha256")
            results[aid] = {
                "ok": ok,
                "reason": "" if ok else "sha256 與 manifest 不符（檔案被改動或覆寫）",
            }
        return results


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _cmd_list(args):
    m = Manifest.load(args.job_dir)
    arts = m.data["artifacts"]
    print(f"job_id : {m.data.get('job_id')}")
    print(f"created: {m.data.get('created_at')}")
    print(f"subject: {m.data.get('subject', {}).get('title', '')}")
    if not arts:
        print("(manifest 中沒有任何 artifact)")
        return 0
    print(f"\n{'artifact_id':<14} {'kind':<6} {'ok':<4} {'bytes':>9}  filename")
    for aid, e in arts.items():
        ok = "✓" if e.get("verified", True) else "✗"
        print(f"{aid:<14} {e['kind']:<6} {ok:<4} {e['bytes']:>9}  {e['filename']}")
    return 0


def _cmd_path(args):
    m = Manifest.load(args.job_dir)
    print(m.resolve(args.artifact_id))
    return 0


def _media_order(aid):
    """month first, then weeks by number — the order to send them in chat."""
    if aid.startswith("month"):
        return (0, 0)
    mm = re.match(r"week-(\d+)-", aid)
    return (1, int(mm.group(1)) if mm else 99)


def _cmd_media(args):
    """Print ready-to-paste MEDIA: lines for every *verified* PNG — the
    mechanical half of "send the image inline, month first". Composing the
    surrounding message (and the retry ladder if a send doesn't render) stays
    with the model."""
    m = Manifest.load(args.job_dir)
    pngs = [(aid, e) for aid, e in m.data["artifacts"].items()
            if e.get("kind") == "png" and e.get("verified")]
    if not pngs:
        print("manifest 中沒有已通過驗證的 PNG（先用 --formats html,png 重跑 build.py？）",
              file=sys.stderr)
        return 1
    for aid, e in sorted(pngs, key=lambda t: _media_order(t[0])):
        print(f"MEDIA:{e['path']}")
    return 0


def _cmd_verify(args):
    m = Manifest.load(args.job_dir)
    results = m.reverify_hashes()
    failed = 0
    for aid, r in results.items():
        mark = "✓" if r["ok"] else "✗"
        line = f"{mark} {aid}"
        if not r["ok"]:
            line += f" — {r['reason']}"
            failed += 1
        print(line)
    if failed:
        print(f"\n{failed} 個 artifact 與 manifest 不符。", file=sys.stderr)
        return 1
    print("\n所有 artifact 與 manifest 一致。")
    return 0


def main():
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("list", help="列出 job 的所有 artifact")
    p.add_argument("job_dir")
    p.set_defaults(func=_cmd_list)

    p = sub.add_parser("path", help="印出某個 artifact id 的真實路徑")
    p.add_argument("job_dir")
    p.add_argument("artifact_id")
    p.set_defaults(func=_cmd_path)

    p = sub.add_parser("verify", help="重新雜湊所有 artifact，比對 manifest")
    p.add_argument("job_dir")
    p.set_defaults(func=_cmd_verify)

    p = sub.add_parser("media", help="印出已驗證 PNG 的 MEDIA: 行（月曆在前）")
    p.add_argument("job_dir")
    p.set_defaults(func=_cmd_media)

    args = ap.parse_args()
    sys.exit(args.func(args))


if __name__ == "__main__":
    main()
