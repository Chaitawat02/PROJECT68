from django.db import models
from django.db.models.deletion import ProtectedError
from django.db.models.signals import pre_delete
from django.utils import timezone
from .upload_paths import (
    upload_ar_file,
    upload_ar_poster,
    upload_museum_image,
    upload_profile_pic,
    upload_qr_code,
    upload_silk_gallery_image,
    upload_silk_image,
    upload_silk_model,
    upload_silk_target,
    upload_speaker_profile,
    upload_speaker_work_image,
    upload_workshop_gallery,
    upload_workshop_image,
)
# =========================================================
# 5.1) SILK PATTERN GALLERY IMAGE (Many images per pattern)
# =========================================================
class SilkPatternGalleryImage(models.Model):
    silkpattern = models.ForeignKey(
        'SilkPattern',
        on_delete=models.CASCADE,
        related_name='gallery_images',
        verbose_name="ลายผ้า"
    )
    image = models.ImageField(
        upload_to=upload_silk_gallery_image,
        verbose_name="รูปประกอบผ้าเพิ่มเติม"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "รูปประกอบผ้าเพิ่มเติม"
        verbose_name_plural = "รูปประกอบผ้าเพิ่มเติมทั้งหมด"

    def __str__(self):
        return f"Gallery Image for {self.silkpattern.Si_name if self.silkpattern else '-'}"
"""
main/models.py
"""
import os
import random
import string
from django.db import models
from django.conf import settings
from django.contrib.auth import get_user_model
from django.db.models.signals import post_save
from django.dispatch import receiver

User = get_user_model()

# ฟังก์ชันสำหรับสุ่มรหัส 13 หลัก สำหรับ SpeakerAssignment
def generate_assignment_id():
    return ''.join(random.choices(string.digits, k=13))

# =========================================================
# 1) USER PROFILE & AUTH
# =========================================================
class Profile(models.Model):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='profile',
        primary_key=True
    )
    full_name = models.CharField(max_length=200, blank=True)
    phone = models.CharField(max_length=20, blank=True)
    image = models.ImageField(upload_to=upload_profile_pic, blank=True, null=True, verbose_name="รูปโปรไฟล์", unique=False)

    role = models.CharField(
        max_length=20,
        choices=[('member', 'Member'), ('speaker', 'Speaker'), ('admin', 'Admin')],
        default='member',
        verbose_name="สิทธิ์การใช้งาน"
    )

    email_verified = models.BooleanField(default=False)
    phone_verified = models.BooleanField(default=False)

    def __str__(self):
        return self.full_name or getattr(self.user, "username", "")


@receiver(post_save, sender=User)
def create_or_update_user_profile(sender, instance, created, **kwargs):
    if created:
        first = (instance.first_name or "").strip()
        last = (instance.last_name or "").strip()
        Profile.objects.update_or_create(
            user=instance,
            defaults={
                'full_name': f"{first} {last}".strip()
            }
        )
    elif hasattr(instance, 'profile'):
        instance.profile.save()


# =========================================================
# 2) SPEAKER
# =========================================================
class Speaker(models.Model):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True, blank=True
    )
    name = models.CharField(max_length=255)
    profile_picture = models.ImageField(upload_to=upload_speaker_profile, blank=True, null=True)
    biography = models.TextField(blank=True)
    expertise = models.CharField(max_length=255, blank=True, verbose_name="ความเชี่ยวชาญ")

    def __str__(self):
        return self.name

    def delete(self, using=None, keep_parents=False):
        # ห้ามลบวิทยากร ถ้ามีหลักฐานผลงาน หรือมีงานที่ปิดงานแล้ว
        has_work_uploads = self.work_uploads.exists()
        has_completed_assignments = self.assignments.filter(status="completed").exists()

        if has_work_uploads or has_completed_assignments:
            raise ProtectedError(
                "ไม่สามารถลบวิทยากรได้ เนื่องจากมีประวัติผลงานหรือมีงานที่ปิดงานแล้ว",
                [self],
            )

        return super().delete(using=using, keep_parents=keep_parents)


