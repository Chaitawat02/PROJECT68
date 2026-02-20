import os
import sys
import django

# Ensure project root is on sys.path so 'myproject' package can be imported
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'myproject.settings')
django.setup()

from main.models import Workshop

qs = Workshop.objects.all().order_by('pk')
print("PK | title | is_active | date | price")
for w in qs:
    print(f"{w.pk} | {w.title!r} | {w.is_active} | {w.date} | {getattr(w, 'price', None)}")
