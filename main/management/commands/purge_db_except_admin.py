from __future__ import annotations

from dataclasses import dataclass

from django.apps import apps
from django.contrib.admin.models import LogEntry
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.contrib.sessions.models import Session
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction


@dataclass(frozen=True)
class PurgeResult:
    deleted_main: int
    deleted_users: int
    deleted_groups: int
    deleted_sessions: int
    deleted_admin_logs: int


class Command(BaseCommand):
    help = (
        "Delete ALL data from the database except ONE admin user. "
        "Keeps system tables like permissions/contenttypes intact."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--username",
            dest="username",
            help="Keep this username (must be a superuser).",
        )
        parser.add_argument(
            "--email",
            dest="email",
            help="Keep this email (must resolve to a superuser).",
        )
        parser.add_argument(
            "--user-id",
            dest="user_id",
            type=int,
            help="Keep this user id/pk (must be a superuser).",
        )
        parser.add_argument(
            "--yes",
            action="store_true",
            help="Required confirmation flag. Without it, nothing will be deleted.",
        )

    def handle(self, *args, **options):
        if not options.get("yes"):
            raise CommandError("Refusing to run without --yes")

        keep_user = self._resolve_keep_user(
            username=options.get("username"),
            email=options.get("email"),
            user_id=options.get("user_id"),
        )

        result = self._purge_except_user(keep_user)

        self.stdout.write(self.style.SUCCESS("Purge completed."))
        self.stdout.write(
            "Kept admin: id={id} username={username}".format(
                id=keep_user.pk, username=getattr(keep_user, "username", "")
            )
        )
        self.stdout.write(
            "Deleted: main={m}, users={u}, groups={g}, sessions={s}, admin_logs={l}".format(
                m=result.deleted_main,
                u=result.deleted_users,
                g=result.deleted_groups,
                s=result.deleted_sessions,
                l=result.deleted_admin_logs,
            )
        )

    def _resolve_keep_user(self, *, username: str | None, email: str | None, user_id: int | None):
        User = get_user_model()

        provided = [v for v in (username, email, user_id) if v is not None]
        if len(provided) > 1:
            raise CommandError("Use only one of --username/--email/--user-id")

        if username is not None:
            qs = User.objects.filter(username=username)
        elif email is not None:
            qs = User.objects.filter(email=email)
        elif user_id is not None:
            qs = User.objects.filter(pk=user_id)
        else:
            qs = User.objects.filter(is_superuser=True).order_by("id")

        keep_user = qs.first()
        if keep_user is None:
            raise CommandError(
                "No matching user found. Create a superuser first (or pass --username/--email/--user-id)."
            )

        if not getattr(keep_user, "is_superuser", False):
            raise CommandError("Selected user is not a superuser")

        # Ensure admin can still log in to /admin
        if hasattr(keep_user, "is_staff") and not keep_user.is_staff:
            keep_user.is_staff = True
            keep_user.save(update_fields=["is_staff"])

        return keep_user

    def _purge_except_user(self, keep_user) -> PurgeResult:
        deleted_main = 0

        with transaction.atomic():
            # 1) Delete ALL project app data (main)
            main_app = apps.get_app_config("main")
            for model in main_app.get_models():
                # Avoid deleting the auth user table through here (not part of main anyway)
                deleted, _ = model.objects.all().delete()
                deleted_main += deleted

            # 2) Delete admin logs & sessions
            deleted_admin_logs, _ = LogEntry.objects.all().delete()
            deleted_sessions, _ = Session.objects.all().delete()

            # 3) Delete non-kept users
            User = get_user_model()
            deleted_users, _ = User.objects.exclude(pk=keep_user.pk).delete()

            # 4) Delete groups (optional; superuser doesn't need them)
            deleted_groups, _ = Group.objects.all().delete()

        return PurgeResult(
            deleted_main=deleted_main,
            deleted_users=deleted_users,
            deleted_groups=deleted_groups,
            deleted_sessions=deleted_sessions,
            deleted_admin_logs=deleted_admin_logs,
        )
