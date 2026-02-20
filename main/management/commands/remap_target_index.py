from __future__ import annotations

import os
from django.core.management.base import BaseCommand
from django.db import transaction
from main.models import SilkPattern


class Command(BaseCommand):
    help = "Remap SilkPattern.target_index sequentially to match .mind order"

    def add_arguments(self, parser):
        parser.add_argument(
            "--mind",
            default=None,
            help="Assign this .mind filename to target_file for all remapped patterns",
        )
        parser.add_argument(
            "--by",
            choices=["reference", "name", "id"],
            default="reference",
            help="Ordering used to assign indices (default: reference filename)",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Show mapping only, do not update database",
        )

    def handle(self, *args, **options):
        order_by = options["by"]
        mind = options["mind"]
        dry_run = options["dry_run"]

        qs = SilkPattern.objects.filter(model_3d__isnull=False)
        patterns = list(qs)

        if order_by == "reference":
            def key_fn(p):
                ref = getattr(p.reference, "name", "") or ""
                base = os.path.basename(ref).lower()
                missing = 1 if not base else 0
                return (missing, base, p.pk)
        elif order_by == "name":
            def key_fn(p):
                name = (p.Si_name or "").lower()
                missing = 1 if not name else 0
                return (missing, name, p.pk)
        else:
            def key_fn(p):
                return p.pk or 0

        patterns.sort(key=key_fn)

        lines = []
        for i, p in enumerate(patterns):
            ref = getattr(p.reference, "name", "") or ""
            lines.append(f"{i}: {p.pk} | {p.Si_name} | {os.path.basename(ref) or '-'}")

        self.stdout.write("\n".join(lines) if lines else "No patterns found")

        if dry_run or not patterns:
            return

        ids = [p.pk for p in patterns]

        with transaction.atomic():
            SilkPattern.objects.filter(pk__in=ids).update(target_index=None)
            for i, p in enumerate(patterns):
                p.target_index = i
                if mind:
                    p.target_file = mind
                    p.save(update_fields=["target_index", "target_file"])
                else:
                    p.save(update_fields=["target_index"])

        self.stdout.write(self.style.SUCCESS("target_index remapped successfully"))
