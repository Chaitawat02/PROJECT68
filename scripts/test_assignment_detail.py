import os,sys
from pathlib import Path
PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

os.environ.setdefault('DJANGO_SETTINGS_MODULE','myproject.settings')
import django
django.setup()
from django.test import Client
from django.contrib.auth import get_user_model
from main.models import Speaker, SpeakerAssignment

User = get_user_model()
user = User.objects.filter(is_active=True).first()
print('Using user:', user.username)

c = Client()
try:
    sp = Speaker.objects.get(user=user)
except Exception as e:
    print('No Speaker for user:', e)
    sp = None
if sp:
    ass = SpeakerAssignment.objects.filter(speaker=sp).first()
    if ass:
        url = f"/speaker/assignments/{ass.id}/"
        r = c.get(url)
        print('GET', url, '=>', r.status_code)
        print(r.content.decode('utf-8')[:400])
    else:
        print('No assignments for speaker')
else:
    print('No speaker profile for selected user')
