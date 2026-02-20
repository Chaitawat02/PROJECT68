from django.urls import reverse
from django.conf import settings
from django.core.files.base import ContentFile
from main.models import Booking
try:
    import qrcode
    _HAS_QRCODE = True
except Exception:
    _HAS_QRCODE = False
import io
from urllib.parse import quote_plus
import urllib.request

base = getattr(settings, 'BASE_URL', 'http://127.0.0.1:8000')

count = 0
for b in Booking.objects.all():
    if getattr(b, 'qr_code') and b.qr_code:
        print(f'Booking #{b.id}: already has QR: {b.qr_code.name}')
        continue
    try:
        qpath = reverse('booking_questionnaire', args=[b.id])
    except Exception as e:
        print(f'Booking #{b.id}: cannot build url, error: {e}')
        continue
    full = base + qpath
    try:
        if _HAS_QRCODE:
            img = qrcode.make(full)
            buf = io.BytesIO()
            img.save(buf, format='PNG')
            buf.seek(0)
            data = buf.read()
        else:
            # fallback: fetch PNG from public QR image generator (api.qrserver.com)
            qr_url = f"https://api.qrserver.com/v1/create-qr-code/?size=300x300&data={quote_plus(full)}"
            with urllib.request.urlopen(qr_url) as resp:
                data = resp.read()

        filename = f'booking_{b.id}_questionnaire.png'
        b.qr_code.save(filename, ContentFile(data), save=True)
        print(f'Booking #{b.id}: QR saved to {b.qr_code.name}')
        count += 1
    except Exception as e:
        print(f'Booking #{b.id}: failed to generate QR: {e}')

print(f'Done. Generated {count} QR codes.')
