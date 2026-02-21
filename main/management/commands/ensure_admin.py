import os
from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model

class Command(BaseCommand):
    help = "Create an admin user if it doesn't exist (safe to run multiple times)."

    def handle(self, *args, **options):
        User = get_user_model()

        username = os.environ.get("ADMIN_USERNAME", "admin")
        email = os.environ.get("ADMIN_EMAIL", "admin@example.com")
        password = os.environ.get("ADMIN_PASSWORD")

        if not password:
            self.stdout.write(self.style.WARNING(
                "ADMIN_PASSWORD is not set. Skipping admin creation."
            ))
            return

        if User.objects.filter(username=username).exists():
            self.stdout.write(self.style.SUCCESS("Admin already exists."))
            return

        User.objects.create_superuser(username=username, email=email, password=password)
        self.stdout.write(self.style.SUCCESS(f"Created admin: {username}"))