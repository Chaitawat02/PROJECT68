from __future__ import annotations

from django.core.management.base import BaseCommand
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from main.models import Booking


class Command(BaseCommand):
    help = (
        "Backfill Booking.decided_at for historical records where staff actions occurred "
        "but decided_at was not persisted. Uses created_at as best-effort fallback."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Show how many records would be updated without saving changes.",
        )
        parser.add_argument(
            "--also-fill-decided-by",
            action="store_true",
            help=(
                "(Not recommended) Also fills decided_by with NULL-safe fallback. "
                "This flag currently does nothing; kept for future extension."
            ),
        )

    def handle(self, *args, **options):
        dry_run: bool = bool(options.get("dry_run"))

        # We only backfill decided_at, because decided_by cannot be reliably inferred.
        qs = (
            Booking.objects.exclude(Q(Re_status__isnull=True) | Q(Re_status="") | Q(Re_status="pending"))
            .filter(decided_at__isnull=True)
            .only("id", "Re_status", "created_at", "decided_at")
        )

        total = qs.count()
        self.stdout.write(f"Found {total} booking(s) needing decided_at backfill")

        if total == 0:
            return

        if dry_run:
            sample = list(qs.values_list("id", "Re_status")[:20])
            self.stdout.write(f"Sample (id, status): {sample}")
            self.stdout.write(self.style.WARNING("Dry run: no changes saved"))
            return

        updated = 0
        with transaction.atomic():
            for booking in qs.iterator(chunk_size=500):
                # Best-effort: use created_at; if missing, use now.
                booking.decided_at = booking.created_at or timezone.now()
                booking.save(update_fields=["decided_at"])
                updated += 1

        self.stdout.write(self.style.SUCCESS(f"Updated {updated} booking(s)"))
