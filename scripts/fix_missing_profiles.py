from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from main.models import Profile

class Command(BaseCommand):
    help = 'Ensure every user has a Profile object.'

    def handle(self, *args, **options):
        User = get_user_model()
        created_count = 0
        for user in User.objects.all():
            profile, created = Profile.objects.get_or_create(user=user)
            if created:
                created_count += 1
                self.stdout.write(self.style.SUCCESS(f'Created profile for user: {user.username}'))
        self.stdout.write(self.style.SUCCESS(f'Completed. Total new profiles created: {created_count}'))
