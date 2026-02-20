from django.core.management.base import BaseCommand
from django.conf import settings
from django.core.files.base import ContentFile
from django.urls import reverse
from main.models import Booking

class Command(BaseCommand):
    help = 'Generate and save QR PNGs for bookings that do not have one yet (points to booking questionnaire)'

    def handle(self, *args, **options):
        import io
        try:
            import qrcode
            has_qrcode = True
        except Exception:
            has_qrcode = False
        from urllib.parse import quote_plus
        import urllib.request
        count = 0
        base = getattr(settings, 'BASE_URL', 'http://127.0.0.1:8000')
        for b in Booking.objects.all():
            if getattr(b, 'qr_code', None) and b.qr_code:
                self.stdout.write(self.style.NOTICE(f'Booking #{b.id}: already has QR: {b.qr_code.name}'))
                continue
            try:
                qpath = reverse('booking_questionnaire', args=[b.id])
            except Exception as e:
                self.stdout.write(self.style.ERROR(f'Booking #{b.id}: cannot build url, error: {e}'))
                continue
            full = base + qpath
            try:
                if has_qrcode:
                    img = qrcode.make(full)
                    buf = io.BytesIO()
                    img.save(buf, format='PNG')
                    buf.seek(0)
                    data = buf.read()
                else:
                    # Use a public QR generation endpoint as fallback
                    api_url = f"https://api.qrserver.com/v1/create-qr-code/?size=300x300&data={quote_plus(full)}"
                    with urllib.request.urlopen(api_url) as resp:
                        data = resp.read()

                filename = f'booking_{b.id}_questionnaire.png'
                b.qr_code.save(filename, ContentFile(data), save=True)
                count += 1
                self.stdout.write(self.style.SUCCESS(f'Booking #{b.id}: QR saved to {b.qr_code.name}'))
            except Exception as e:
                self.stdout.write(self.style.ERROR(f'Booking #{b.id}: failed to generate QR: {e}'))
        self.stdout.write(self.style.SUCCESS(f'Done. Generated {count} QR codes.'))
