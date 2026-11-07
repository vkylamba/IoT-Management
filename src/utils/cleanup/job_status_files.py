import logging
import os
import time

logger = logging.getLogger('django')


def purge_expired_job_status_files(
    directory: str,
    *,
    ttl_seconds: int,
    dry_run: bool = True,
) -> int:
    if not directory or not os.path.isdir(directory):
        return 0

    now = time.time()
    removed = 0
    for entry in os.scandir(directory):
        if not entry.is_file() or not entry.name.endswith('.json'):
            continue
        try:
            age = now - entry.stat().st_mtime
        except OSError:
            logger.warning('Could not stat job status file: %s', entry.path)
            continue
        if age <= ttl_seconds:
            continue
        removed += 1
        if not dry_run:
            try:
                os.remove(entry.path)
            except OSError:
                logger.warning('Failed to remove expired job status file: %s', entry.path)
    return removed