# =========================================================
# 3) MUSEUM PROFILE & WORKSHOP
# =========================================================
class MuseumProfile(models.Model):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        null=True, blank=True
    )
    name = models.CharField(max_length=255, default="National Silk Museum", verbose_name="ชื่อพิพิธภัณฑ์")
    history = models.TextField(blank=True, null=True, verbose_name="ประวัติความเป็นมา")
    biography = models.TextField(blank=True, verbose_name="คำแนะนำสั้นๆ")
    address = models.TextField(blank=True, null=True, verbose_name="ที่อยู่")
    phone = models.CharField(max_length=50, blank=True, null=True, verbose_name="เบอร์โทรศัพท์")
    opening_hours = models.CharField(max_length=255, blank=True, null=True, verbose_name="เวลาทำการ")

    # ข้อมูลติดต่อเพิ่มเติม
    email = models.EmailField(blank=True, null=True, verbose_name="อีเมลทางการ")

    # รูปภาพสำหรับหน้าเว็บหลัก
    logo = models.ImageField(
        upload_to=upload_museum_image,
        blank=True,
        null=True,
        verbose_name="โลโก้พิพิธภัณฑ์",
        help_text="ใช้แสดงเป็นโลโก้ของพิพิธภัณฑ์ในหน้ารายงาน/ส่วนหัวต่าง ๆ"
    )
    hero_image = models.ImageField(
        upload_to=upload_museum_image,
        blank=True,
        null=True,
        verbose_name="รูปพื้นหลังหลักของหน้าแรก",
        help_text="ใช้แสดงเป็นภาพพื้นหลัง/เฮดเดอร์บนหน้าแรกของเว็บไซต์"
    )
    gallery_image1 = models.ImageField(
        upload_to=upload_museum_image,
        blank=True,
        null=True,
        verbose_name="รูปแกลเลอรี 1 (เกี่ยวกับพิพิธภัณฑ์)"
    )
    gallery_image2 = models.ImageField(
        upload_to=upload_museum_image,
        blank=True,
        null=True,
        verbose_name="รูปแกลเลอรี 2 (เกี่ยวกับพิพิธภัณฑ์)"
    )
    gallery_image3 = models.ImageField(
        upload_to=upload_museum_image,
        blank=True,
        null=True,
        verbose_name="รูปแกลเลอรี 3 (เกี่ยวกับพิพิธภัณฑ์)"
    )

    def __str__(self):
        return self.name


