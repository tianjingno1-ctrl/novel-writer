"""文件备份等共用工具。"""

from __future__ import annotations

import shutil
from datetime import datetime
from pathlib import Path

BACKUP_KEEP = 10


def backup_file(path: Path, backups_dir: Path) -> None:
    if not path.exists() or path.stat().st_size <= 0:
        return
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    backups_dir.mkdir(parents=True, exist_ok=True)
    dest = backups_dir / f"{path.stem}_{ts}{path.suffix}"
    shutil.copy2(path, dest)
    old = sorted(backups_dir.glob(f"{path.stem}_*{path.suffix}"))
    for f in old[:-BACKUP_KEEP]:
        f.unlink(missing_ok=True)
