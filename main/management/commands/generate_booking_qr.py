from django.core.management.base import BaseCommand
from django.conf import settings
from django.core.files.base import ContentFile
from django.urls import reverse
from main.models import Booking
from django.core import signing
from urllib.parse import quote_plus


QUESTIONNAIRE_TOKEN_SALT = "booking-questionnaire-v1"


def _questionnaire_token_for_booking_id(booking_id: int) -> str:
    return signing.dumps(int(booking_id), salt=QUESTIONNAIRE_TOKEN_SALT)

class Command(BaseCommand):
    help = 'Generate and save QR PNGs for bookings that do not have one yet (points to booking questionnaire)'

    def handle(self, *args, **options):
        import io
        try:
            import qrcode
            has_qrcode = True
        except Exception:
            has_qrcode = False
        import urllib.request
        count = 0
        base = getattr(settings, 'BASE_URL', 'http://127.0.0.1:8000')
        for b in Booking.objects.all():
            # Refresh old QR (non-v2) so it contains the tokenized URL.
            if getattr(b, 'qr_code', None) and b.qr_code and 'questionnaire_v2' in (b.qr_code.name or ''):
                self.stdout.write(self.style.NOTICE(f'Booking #{b.id}: already has QR v2: {b.qr_code.name}'))
                continue
            try:
                qpath = reverse('booking_questionnaire', args=[b.id])
            except Exception as e:
                self.stdout.write(self.style.ERROR(f'Booking #{b.id}: cannot build url, error: {e}'))
                continue
            token = _questionnaire_token_for_booking_id(b.id)
            full = base + qpath + f"?t={quote_plus(token)}"
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

                filename = f'booking_{b.id}_questionnaire_v2.png'
                b.qr_code.save(filename, ContentFile(data), save=True)
                count += 1
                self.stdout.write(self.style.SUCCESS(f'Booking #{b.id}: QR saved to {b.qr_code.name}'))
            except Exception as e:
                self.stdout.write(self.style.ERROR(f'Booking #{b.id}: failed to generate QR: {e}'))
        self.stdout.write(self.style.SUCCESS(f'Done. Generated {count} QR codes.'))
