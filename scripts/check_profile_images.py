import os, sys
from pathlib import Path
PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

os.environ.setdefault('DJANGO_SETTINGS_MODULE','myproject.settings')
import django
django.setup()
from django.conf import settings
from django.contrib.auth import get_user_model
User = get_user_model()

print('MEDIA_ROOT =', settings.MEDIA_ROOT)
print('MEDIA_URL =', settings.MEDIA_URL)

users = User.objects.all()
print('Total users:', users.count())
found = False
for u in users:
    try:
        p = u.profile
    except Exception:
        continue
    if p.image:
        found = True
        path = p.image.path
        url = p.image.url
        print('User:', u.username)
        print('  profile.image:', p.image)
        print('  url:', url)
        print('  filesystem path:', path)
        print('  exists:', os.path.exists(path))
        break

if not found:
    print('No profiles with images found.')
