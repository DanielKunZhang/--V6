#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path
import shutil


ROOT = Path(__file__).resolve().parents[2]
ARCHIVE_ROOT = ROOT / "archive" / "20260520_dirty_worktree_cleanup"
DEST_ROOT = ARCHIVE_ROOT / "untracked_files"
MANIFEST = ARCHIVE_ROOT / "untracked_files_manifest.txt"


def main() -> None:
    moved = 0
    skipped: list[str] = []
    for line in MANIFEST.read_text(encoding="utf-8").splitlines():
        rel_text = line.strip()
        if not rel_text or rel_text.startswith("archive/20260520_dirty_worktree_cleanup/"):
            continue
        rel = Path(rel_text)
        src = ROOT / rel
        dst = DEST_ROOT / rel
        if not src.exists() or dst.exists():
            skipped.append(rel_text)
            continue
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(src), str(dst))
        moved += 1
    print(f"moved={moved} skipped={len(skipped)}")
    if skipped:
        (ARCHIVE_ROOT / "move_untracked_skipped.txt").write_text("\n".join(skipped) + "\n", encoding="utf-8")
        print(f"skipped_manifest={ARCHIVE_ROOT / 'move_untracked_skipped.txt'}")


if __name__ == "__main__":
    main()