class Workshop(models.Model):
    title = models.CharField(max_length=255, verbose_name="ชื่อกิจกรรม")
    description = models.TextField(blank=True, verbose_name="รายละเอียด")
    start_date = models.DateField(null=True, blank=True, verbose_name="วันที่เริ่มกิจกรรม")
    end_date = models.DateField(null=True, blank=True, verbose_name="วันที่สิ้นสุดกิจกรรม")
    start_time = models.TimeField(null=True, blank=True, verbose_name="เวลาเริ่ม")
    end_time = models.TimeField(null=True, blank=True, verbose_name="เวลาสิ้นสุด")
    SESSION_PERIOD_CHOICES = [
        ("morning", "ช่วงเช้า"),
        ("afternoon", "ช่วงบ่าย"),
        ("both", "ทั้งเช้าและบ่าย"),
    ]
    session_period = models.CharField(
        max_length=20,
        choices=SESSION_PERIOD_CHOICES,
        default="both",
        blank=True,
        verbose_name="ช่วงจัดกิจกรรม",
        help_text="เลือกช่วงเวลาที่จัดกิจกรรม (เช้า / บ่าย / ทั้งเช้าและบ่าย)",
    )
    duration = models.CharField(
        max_length=50,
        blank=True,
        verbose_name="ระยะเวลา",
        help_text="เช่น 6 เดือน หรือ 1 ปี"
    )
    location = models.CharField(max_length=255, blank=True, verbose_name="สถานที่")
    max_participants = models.IntegerField(default=20, verbose_name="รับจำนวนจำกัด")
    is_active = models.BooleanField(default=True, verbose_name="เปิดให้จอง")
    inactive_reason = models.CharField(
        max_length=255,
        blank=True,
        verbose_name="เหตุผลที่ปิดกิจกรรม",
        help_text="เช่น วัสดุอุปกรณ์ไม่พอ / เต็มแล้ว / ปิดปรับปรุง",
    )
    image = models.ImageField(upload_to=upload_workshop_image, blank=True, null=True, verbose_name="รูปภาพ")
    detail_image = models.ImageField(
        upload_to=upload_workshop_image,
        blank=True,
        null=True,
        verbose_name="รูปประกอบกิจกรรม",
        help_text="รูปเพิ่มเติมที่ใช้แสดงในหน้ารายละเอียดกิจกรรม",
    )

    def __str__(self):
        return self.title

    def delete(self, using=None, keep_parents=False):
        # 1) ถ้ามีการจอง/ผูกข้อมูลแล้ว ห้ามลบ
        has_any_booking = (
            self.workshopbooking_set.exists()
            or self.booking_set.exists()
        )

        # 2) ถ้ากิจกรรมจบไปแล้ว (ตามวันสิ้นสุด/วันเริ่ม) ห้ามลบ
        end_or_start = self.end_date or self.start_date
        is_past = bool(end_or_start and end_or_start < timezone.localdate())

        if has_any_booking or is_past:
            raise ProtectedError(
                "ไม่สามารถลบกิจกรรมได้ เนื่องจากมีการจองหรือกิจกรรมสิ้นสุดแล้ว",
                [self],
            )

        return super().delete(using=using, keep_parents=keep_parents)


class WorkshopGalleryImage(models.Model):
    workshop = models.ForeignKey(
        Workshop,
        on_delete=models.CASCADE,
        related_name="gallery_images",
        verbose_name="กิจกรรม",
    )
    image = models.ImageField(
        upload_to=upload_workshop_gallery,
        verbose_name="รูปประกอบกิจกรรมเพิ่มเติม",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "รูปประกอบกิจกรรม"
        verbose_name_plural = "รูปประกอบกิจกรรม (หลายรูปต่อกิจกรรม)"

    def __str__(self):
        return f"รูปประกอบ {self.workshop.title}"


# =========================================================
# 4) BOOKING & RESERVATION
# =========================================================
class Booking(models.Model):
    Re_date = models.DateField(null=True, blank=True)
    Re_quantity = models.IntegerField(default=1)

    VISIT_SESSION_CHOICES = [
        ('morning', 'ช่วงเช้า (09:00-12:00)'),
        ('afternoon', 'ช่วงบ่าย (13:00-16:00)'),
    ]
    visit_session = models.CharField(
        max_length=20,
        choices=VISIT_SESSION_CHOICES,
        null=True,
        blank=True,
        verbose_name="ช่วงเวลาเข้าชม",
    )

    STATUS_CHOICES = [
        ('pending', 'รออนุมัติการจอง'),
        ('approved', 'อนุมัติแล้ว'),
        ('rejected', 'ปฏิเสธ'),
        ('cancelled', 'ยกเลิกโดยผู้ใช้'),
        ('confirmed', 'มอบหมายวิทยากรแล้ว'),
        ('completed', 'เสร็จสิ้นการเข้าชม'),
    ]
    Re_status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')

    Us_ID = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='bookings'
    )

    workshop = models.ForeignKey(
        Workshop,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        verbose_name="กิจกรรม"
    )

    fullname = models.CharField(max_length=255, blank=True)
    email = models.EmailField(blank=True)
    phone = models.CharField(max_length=20, blank=True, null=True, verbose_name="เบอร์โทรศัพท์")

    check_in = models.TimeField(null=True, blank=True)
    check_out = models.TimeField(null=True, blank=True)
    people = models.PositiveIntegerField(null=True, blank=True)

    rating = models.PositiveSmallIntegerField(null=True, blank=True)
    rating_comment = models.TextField(blank=True)
    rated_at = models.DateTimeField(null=True, blank=True)

    decided_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='decided_bookings'
    )
    decided_at = models.DateTimeField(null=True, blank=True)
    decision_note = models.TextField(null=True, blank=True)

    # ✅ เพิ่ม: เหตุผล + เวลาที่ยกเลิก
    cancel_reason = models.CharField(
        max_length=255,
        blank=True,
        null=True,
        verbose_name="เหตุผลการยกเลิก"
    )
    cancelled_at = models.DateTimeField(
        blank=True,
        null=True,
        verbose_name="เวลาที่ยกเลิก"
    )

    # QR code image for this booking (generated and stored on server)
    qr_code = models.ImageField(
        upload_to=upload_qr_code,
        null=True,
        blank=True,
        verbose_name="QR Code สำหรับการจอง"
    )

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "main_booking"
        ordering = ['-Re_date', '-created_at']

    def __str__(self):
        return f"Booking #{self.pk} — {self.fullname} ({self.Re_status})"

    def delete(self, using=None, keep_parents=False):
        # ห้ามลบการจอง ถ้ามีการมอบหมายวิทยากรแล้ว หรือมีการตอบแบบประเมินแล้ว
        has_speaker_assigned = False
        try:
            has_speaker_assigned = bool(getattr(self, "speaker_assignment", None))
        except Exception:
            has_speaker_assigned = False

        has_questionnaire_answers = self.question_responses.exists()

        if has_speaker_assigned or has_questionnaire_answers:
            raise ProtectedError(
                "ไม่สามารถลบการจองได้ เนื่องจากมีการมอบหมายวิทยากรหรือมีการทำแบบประเมินแล้ว",
                [self],
            )

        return super().delete(using=using, keep_parents=keep_parents)

