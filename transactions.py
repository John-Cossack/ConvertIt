"""Publish complete multi-file conversions, with rollback on failure."""
from localization import localize
from pathlib import Path
import os


def publish(pairs, overwrite=False):
    pairs = [(Path(a), Path(b)) for a, b in pairs]
    for staged, destination in pairs:
        if not staged.is_file() or not staged.stat().st_size:
            raise ValueError(localize('Конвертер не створив повний результат.'))
        if destination.exists() and (not overwrite or destination.is_dir()):
            raise FileExistsError(str(destination))
    backups, created = [], []
    try:
        for index, (staged, destination) in enumerate(pairs):
            if overwrite and destination.exists():
                backup = staged.parent / ('backup-'+str(index))
                destination.rename(backup)
                backups.append((backup, destination))
            os.link(staged, destination)
            created.append(destination)
    except Exception:
        for path in reversed(created):
            path.unlink()
        for backup, destination in reversed(backups):
            backup.rename(destination)
        raise
    return [b for a, b in pairs]
