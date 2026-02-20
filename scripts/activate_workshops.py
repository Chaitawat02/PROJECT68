import os
import sys

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'myproject.settings')
import django
django.setup()

from main.models import Workshop

qs = Workshop.objects.filter(is_active=False)
print(f"Found {qs.count()} inactive workshops")
for w in qs:
    print(f"Activating {w.pk} | {w.title!r}")
    w.is_active = True
    w.save()
print("Done.")
