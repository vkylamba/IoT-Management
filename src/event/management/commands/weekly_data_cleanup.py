import os
import tempfile
from datetime import timedelta

from api.monthly_report_jobs import (
    MONTHLY_REPORT_JOB_STATUS_DIR,
    MONTHLY_REPORT_JOB_STATUS_TTL_SECONDS,
)
from django.conf import settings
from django.core.management.base import BaseCommand
from django.utils import timezone
from event.models import Action, DeviceEvent, EventHistory
from iot_server.admin_utils import get_mongo_db
from utils.cleanup.job_status_files import purge_expired_job_status_files
from utils.cleanup.mongo_bulk_delete import aggregation_orphan_ids, delete_many_in_chunks

REPROCESS_JOB_STATUS_DIR = os.path.join(
    tempfile.gettempdir(),
    'iot-management-reprocess-jobs',
)
REPROCESS_JOB_STATUS_TTL_SECONDS = 6 * 60 * 60


class Command(BaseCommand):
    help = (
        'Weekly cleanup: stale/orphan event history and expired report job status files. '
        'Does not modify RawData or AssetStatus.'
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--apply',
            action='store_true',
            help='Delete data. Default is dry-run (counts only).',
        )
        parser.add_argument(
            '--history-days',
            type=int,
            default=7,
            help='Delete EventHistory rows older than this many days (default: 7).',
        )
        parser.add_argument(
            '--chunk-size',
            type=int,
            default=2000,
            help='Mongo bulk delete chunk size (default: 2000).',
        )
        parser.add_argument(
            '--skip-job-files',
            action='store_true',
            help='Skip cleaning expired monthly/reprocess job status JSON files.',
        )
        parser.add_argument(
            '--include-dangling-actions',
            action='store_true',
            help='Also delete Action rows whose device_event no longer exists.',
        )

    def handle(self, *args, **options):
        dry_run = not bool(options.get('apply'))
        retention_days = max(1, int(options.get('history_days') or 7))
        chunk_size = max(1, int(options.get('chunk_size') or 2000))

        mode = 'DRY-RUN' if dry_run else 'APPLY'
        self.stdout.write(self.style.WARNING(f'Weekly data cleanup — {mode}'))

        if settings.DATABASES['default'].get('ENGINE') != 'djongo':
            self.stderr.write(self.style.ERROR('This command requires the Djongo/MongoDB backend.'))
            return

        client, db = get_mongo_db()
        try:
            stats = self._cleanup_event_history(db, retention_days, chunk_size, dry_run)
            stats.update(
                self._cleanup_orphan_actions(db, chunk_size, dry_run, options.get('include_dangling_actions'))
            )
        finally:
            client.close()

        if not options.get('skip_job_files'):
            stats_files = self._cleanup_job_status_files(dry_run)
            stats.update(stats_files)

        self.stdout.write('')
        self.stdout.write(self.style.SUCCESS('Summary'))
        for key, value in sorted(stats.items()):
            self.stdout.write(f'  {key}: {value}')

        if dry_run:
            self.stdout.write(self.style.WARNING('No changes applied. Re-run with --apply to execute deletes.'))

    def _history_collection(self, db):
        table = EventHistory._meta.db_table
        return db[table], table

    def _cleanup_event_history(self, db, retention_days, chunk_size, dry_run):
        collection, table = self._history_collection(db)
        cutoff = timezone.now() - timedelta(days=retention_days)
        stale_filter = {'trigger_time': {'$lt': cutoff}}

        stale_count = collection.count_documents(stale_filter)
        stale_deleted = 0
        if stale_count and not dry_run:
            result = collection.delete_many(stale_filter)
            stale_deleted = int(result.deleted_count)
        elif stale_count:
            stale_deleted = stale_count

        self.stdout.write(
            f'EventHistory ({table}): stale (> {retention_days}d) count={stale_count}, '
            f'{"would delete" if dry_run else "deleted"}={stale_deleted or stale_count}'
        )

        device_event_table = DeviceEvent._meta.db_table
        orphan_event_ids = list(
            aggregation_orphan_ids(
                collection,
                parent_collection=device_event_table,
                foreign_key_field='device_event_id',
            )
        )
        orphan_event_deleted = delete_many_in_chunks(
            collection,
            orphan_event_ids,
            chunk_size=chunk_size,
            dry_run=dry_run,
        )
        self.stdout.write(
            f'EventHistory orphan device_event: count={len(orphan_event_ids)}, '
            f'{"would delete" if dry_run else "deleted"}={orphan_event_deleted}'
        )

        action_table = Action._meta.db_table
        orphan_action_ids = list(
            aggregation_orphan_ids(
                collection,
                parent_collection=action_table,
                foreign_key_field='action_id',
                extra_match={'action_id': {'$ne': None}},
            )
        )
        orphan_action_deleted = delete_many_in_chunks(
            collection,
            orphan_action_ids,
            chunk_size=chunk_size,
            dry_run=dry_run,
        )
        self.stdout.write(
            f'EventHistory orphan action: count={len(orphan_action_ids)}, '
            f'{"would delete" if dry_run else "deleted"}={orphan_action_deleted}'
        )

        return {
            'event_history_stale': stale_deleted or stale_count,
            'event_history_orphan_device_event': orphan_event_deleted,
            'event_history_orphan_action': orphan_action_deleted,
        }

    def _cleanup_orphan_actions(self, db, chunk_size, dry_run, include_dangling_actions):
        if not include_dangling_actions:
            self.stdout.write('Skipping dangling Action cleanup (pass --include-dangling-actions to enable).')
            return {'action_orphan_device_event': 0}

        action_collection = db[Action._meta.db_table]
        device_event_table = DeviceEvent._meta.db_table
        orphan_action_rows = list(
            aggregation_orphan_ids(
                action_collection,
                parent_collection=device_event_table,
                foreign_key_field='device_event_id',
            )
        )
        deleted = delete_many_in_chunks(
            action_collection,
            orphan_action_rows,
            chunk_size=chunk_size,
            dry_run=dry_run,
        )
        self.stdout.write(
            f'Action orphan device_event: count={len(orphan_action_rows)}, '
            f'{"would delete" if dry_run else "deleted"}={deleted}'
        )
        return {'action_orphan_device_event': deleted}

    def _cleanup_job_status_files(self, dry_run):
        monthly_removed = purge_expired_job_status_files(
            MONTHLY_REPORT_JOB_STATUS_DIR,
            ttl_seconds=MONTHLY_REPORT_JOB_STATUS_TTL_SECONDS,
            dry_run=dry_run,
        )
        reprocess_removed = purge_expired_job_status_files(
            REPROCESS_JOB_STATUS_DIR,
            ttl_seconds=REPROCESS_JOB_STATUS_TTL_SECONDS,
            dry_run=dry_run,
        )
        self.stdout.write(
            f'Job status files: monthly={monthly_removed}, reprocess={reprocess_removed} '
            f'({"would remove" if dry_run else "removed"})'
        )
        return {
            'job_status_monthly_files': monthly_removed,
            'job_status_reprocess_files': reprocess_removed,
        }
