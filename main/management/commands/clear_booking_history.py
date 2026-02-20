from django.core.management.base import BaseCommand
from django.db import transaction

from main.models import (
    Booking,
    Reservation,
    WorkshopBooking,
    BookingQuestionResponse,
    SilkPatternRating,
    SurveyRating,
)


class Command(BaseCommand):
    help = "ลบประวัติการจองทั้งหมด และข้อมูลคำตอบแบบประเมินที่เกี่ยวข้อง (ใช้อย่างระมัดระวัง!)"

    def add_arguments(self, parser):
        parser.add_argument(
            "--force",
            action="store_true",
            help="ยืนยันการลบข้อมูลทั้งหมดโดยไม่ถามซ้ำ (ไม่สามารถกู้คืนได้)",
        )

    def handle(self, *args, **options):
        if not options["force"]:
            self.stdout.write(self.style.ERROR(
                "คำเตือน: คำสั่งนี้จะลบ 'ประวัติการจองทั้งหมด' และ 'ประวัติการตอบแบบประเมินทั้งหมด'.\n"
                "หากต้องการลบจริง ให้รันคำสั่งซ้ำพร้อมพารามิเตอร์ --force"
            ))
            self.stdout.write("ตัวอย่าง: python manage.py clear_booking_history --force")
            return

        with transaction.atomic():
            # ลบข้อมูลคำตอบ/แบบประเมินต่าง ๆ ก่อน (ถึงแม้จะมี CASCADE แต่ทำให้ชัดเจน)
            bq_count, _ = BookingQuestionResponse.objects.all().delete()
            silk_rating_count, _ = SilkPatternRating.objects.all().delete()
            survey_count, _ = SurveyRating.objects.all().delete()

            # ลบการจองเสริมอื่น ๆ ที่ผูกกับ Booking
            workshop_booking_count, _ = WorkshopBooking.objects.all().delete()
            reservation_count, _ = Reservation.objects.all().delete()

            # ลบประวัติการจองหลักทั้งหมด
            booking_count, _ = Booking.objects.all().delete()

        self.stdout.write(self.style.SUCCESS(
            "ลบข้อมูลเรียบร้อยแล้ว:\n"
            f"- Booking           : {booking_count} แถว\n"
            f"- WorkshopBooking   : {workshop_booking_count} แถว\n"
            f"- Reservation       : {reservation_count} แถว\n"
            f"- BookingQuestion   : {bq_count} แถว\n"
            f"- SilkPatternRating : {silk_rating_count} แถว\n"
            f"- SurveyRating      : {survey_count} แถว\n"
        ))