class Reservation(models.Model):
    VISIT_CHOICES = [
        ('visit', 'เข้าชมพิพิธภัณฑ์'),
        ('workshop', 'เวิร์กช็อป')
    ]
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='reservations')
    reservation_type = models.CharField(max_length=20, choices=VISIT_CHOICES)
    date = models.DateField()
    booking = models.ForeignKey(Booking, on_delete=models.CASCADE, null=True, blank=True, related_name='reservations')
    created_at = models.DateTimeField(auto_now_add=True)


# =========================================================
# 5) AR & SILK PATTERN
# =========================================================
class ARAsset(models.Model):
    title = models.CharField(max_length=120)
    slug = models.SlugField(unique=True)
    description = models.TextField(blank=True)
    glb = models.FileField(upload_to=upload_ar_file, blank=True, null=True)
    usdz = models.FileField(upload_to=upload_ar_file, blank=True, null=True)
    poster = models.ImageField(upload_to=upload_ar_poster, blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)


from django.db import models

class SilkPattern(models.Model):
    # --- ข้อมูลทั่วไป ---
    Si_ID = models.CharField(
        max_length=13,
        unique=True,
        null=True,
        blank=True,
        db_index=True,
        verbose_name="รหัสผ้า (Si_ID)"
    )
    Si_name = models.CharField(max_length=100, verbose_name="ชื่อลายผ้า")
    Si_address = models.CharField(max_length=255, blank=True, verbose_name="แหล่งผลิต/ที่มา")
    Si_type = models.CharField(max_length=100, blank=True, verbose_name="ประเภทผ้า")
    Si_color = models.CharField(max_length=100, blank=True, verbose_name="สีหลัก")
    Si_history = models.TextField(blank=True, verbose_name="ประวัติและความเป็นมา")

    # --- ส่วนประกอบสำหรับ AR (CRUD ผ่าน Admin) ---

    # 1) ลำดับ Index ในไฟล์ .mind
    target_index = models.PositiveIntegerField(
        null=True,
        blank=True,
        verbose_name="ลำดับเป้าหมายในไฟล์ .mind (Target Index)",
        help_text="ใส่เลข 0, 1, 2... ให้ตรงกับลำดับรูปที่ใช้ทำไฟล์ .mind"
    )

    # 2) ชื่อไฟล์ .mind ที่ใช้งานร่วมกับรายการนี้
    target_file = models.CharField(
        max_length=100,
        blank=True,
        null=True,
        verbose_name="ชื่อไฟล์ .mind ที่เก็บรูป (เช่น targets0.mind)",
        help_text="ระบุชื่อไฟล์ .mind ที่ประกอบด้วยรูปของรายการนี้ (ว่างได้)"
    )

    # 3) ไฟล์โมเดล 3D (.glb) ใช้ช่องเดียว
    model_3d = models.FileField(
        upload_to=upload_silk_model,
        blank=True,
        null=True,
        verbose_name="โมเดล 3D (.glb)"
    )

    # 4) รูปภาพอ้างอิง AR (jpg/png)
    reference = models.ImageField(
        upload_to=upload_silk_target,
        blank=True,
        null=True,
        verbose_name="รูปภาพอ้างอิง AR (Reference Image)"
    )

    # 5) รูปภาพประกอบลายผ้า
    image = models.ImageField(
        upload_to=upload_silk_image,
        blank=True,
        null=True,
        verbose_name="รูปภาพประกอบลายผ้า"
    )

    class Meta:
        ordering = ["target_index"]
        verbose_name = "ข้อมูลลายผ้าไหม"
        verbose_name_plural = "จัดการลายผ้าไหม (AR & Info)"
        unique_together = ("target_file", "target_index")

    def __str__(self):
        return f"{self.Si_ID} - {self.Si_name}" if self.Si_ID else self.Si_name

    # ✅ ตรวจนามสกุลไฟล์โมเดล 3D
    def clean(self):
        if self.model_3d:
            ext = os.path.splitext(self.model_3d.name)[1].lower()
            if ext != ".glb":
                raise ValidationError("ระบบรองรับเฉพาะไฟล์โมเดลนามสกุล .glb เท่านั้น")

