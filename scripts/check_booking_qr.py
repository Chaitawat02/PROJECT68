import os
import sys
import django

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'myproject.settings')
django.setup()

from main.models import Booking
from django.conf import settings

bk_id = 3
try:
    b = Booking.objects.get(pk=bk_id)
except Booking.DoesNotExist:
    print(f'Booking {bk_id} does not exist')
    sys.exit(0)

print('Booking id:', b.id)
print('qr_code name:', b.qr_code.name)
print('qr_code url:', getattr(b.qr_code, 'url', None))
print('MEDIA_ROOT:', settings.MEDIA_ROOT)
if b.qr_code and getattr(b.qr_code, 'path', None):
    p = b.qr_code.path
    print('qr_code path:', p)
    print('exists on disk:', os.path.exists(p))
else:
    print('No qr_code.path available')

# list qr_codes folder
qr_dir = os.path.join(settings.MEDIA_ROOT, 'qr_codes')
print('qr_codes dir:', qr_dir)
if os.path.isdir(qr_dir):
    print('files in qr_codes:')
    for f in os.listdir(qr_dir)[:50]:
        print(' -', f)
else:
    print('qr_codes dir not found')
