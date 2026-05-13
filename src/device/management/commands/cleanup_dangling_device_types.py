from django.apps import apps
from django.core.management.base import BaseCommand
from django.db import models, transaction
from django.db.models.deletion import DO_NOTHING


class Command(BaseCommand):
    help = "Find and optionally clear dangling nullable DO_NOTHING foreign key references."

    def add_arguments(self, parser):
        parser.add_argument(
            "--apply",
            action="store_true",
            help="Apply fixes. Without this flag, command runs in dry-run mode.",
        )
        parser.add_argument(
            "--limit",
            type=int,
            default=50,
            help="Max number of sample affected rows to print per relation (default: 50).",
        )
        parser.add_argument(
            "--app",
            action="append",
            dest="apps",
            help="Optional app label(s) to scan, e.g. --app device --app dashboard.",
        )

    @transaction.atomic
    def handle(self, *args, **options):
        apply_fixes = bool(options.get("apply"))
        sample_limit = max(int(options.get("limit") or 0), 0)
        selected_apps = set(options.get("apps") or [])

        mode = "APPLY" if apply_fixes else "DRY-RUN"
        self.stdout.write(self.style.WARNING(f"Mode: {mode}"))

        models_scanned = 0
        relations_scanned = 0
        total_dangling = 0
        total_fixed = 0
        non_nullable_dangling = 0

        for model in apps.get_models():
            if selected_apps and model._meta.app_label not in selected_apps:
                continue
            models_scanned += 1

            for field in model._meta.get_fields():
                if not isinstance(field, models.ForeignKey):
                    continue
                remote_field = field.remote_field
                if remote_field is None or getattr(remote_field, "on_delete", None) is not DO_NOTHING:
                    continue

                relations_scanned += 1
                fk_attname = field.attname
                model_pk = model._meta.pk
                if model_pk is None:
                    continue
                pk_name = model_pk.name
                related_model = remote_field.model
                related_pk = related_model._meta.pk
                if related_pk is None:
                    continue
                related_pk_name = related_pk.name

                relation_label = f"{model._meta.label}.{field.name} -> {related_model._meta.label}"

                # Fetch valid IDs into Python to avoid $nin subquery which Djongo/MongoDB doesn't support.
                valid_ids = set(related_model.objects.values_list(related_pk_name, flat=True))

                all_rows = list(
                    model.objects
                    .exclude(**{f"{fk_attname}__isnull": True})
                    .values(pk_name, fk_attname)
                )
                set_count = len(all_rows)
                dangling_rows = [r for r in all_rows if r[fk_attname] not in valid_ids]
                dangling_count = len(dangling_rows)
                total_dangling += dangling_count

                self.stdout.write(
                    f"{relation_label}: set={set_count} dangling={dangling_count} nullable={field.null}"
                )

                if sample_limit > 0 and dangling_count > 0:
                    self.stdout.write(f"Sample dangling rows for {relation_label}:")
                    for row in dangling_rows[:sample_limit]:
                        self.stdout.write(f"- {pk_name}={row[pk_name]} {fk_attname}={row[fk_attname]}")

                if not apply_fixes or dangling_count == 0:
                    continue

                dangling_pks = [r[pk_name] for r in dangling_rows]
                if field.null:
                    fixed = model.objects.filter(**{f"{pk_name}__in": dangling_pks}).update(**{field.name: None})
                    total_fixed += fixed
                    self.stdout.write(self.style.SUCCESS(f"  Cleared {fixed} rows for {relation_label}."))
                else:
                    non_nullable_dangling += dangling_count
                    self.stdout.write(
                        self.style.WARNING(
                            f"Skipped {dangling_count} non-nullable dangling rows for {relation_label}."
                        )
                    )

        self.stdout.write(
            self.style.WARNING(
                f"Scanned models={models_scanned}, relations={relations_scanned}, dangling_total={total_dangling}"
            )
        )

        if not apply_fixes:
            self.stdout.write(self.style.WARNING("No changes applied. Re-run with --apply to fix nullable relations."))
            return

        self.stdout.write(self.style.SUCCESS(f"Fixed nullable dangling references: {total_fixed}"))
        if non_nullable_dangling > 0:
            self.stdout.write(
                self.style.WARNING(
                    f"Non-nullable dangling references still present: {non_nullable_dangling}"
                )
            )