class SilkPatternRating(models.Model):
    GROUP_CHOICES = [
        ('school', 'โรงเรียน'), ('university', 'มหาวิทยาลัย'), ('tour_group', 'ทัวร์'),
        ('family', 'ครอบครัว'), ('organization', 'องค์กร'), ('other', 'อื่นๆ'),
    ]
    silk = models.ForeignKey(SilkPattern, on_delete=models.CASCADE, related_name='ratings', null=True, blank=True)
    booking = models.ForeignKey(Booking, on_delete=models.CASCADE, related_name='silk_ratings')
    group_type = models.CharField(max_length=20, choices=GROUP_CHOICES, default='other')
    q1_display = models.PositiveSmallIntegerField(default=3)
    q2_knowledge = models.PositiveSmallIntegerField(default=3)
    q3_quality = models.PositiveSmallIntegerField(default=3)
    q4_variety = models.PositiveSmallIntegerField(default=3)
    q5_colors = models.PositiveSmallIntegerField(default=3)
    q6_ar_experience = models.PositiveSmallIntegerField(default=3)
    q7_guide = models.PositiveSmallIntegerField(default=3)
    q8_facility = models.PositiveSmallIntegerField(default=3)
    q9_price = models.PositiveSmallIntegerField(default=3)
    q10_recommend = models.PositiveSmallIntegerField(default=3)
    comment = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)


# =========================================================
# 6) QUESTION
# =========================================================
class Question(models.Model):
    question = models.TextField(verbose_name="หัวข้อคำถาม")
    option_a = models.CharField(max_length=200, verbose_name="ตัวเลือก A")
    option_b = models.CharField(max_length=200, verbose_name="ตัวเลือก B")
    option_c = models.CharField(max_length=200, verbose_name="ตัวเลือก C")
    option_d = models.CharField(max_length=200, verbose_name="ตัวเลือก D")
    option_e = models.CharField(max_length=200, verbose_name="ตัวเลือก E", blank=True, default='5')
    is_active = models.BooleanField(default=True, verbose_name="เปิดให้ทำแบบประเมิน")
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.question

    def delete(self, using=None, keep_parents=False):
        # ถ้ามีคำตอบแล้ว ห้ามลบ
        if self.bookingquestionresponse_set.exists() or self.survey_ratings.exists():
            raise ProtectedError(
                "ไม่สามารถลบคำถามได้ เนื่องจากมีผู้ตอบคำถามนี้แล้ว",
                [self],
            )
        return super().delete(using=using, keep_parents=keep_parents)


