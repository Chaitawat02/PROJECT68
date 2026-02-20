from django.core.management.base import BaseCommand
from django.db import transaction

from main.models import SpeakerAssignment, SpeakerSchedule


class Command(BaseCommand):
    help = "ลบประวัติการมอบหมายงานและตารางงานของวิทยากรทั้งหมด (ใช้อย่างระมัดระวัง!)"

    def add_arguments(self, parser):
        parser.add_argument(
            "--force",
            action="store_true",
            help="ยืนยันการลบข้อมูลทั้งหมดโดยไม่ถามซ้ำ (ไม่สามารถกู้คืนได้)",
        )

    def handle(self, *args, **options):
        if not options["force"]:
            self.stdout.write(self.style.ERROR(
                "คำเตือน: คำสั่งนี้จะลบ 'ประวัติการรับงานของวิทยากร' ทั้งหมด รวมถึงตารางงานที่บันทึกไว้.\n"
                "หากต้องการลบจริง ให้รันคำสั่งซ้ำพร้อมพารามิเตอร์ --force"
            ))
            self.stdout.write("ตัวอย่าง: python manage.py clear_speaker_history --force")
            return

        with transaction.atomic():
            schedule_count, _ = SpeakerSchedule.objects.all().delete()
            assignment_count, _ = SpeakerAssignment.objects.all().delete()

        self.stdout.write(self.style.SUCCESS(
            "ลบข้อมูลประวัติวิทยากรเรียบร้อยแล้ว:\n"
            f"- SpeakerSchedule  : {schedule_count} แถว\n"
            f"- SpeakerAssignment: {assignment_count} แถว\n"
        ))
