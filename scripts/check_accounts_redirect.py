import os
import sys
from pathlib import Path
# ensure project root is on sys.path (script runs from scripts/ folder)
PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))
os.environ.setdefault('DJANGO_SETTINGS_MODULE','myproject.settings')
import django
django.setup()
from django.test import Client
c = Client()
resp = c.get('/accounts/login/?next=/admin-panel/speaker/edit/1/', follow=False)
print('status_code:', resp.status_code)
if resp.has_header('Location'):
    print('Location:', resp['Location'])
else:
    # show small portion of content for debugging
    content = resp.content.decode('utf-8', errors='replace')
    print('Content (start):')
    print(content[:400])