# =========================================================
# 7) SPEAKER ASSIGNMENT & SCHEDULE
# =========================================================

class SpeakerAssignment(models.Model):
    assignment_id = models.CharField(
        max_length=13,
        primary_key=True,         # ใช้เป็นคีย์หลักแทน ID ปกติ
        default=generate_assignment_id,
        blank=True,               # ใน Form อนุญาตให้ว่างได้ (เพราะเดี๋ยว Default จะเติมให้)
        editable=False,           # แนะนำ: เพิ่มเพื่อป้องกันการแก้ไขผ่าน Admin/Form และซ่อนจากหน้า Form
        verbose_name="รหัสมอบหมายวิทยากร"
    )

    quantity = models.CharField(max_length=50, blank=True, null=True, verbose_name="จำนวน")
    schedule_text = models.TextField(blank=True, null=True, verbose_name="วันที่-เวลา")

    speaker = models.ForeignKey(
        'Speaker',
        on_delete=models.CASCADE,
        related_name='assignments',
        verbose_name="วิทยากร"
    )

    booking = models.OneToOneField(
        'Booking',
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='speaker_assignment',
        verbose_name="การจอง/กิจกรรม"
    )

    title = models.CharField(max_length=255, blank=True, verbose_name="หัวข้อ")
    note = models.TextField(blank=True, verbose_name="หมายเหตุ")
    status = models.CharField(max_length=20, default='pending', verbose_name="สถานะ")
    assigned_at = models.DateTimeField(auto_now_add=True)

    # เวลา/วันที่ที่วิทยากรกดยืนยันปฏิเสธงาน (ใช้บังคับเงื่อนไข: ปฏิเสธวันนี้แล้วมอบหมายซ้ำวันนี้ไม่ได้)
    rejected_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        # ใช้ getattr ป้องกัน Error กรณี speaker ถูกลบไปแล้วแต่ assignment ยังอยู่ (ทางทฤษฎีไม่เกิดเพราะ on_delete=CASCADE แต่กันไว้ดีกว่า)
        speaker_name = getattr(self.speaker, 'name', 'Unknown Speaker')
        return f"{self.assignment_id} - {speaker_name}"


class SpeakerSchedule(models.Model):
    speaker = models.ForeignKey(Speaker, on_delete=models.CASCADE, related_name='schedules')
    event_name = models.CharField(max_length=255)
    event_date = models.DateTimeField()
    location = models.CharField(max_length=255)


class WorkshopBooking(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='workshop_bookings', null=True, blank=True)
    workshop = models.ForeignKey(Workshop, on_delete=models.CASCADE, null=True, blank=True)
    date = models.DateField()
    booking = models.ForeignKey(Booking, on_delete=models.CASCADE, null=True, blank=True, related_name='workshop_items')
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.workshop.title if self.workshop else 'N/A'} - {self.date}"


# =========================================================
# 8) POST-VISIT QUESTIONNAIRE RESPONSES
# =========================================================
class BookingQuestionResponse(models.Model):
    """เก็บคำตอบของคำถามหลังการเข้าชม สำหรับแต่ละการจอง"""
    booking = models.ForeignKey(Booking, on_delete=models.CASCADE, related_name='question_responses')
    question = models.ForeignKey(Question, on_delete=models.CASCADE)
    # บันทึกคำตอบเป็นตัวอักษร 'a'|'b'|'c'|'d' หรือข้อความอื่นๆ
    answer = models.CharField(max_length=10)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'คำตอบแบบประเมินการจอง'
        verbose_name_plural = 'คำตอบแบบประเมินการจอง'

    def __str__(self):
        return f"Booking {self.booking_id} - Q{self.question.id} => {self.answer}"

