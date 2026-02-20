import os
import django
os.environ.setdefault('DJANGO_SETTINGS_MODULE','myproject.settings')
# Ensure project root is on PYTHONPATH when running
django.setup()

from django.test import Client
from django.contrib.auth import get_user_model
from django.urls import reverse
from main.models import Profile

User = get_user_model()

# Create admin user
admin, created = User.objects.get_or_create(username='test_admin', defaults={'email':'admin@test.local'})
admin.set_password('adminpass')
admin.is_staff = True
admin.is_superuser = False
admin.save()
Profile.objects.get_or_create(user=admin)

# Create target user
target, _ = User.objects.get_or_create(username='target_user', defaults={'email':'target@test.local'})
target.set_password('targetpass')
target.is_staff = False
target.is_superuser = False
target.save()
Profile.objects.get_or_create(user=target)

c = Client()
logged = c.login(username='test_admin', password='adminpass')
print('logged_in:', logged)

url = reverse('manage_users_edit', args=[target.id])
print('POSTing to', url)
post_data = {
    'first_name': 'Target',
    'last_name': 'User',
    'email': 'target.changed@test.local',
    'is_active': 'on',
    'role': 'admin',
    'phone': '0123456789'
}
resp = c.post(url, post_data, follow=True)
print('response_status:', resp.status_code)

# Refresh and print results
target.refresh_from_db()
profile = Profile.objects.get(user=target)
print('target.is_staff:', target.is_staff)
print('target.is_superuser:', target.is_superuser)
print('profile.role:', profile.role)
print('target.email:', target.email)
