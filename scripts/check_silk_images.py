import os, sys
from pathlib import Path
PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

os.environ.setdefault('DJANGO_SETTINGS_MODULE','myproject.settings')
import django
django.setup()
from main.models import SilkPattern
from django.conf import settings

print('MEDIA_ROOT =', settings.MEDIA_ROOT)

patterns = SilkPattern.objects.all()
print('Total patterns:', patterns.count())
for p in patterns:
    print('---')
    print('ID:', p.pk, 'Name:', p.Si_name)
    print('image field:', p.image)
    if p.image:
        path = p.image.path
        print(' filesystem path:', path)
        print(' exists:', os.path.exists(path))
    else:
        print(' no image set')
