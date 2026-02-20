import os, sys
from pathlib import Path
PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'myproject.settings')
import django
django.setup()
from django.test import Client
from main.models import Speaker, SpeakerAssignment

c = Client()
# find a speaker with an assignment
ass = SpeakerAssignment.objects.select_related('speaker','booking').first()
if not ass:
    print('No SpeakerAssignment found')
    sys.exit(0)
user = ass.speaker.user
print('Found assignment id=', ass.id, 'for speaker user=', user.username)
# force login
c.force_login(user)
url = f'/speaker/assignments/{ass.id}/'
r = c.get(url)
print('status_code:', r.status_code)
content = r.content.decode('utf-8', errors='replace')
print('\n--- HTML START (first 2000 chars) ---\n')
print(content[:2000])
print('\n--- HTML END ---')
