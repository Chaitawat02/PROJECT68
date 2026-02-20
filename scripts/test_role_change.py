import os
import django
os.environ.setdefault('DJANGO_SETTINGS_MODULE','myproject.settings')
django.setup()
from django.contrib.auth import get_user_model
from main.models import Profile
User = get_user_model()
user, created = User.objects.get_or_create(username='role_test_user', defaults={'email':'role@test'})
user.set_password('test1234')
user.save()
profile, _ = Profile.objects.get_or_create(user=user)
print('Before:', user.username, user.is_staff, user.is_superuser, profile.role)
# Simulate role change to admin
role = 'admin'
user.is_staff = (role == 'admin')
user.is_superuser = (role == 'admin')
user.save()
profile.role = role
profile.save()
print('After:', user.username, user.is_staff, user.is_superuser, profile.role)