# =========================================================
# 9) GENERIC SURVEY / RATING (1-5 scale)
# =========================================================
class SurveyRating(models.Model):
    """บันทึกคะแนนแบบตัวเลข 1-5 และข้อเสนอแนะสำหรับแต่ละหัวข้อคำถาม"""
    question = models.ForeignKey(Question, on_delete=models.CASCADE, related_name='survey_ratings')
    rating = models.PositiveSmallIntegerField(default=3)
    comment = models.TextField(blank=True)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'คะแนนแบบประเมิน'
        verbose_name_plural = 'คะแนนแบบประเมิน'

    def __str__(self):
        return f"Q{self.question.id} => {self.rating}"

# main/models.py
# =========================================================
# 10) SPEAKER WORK UPLOAD (วิทยากรอัปโหลดรูปงาน)
# =========================================================
class SpeakerWorkUpload(models.Model):
    speaker = models.ForeignKey(
        Speaker,
        on_delete=models.CASCADE,
        related_name="work_uploads",
        verbose_name="วิทยากร",
    )

    # ผูกกับงานที่ได้รับมอบหมาย (ถ้าเลือก)
    assignment = models.ForeignKey(
        SpeakerAssignment,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="work_uploads",
        verbose_name="งานที่รับผิดชอบ",
    )

    title = models.CharField(max_length=255, blank=True, verbose_name="หัวข้อ/ชื่อชุดรูป")
    note = models.TextField(blank=True, verbose_name="หมายเหตุ/รายละเอียด")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "ชุดรูปผลงานวิทยากร"
        verbose_name_plural = "ชุดรูปผลงานวิทยากร"

    def __str__(self):
        return f"Upload by {self.speaker.name} ({self.created_at:%Y-%m-%d %H:%M})"


class SpeakerWorkImage(models.Model):
    upload = models.ForeignKey(
        SpeakerWorkUpload,
        on_delete=models.CASCADE,
        related_name="images",
        verbose_name="ชุดอัปโหลด",
    )
    image = models.ImageField(upload_to=upload_speaker_work_image, verbose_name="รูปภาพ")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "รูปผลงานวิทยากร"
        verbose_name_plural = "รูปผลงานวิทยากร"

    def __str__(self):
        return f"WorkImage #{self.pk}"


@receiver(pre_delete, sender=User)
def prevent_user_delete_if_has_bookings(sender, instance, **kwargs):
    # ✅ ถ้าผู้ใช้งานมีประวัติการจอง/เข้าร่วมแล้ว ห้ามลบ
    # ครอบคลุม: การจองเข้าชม (Booking), การจองกิจกรรม (WorkshopBooking), และ Reservation
    try:
        has_booking = Booking.objects.filter(Us_ID=instance).exists()
    except Exception:
        has_booking = False

    try:
        has_workshop_booking = WorkshopBooking.objects.filter(user=instance).exists()
    except Exception:
        has_workshop_booking = False

    try:
        has_reservation = Reservation.objects.filter(user=instance).exists()
    except Exception:
        has_reservation = False

    if has_booking or has_workshop_booking or has_reservation:
        raise ProtectedError(
            "ไม่สามารถลบผู้ใช้งานได้ เนื่องจากมีประวัติการจองในระบบ",
            [instance],
        )

    # ✅ ถ้าเป็นบัญชีวิทยากร: ห้ามลบถ้ามีผลงาน หรือมีงาน completed แล้ว
    try:
        speaker = Speaker.objects.filter(user=instance).first()
    except Exception:
        speaker = None

    if speaker:
        has_work_uploads = speaker.work_uploads.exists()
        has_completed_assignments = speaker.assignments.filter(status="completed").exists()
        if has_work_uploads or has_completed_assignments:
            raise ProtectedError(
                "ไม่สามารถลบบัญชีวิทยากรได้ เนื่องจากมีประวัติผลงานหรือมีงานที่ปิดงานแล้ว",
                [instance],
            )