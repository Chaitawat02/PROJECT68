# ฟังก์ชันตรวจสอบสิทธิ์วิทยากร (ต้องอยู่ก่อนใช้งาน)
# =====================================================================
# IMPORTS
# =====================================================================
import json
import logging
import statistics
import io
import base64
import uuid
import re
from datetime import datetime, time, timedelta
from urllib.parse import quote_plus

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import authenticate, login, logout, get_user_model
from django.contrib.auth.decorators import login_required, user_passes_test
from django.views.decorators.http import require_http_methods
from django.shortcuts import get_object_or_404, redirect, render
from django.core.files.base import ContentFile
from django.core import signing
from django.core.serializers.json import DjangoJSONEncoder
from django.db import IntegrityError, transaction
from django.db.utils import OperationalError
from django.db.models.deletion import ProtectedError
from django.db.models import Q, Count, Avg, Max, IntegerField, OuterRef, Subquery, Case, When, Value
from django.db.models.functions import TruncMonth, Cast
from django.http import JsonResponse, Http404
from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST
from .models import SpeakerWorkUpload, SpeakerWorkImage
from django.utils.http import url_has_allowed_host_and_scheme

# =====================================================================
# MODELS
# =====================================================================
from .models import (
    SilkPattern, Booking, WorkshopBooking, Reservation, ARAsset,
    MuseumProfile, Speaker, SpeakerAssignment, SilkPatternRating,
    SpeakerSchedule, Profile, Workshop, Question,
    BookingQuestionResponse, SurveyRating,
    WorkshopGalleryImage, SilkPatternGalleryImage,
)

# =====================================================================
# FORMS
# =====================================================================
from .forms import (
    LoginForm, SignUpForm, UserEditForm,
    SilkPatternForm, BookingForm, QuestionForm, WorkshopForm,
    MuseumProfileForm,
    ForgotPasswordForm, SetNewPasswordForm,
    SpeakerAssignFromBookingForm, BookingRatingForm,
    SurveyRatingForm
)
# ใช้ชื่อ alias สำหรับคำถามแบบประเมิน
QuestionModel = Question

User = get_user_model()
logger = logging.getLogger(__name__)


QUESTIONNAIRE_TOKEN_SALT = "booking-questionnaire-v1"
QUESTIONNAIRE_QUESTIONS_SALT = "booking-questionnaire-questions-v1"


def _questionnaire_token_for_booking_id(booking_id: int) -> str:
    # Token is deterministic for the booking id (no DB field needed).
    return signing.dumps(int(booking_id), salt=QUESTIONNAIRE_TOKEN_SALT)


def _is_valid_questionnaire_token(booking_id: int, token: str | None) -> bool:
    if not token:
        return False
    try:
        payload = signing.loads(token, salt=QUESTIONNAIRE_TOKEN_SALT)
    except Exception:
        return False
    return str(payload) == str(booking_id)


def _questionnaire_public_path(booking_id: int) -> str:
    token = _questionnaire_token_for_booking_id(booking_id)
    return f"{reverse('booking_questionnaire', args=[booking_id])}?t={quote_plus(token)}"


def _questionnaire_questions_signature(question_ids: list[int]) -> str:
    # Use a timestamped signature so stale pages naturally expire.
    return signing.dumps([int(x) for x in question_ids], salt=QUESTIONNAIRE_QUESTIONS_SALT)


def _load_questionnaire_question_ids(signature: str | None, *, max_age_seconds: int = 60 * 60 * 24 * 7) -> list[int] | None:
    if not signature:
        return None
    try:
        ids = signing.loads(signature, salt=QUESTIONNAIRE_QUESTIONS_SALT, max_age=max_age_seconds)
    except Exception:
        return None

    if not isinstance(ids, list):
        return None

    out: list[int] = []
    for x in ids:
        try:
            out.append(int(x))
        except Exception:
            return None
    return out


def _generate_qr_data_uri(text: str) -> str:
    """Generate a PNG QR code and return a data URI (base64).

    Falls back to returning an external Google Chart URL if qrcode lib missing.
    """
    try:
        import qrcode
    except Exception:
        # fallback to public QR image generator (api.qrserver.com)
        return f"https://api.qrserver.com/v1/create-qr-code/?size=240x240&data={quote_plus(text)}"

    qr = qrcode.make(text)
    buf = io.BytesIO()
    qr.save(buf, format='PNG')
    data = base64.b64encode(buf.getvalue()).decode('ascii')
    return f"data:image/png;base64,{data}"


def _get_latest_ar_items(request, limit: int = 4):
    """ดึง ARAsset ล่าสุดแบบปลอดภัย (กันกรณีตารางยังไม่ถูกสร้างใน DB จริง).

    ถ้าเกิด OperationalError เช่น "no such table: main_arasset" จะคืนลิสต์ว่าง
    แทนที่จะทำให้หน้าแรกล่มบนโฮสต์จริงที่ยังไม่ได้รัน migrate.
    """
    try:
        items = list(ARAsset.objects.order_by('-updated_at')[:limit])
    except OperationalError:
        return []

    for item in items:
        item.scene_link = _scene_viewer_link(request, item)
    return items

# =====================================================================
# PERMISSION HELPERS
# =====================================================================

def is_speaker(user):
    """ตรวจสอบสิทธิ์วิทยากรให้สม่ำเสมอทั้งระบบ"""
    if not user or not getattr(user, "is_authenticated", False):
        return False

    try:
        if hasattr(user, "profile") and getattr(user.profile, "role", None) == "speaker":
            return True
    except Exception:
        pass

    return (
        user.is_staff
        or user.is_superuser
        or user.groups.filter(name="Speaker").exists()
        or Speaker.objects.filter(user=user).exists()
    )


@login_required
@user_passes_test(is_speaker)
def reject_assignment(request, assignment_id):
    assignment = get_object_or_404(
        SpeakerAssignment,
        assignment_id=assignment_id,
        speaker__user=request.user,
    )

    if assignment.status not in ['pending', 'assigned']:
        messages.warning(request, "ไม่สามารถปฏิเสธงานนี้ได้")
        return redirect(f"{reverse('speaker_dashboard')}#section-pending")

    if request.method == "POST":
        reason = (request.POST.get("reason") or "").strip()

        with transaction.atomic():
            # ✅ เก็บ booking ไว้ก่อนตัดความสัมพันธ์
            booking = assignment.booking

            # 1) เซฟว่า rejected + เก็บเหตุผล

            assignment.status = "rejected"
            assignment.rejected_at = timezone.now()

            # เก็บข้อมูล snapshot ของงานไว้ใน note เผื่อ admin ต้องดูประวัติ
            # (เพราะด้านล่างมีการตัด booking ออกจาก assignment เพื่อให้มอบหมายใหม่ได้)
            if booking:
                booking_line = f"[งาน] Booking #{booking.id} - {getattr(booking, 'fullname', '-') or '-'}"
                if getattr(booking, 'Re_date', None):
                    booking_line += f" | วันที่เข้าชม {booking.Re_date.strftime('%d/%m/%Y')}"

                if assignment.note:
                    assignment.note = assignment.note.rstrip() + "\n"
                else:
                    assignment.note = ""
                assignment.note += booking_line

            if reason:
                if assignment.note:
                    assignment.note = assignment.note.rstrip() + "\n"
                assignment.note = (assignment.note or "") + f"[ปฏิเสธโดยวิทยากร] {reason}"

            # 2) คืนงานให้ผู้ดูแลระบบ: ทำให้ booking กลับไปอยู่สถานะที่รอมอบหมาย
            # (ในระบบคุณใช้ assign แล้ว set confirmed ดังนั้นตอนคืนควรกลับไป approved)
            if booking:
                booking.Re_status = "approved"
                booking.save(update_fields=["Re_status"])

            # 3) ปลด booking ออกจาก assignment เพื่อให้ admin assign ใหม่ได้
            assignment.booking = None
            assignment.save(update_fields=["status", "note", "booking", "rejected_at"])

        messages.success(request, "ปฏิเสธงานเรียบร้อยแล้ว และส่งกลับให้ผู้ดูแลระบบมอบหมายใหม่")
        return redirect(f"{reverse('speaker_dashboard')}#section-pending")

    return render(request, "speaker/reject_assignment.html", {"assignment": assignment})

def is_admin(user):
    """ตรวจสอบว่าเป็นผู้ดูแลระบบหรือไม่"""
    if not user or not getattr(user, 'is_authenticated', False):
        return False
    try:
        return user.is_superuser or (
            hasattr(user, 'profile') and getattr(user.profile, 'role', None) == 'admin'
        )
    except Exception:
        return user.is_superuser


def is_staff_or_admin(user):
    """ตรวจสอบสิทธิ์เจ้าหน้าที่หรือผู้ดูแลระบบ"""
    return user.is_authenticated and (user.is_staff or user.is_superuser)


def _speaker_rejected_today(speaker: Speaker, *, today=None) -> bool:
    """Return True if speaker rejected any assignment today.

    Uses rejected_at when available; falls back to assigned_at for legacy rows
    that predate rejected_at being populated.
    """
    if not speaker:
        return False

    today = today or timezone.localdate()

    day_start = datetime.combine(today, time.min)
    day_end = day_start + timedelta(days=1)

    # Use an explicit [start, end) range instead of __date to avoid backend/timezone quirks.
    if getattr(settings, "USE_TZ", False):
        tz = timezone.get_current_timezone()
        if timezone.is_naive(day_start):
            day_start = timezone.make_aware(day_start, tz)
        if timezone.is_naive(day_end):
            day_end = timezone.make_aware(day_end, tz)

    return (
        SpeakerAssignment.objects.filter(speaker=speaker, status="rejected")
        .filter(
            Q(rejected_at__gte=day_start, rejected_at__lt=day_end)
            | (Q(rejected_at__isnull=True) & Q(assigned_at__gte=day_start, assigned_at__lt=day_end))
        )
        .exists()
    )

# =====================================================================
# UTILITIES
# =====================================================================

def _scene_viewer_link(request, asset) -> str:
    """สร้างลิงก์ Google Scene Viewer สำหรับเปิด AR"""
    if not asset:
        return ""
    if getattr(asset, 'glb', None):
        file_url = asset.glb.url
        # สร้างลิงก์ Scene Viewer ของ Google
        return (
            "https://arvr.google.com/scene-viewer/1.0?"
            f"file={request.build_absolute_uri(file_url)}&"
            f"mode=ar_preferred&title={asset.title}"
        )
    return ""

def _social_context() -> dict:
    """ดึงค่า Setting สำหรับ Social Media"""
    defaults = {
        "FACEBOOK_PAGE_URL": "#",
        "line_id": "@thaisilk",
        "CONTACT_TEL": "0000000000",
        "MAP_URL": "#",
    }
    return {k: getattr(settings, k, d) for k, d in defaults.items()}

def collections_view(request):
    """หน้ารวมลายผ้าไหม"""
    query = request.GET.get('q')

    if query:
        patterns = SilkPattern.objects.filter(
            Q(Si_name__icontains=query) |
            Q(Si_history__icontains=query) |  # ใช้ Si_history แทน description
            Q(Si_ID__icontains=query)        # เพิ่มการค้นหาด้วยรหัสผ้า
        ).order_by('target_index')
    else:
        patterns = SilkPattern.objects.all().order_by('target_index')

    return render(request, 'collections/collections.html', {
        'patterns': patterns,
        'title': 'คลังลายผ้าไหม',
    })





# =====================================================
# ส่วนที่ 1 หมวดหมู่การจัดการผู้ใช้และการเข้าสู่ระบบ
# =====================================================
# =====================================================================
# AUTHENTICATION (LOGIN / LOGOUT)
# =====================================================================

def login_view(request):
    """
    เข้าสู่ระบบ
    """
    if request.user.is_authenticated:
        return redirect('home')

    form = LoginForm()

    if request.method == 'POST':
        form = LoginForm(request.POST)

        if form.is_valid():
            username = form.cleaned_data.get('username')
            password = form.cleaned_data.get('password')

            user = authenticate(
                request,
                username=username,
                password=password
            )

            if user:
                login(request, user)
                messages.success(request, 'เข้าสู่ระบบสำเร็จ')

                if is_staff_or_admin(user):
                    return redirect('admin_dashboard')
                if is_speaker(user):
                    return redirect('speaker_dashboard')

                return redirect('home')

            messages.error(
                request,
                'ชื่อผู้ใช้หรือรหัสผ่านไม่ถูกต้อง'
            )
        else:
            messages.error(
                request,
                'กรุณากรอกข้อมูลให้ถูกต้อง'
            )

    return render(
        request,
        'main/login.html',
        {'form': form}
    )


def logout_view(request):
    """
    ออกจากระบบ
    """
    logout(request)
    messages.info(request, 'ออกจากระบบแล้ว')
    return redirect('home')


# =====================================================================
# REGISTRATION
# =====================================================================

@transaction.atomic
def signup_view(request):
    """
    สมัครสมาชิก
    """
    if request.method == 'POST':
        form = SignUpForm(request.POST)

        if form.is_valid():
            user = form.save()

            # Auto Login หลังสมัคร
            auth_user = authenticate(
                request,
                username=user.username,
                password=form.cleaned_data['password1']
            )
            login(request, auth_user or user)

            messages.success(
                request,
                "สมัครสมาชิกสำเร็จ 🎉"
            )
            return redirect('home')

        messages.error(
            request,
            "ข้อมูลไม่ถูกต้อง กรุณาตรวจสอบอีกครั้ง"
        )
    else:
        form = SignUpForm()

    return render(
        request,
        'main/signup.html',
        {'form': form}
    )


# =====================================================================
# PASSWORD RESET (SIMPLE FLOW)
# =====================================================================

# ในไฟล์ views.py

def forgot_password_view(request):
    """
    ลืมรหัสผ่าน (ยืนยันตัวตนด้วยอีเมล)
    """
    if request.method == "POST":
        # 1. รับค่าจากฟอร์ม HTML (name="email")
        email = request.POST.get('email', '').strip().lower()

        if email:
            # 2. ค้นหา User จาก Email
            user = User.objects.filter(email__iexact=email).first()

            if user:
                # 3. เจอ User -> เก็บ ID ลง Session เพื่อใช้ในหน้าเปลี่ยนรหัส
                request.session["reset_user_id"] = user.id
                messages.success(request, "ยืนยันตัวตนเรียบร้อย โปรดตั้งรหัสผ่านใหม่")
                return redirect("reset_password_simple")
            else:
                messages.error(request, "ไม่พบบัญชีผู้ใช้ที่มีอีเมลนี้")
        else:
            messages.error(request, "กรุณากรอกอีเมล")

    # 4. [สำคัญ] แก้ Path ให้ตรงกับไฟล์ที่สร้างไว้ใน main/templates/main/
    return render(request, "main/forgot_password.html")


def reset_password_view(request, token=None):
    """
    หน้าตั้งรหัสผ่านใหม่ (ใช้ Session ID จากขั้นตอน Forgot Password)
    """
    # ตรวจสอบว่ามี User ID ใน Session ไหม (ถ้าไม่มีแสดงว่าข้ามขั้นตอนมา)
    user_id = request.session.get("reset_user_id")
    if not user_id:
        messages.error(request, "หมดเวลาหรือขั้นตอนไม่ถูกต้อง กรุณาทำรายการใหม่")
        return redirect("forgot_password")

    if request.method == "POST":
        new_pass = request.POST.get("new_password")
        confirm_pass = request.POST.get("confirm_password")

        if new_pass != confirm_pass:
            messages.error(request, "รหัสผ่านทั้งสองช่องไม่ตรงกัน")
        elif len(new_pass) < 8:
            messages.error(request, "รหัสผ่านต้องมีความยาวอย่างน้อย 8 ตัวอักษร")
        else:
            # หา User และเปลี่ยนรหัส
            user = User.objects.filter(id=user_id).first()
            if user:
                user.set_password(new_pass)
                user.save()

                # ล้าง Session และแจ้งเตือน
                del request.session["reset_user_id"]
                messages.success(request, "เปลี่ยนรหัสผ่านสำเร็จ! กรุณาเข้าสู่ระบบ")
                return redirect("login")
            else:
                messages.error(request, "ไม่พบข้อมูลผู้ใช้งาน")

    # [สำคัญ] แก้ Path ตรงนี้จาก museum/... เป็น main/...
    return render(request, "main/reset_password.html")


# =====================================================
# ส่วนที่ 1 หมวดหมู่การจัดการผู้ใช้และการเข้าสู่ระบบ
# =====================================================





# =====================================================
# ส่วนที่ 2 หมวดหมู่หน้าเว็บสาธารณะและข้อมูล
# =====================================================
# =====================================================================
# HOME & STATIC PAGES
# =====================================================================
def home_view(request):
    """หน้าแรก"""
    ar_items = _get_latest_ar_items(request, limit=4)

    # ถ้ามีหลายแถว (เช่น เพิ่มผ่าน /admin/) ให้ใช้แถวล่าสุด
    museum = MuseumProfile.objects.order_by('-id').first()

    return render(request, 'main/base.html', {
        'ar_items': ar_items,
        'museum': museum,
    })


# =====================================================================
# WORKSHOPS (PUBLIC)
# =====================================================================

def workshops_view(request):
    """หน้าแสดงรายการเวิร์กช็อป"""
    from django.core.paginator import Paginator

    # คีย์เวิร์ดสำหรับค้นหา
    query = (request.GET.get('q') or '').strip()

    today = (
        timezone.localdate()
        if hasattr(timezone, 'localdate')
        else timezone.now().date()
    )

    # Staff/Admin เห็นทั้งหมด
    show_all = (
        request.user.is_authenticated
        and is_staff_or_admin(request.user)
    )

    if show_all:
        qs = Workshop.objects.all()
    else:
        # สำหรับผู้ใช้ทั่วไป: แสดงเฉพาะกิจกรรมที่ยังเปิดอยู่และยังไม่หมดช่วงเวลา
        qs = Workshop.objects.filter(
            is_active=True
        ).filter(
            Q(start_date__gte=today)
            | Q(end_date__gte=today)
            | Q(start_date__isnull=True)
        )

    # ถ้ามีการค้นหา ให้กรองตามชื่อ/คำอธิบาย/สถานที่
    if query:
        qs = qs.filter(
            Q(title__icontains=query)
            | Q(description__icontains=query)
            | Q(location__icontains=query)
        )

    qs = qs.order_by('start_date')

    paginator = Paginator(qs, 6)
    page_obj = paginator.get_page(
        request.GET.get('page')
    )

    context = {
        'workshops': page_obj.object_list,
        'is_paginated': page_obj.has_other_pages(),
        'page_obj': page_obj,
        'title': 'Workshops & Events',
    }
    context.update(_social_context())

    return render(
        request,
        'workshops/workshops.html',
        context
    )

def workshops_list_view(request):
    workshop_id = request.GET.get('workshop_id')
    workshop_main = get_object_or_404(Workshop, id=workshop_id)

    # ดึงข้อมูลจาก WorkshopBooking (ซึ่งคือ "รอบ" ของกิจกรรม)
    # หากกิจกรรมถูกปิดไม่ให้จอง (is_active=False) ไม่ต้องแสดงรอบให้เลือก
    if workshop_main.is_active:
        rounds = WorkshopBooking.objects.filter(
            workshop=workshop_main,
            date__gte=timezone.localdate()
        ).order_by('date')
    else:
        rounds = WorkshopBooking.objects.none()

    gallery_images = workshop_main.gallery_images.all()

    return render(request, 'workshops/workshops_list.html', {
        'workshop': workshop_main,
        'rounds': rounds,  # ส่ง 'rounds' ไปแสดงผลใน HTML
        'gallery_images': gallery_images,
    })
# =====================================================
# ส่วนที่ 2 หมวดหมู่หน้าเว็บสาธารณะและข้อมูล
# =====================================================





# =====================================================================
# ส่วนที่ 3 หมวดหมู่ระบบการจอง
# =====================================================================
# =====================================================================
# BOOKING (USER)
# =====================================================================
@login_required
def booking_view(request):
    today = timezone.localdate()

    # --- 1. จัดการวันที่ ---
    selected_date_str = request.GET.get("date") or request.POST.get('Re_date')
    try:
        if selected_date_str:
            target_date = datetime.strptime(selected_date_str, '%Y-%m-%d').date()
        else:
            target_date = today
    except ValueError:
        target_date = today

    # --- 2.1 เช็คว่ารอบของวันนั้นเต็มหรือไม่ (1 คณะต่อ 1 รอบ) ---
    occupied_qs = Booking.objects.filter(Re_date=target_date).exclude(
        Re_status__in=['rejected', 'cancelled']
    )
    is_morning_full = occupied_qs.filter(visit_session='morning').exists()
    is_afternoon_full = occupied_qs.filter(visit_session='afternoon').exists()
    is_day_full = bool(is_morning_full and is_afternoon_full)

    # --- 2. บันทึกข้อมูล (POST) ---
    if request.method == "POST":
        fullname = request.POST.get('fullname')
        email = request.POST.get('email')
        phone = request.POST.get('phone')
        re_quantity = request.POST.get('Re_quantity', 1)
        visit_session = request.POST.get('visit_session')
        selected_ws_ids = request.POST.getlist('workshop_ids')

        try:
            with transaction.atomic():
                # ตรวจสอบว่ามีการเลือกช่วงเวลาแล้วหรือยัง
                if not visit_session:
                    raise ValueError("กรุณาเลือกช่วงเวลาเข้าชม (ช่วงเช้าหรือช่วงบ่าย)")

                # จำกัด 1 งานต่อช่วงเวลา/วัน (เช้า 1 บ่าย 1)
                session_conflict = Booking.objects.filter(
                    Re_date=target_date,
                    visit_session=visit_session
                ).exclude(Re_status__in=['rejected', 'cancelled']).exists()
                if session_conflict:
                    if visit_session == 'morning':
                        raise ValueError("ช่วงเช้าของวันที่เลือกมีคณะอื่นจองเต็มแล้ว กรุณาเลือกช่วงบ่ายหรือวันอื่น")
                    elif visit_session == 'afternoon':
                        raise ValueError("ช่วงบ่ายของวันที่เลือกมีคณะอื่นจองเต็มแล้ว กรุณาเลือกช่วงเช้าหรือวันอื่น")

                # บันทึกข้อมูลการจองหลัก
                booking = Booking.objects.create(
                    Us_ID=request.user,
                    fullname=fullname,
                    email=email,
                    phone=phone,
                    Re_date=target_date, # ใช้ target_date ที่เป็น object date แล้ว
                    visit_session=visit_session,
                    Re_quantity=re_quantity,
                    Re_status='pending'
                )

                if selected_ws_ids:
                    for ws_id in selected_ws_ids:
                        workshop_obj = Workshop.objects.select_for_update().get(id=ws_id)

                        # ตรวจสอบจำนวนผู้เข้าร่วม (นับจากจำนวนคนที่จองจริง)
                        current_bookings = WorkshopBooking.objects.filter(
                            workshop=workshop_obj,
                            date=target_date
                        ).count()

                        if current_bookings < workshop_obj.max_participants:
                            WorkshopBooking.objects.create(
                                booking=booking, # <--- สำคัญมาก: ควรเชื่อมกับ Booking หลัก
                                workshop=workshop_obj,
                                user=request.user,
                                date=target_date
                            )
                        else:
                            # ถ้าเต็มให้ Raise Error เพื่อให้ transaction.atomic ทำการ Rollback ข้อมูล Booking ที่สร้างไปก่อนหน้า
                            raise ValueError(f"กิจกรรม {workshop_obj.title} ในวันที่เลือกเต็มแล้ว")

                # ✅ สร้าง QR สำหรับแบบประเมินผูกกับการจองนี้ทันที (หลัง commit)
                transaction.on_commit(lambda: _ensure_booking_qr(request, booking))

                # ถ้าผ่านหมดถึงจะ Success
                messages.success(request, "บันทึกข้อมูลการจองเรียบร้อยแล้ว!")
                return redirect('/user/dashboard/?section=booking')

        except ValueError as e:
            messages.error(request, str(e))
        except Exception as e:
            messages.error(request, f"เกิดข้อผิดพลาดทางระบบ: {str(e)}")

    # --- 3. เตรียมข้อมูลแสดงผล (GET) ---
    # (ส่วนนี้คงเดิมตามที่คุณเขียนไว้ได้เลยครับ)
    user_initial_data = {
        'fullname': f"{request.user.first_name} {request.user.last_name}".strip() or request.user.username,
        'email': request.user.email,
        'phone': getattr(request.user.profile, 'phone', '') if hasattr(request.user, 'profile') else '',
    }

    # แสดงเฉพาะกิจกรรมที่เปิดให้จอง (is_active=True)
    # ไม่จำกัดด้วยช่วงวันที่ start_date / end_date เพื่อให้กิจกรรมเปิดได้ตลอด
    available_workshops = Workshop.objects.filter(
        is_active=True
    ).order_by('start_time')

    return render(request, "booking/booking.html", {
        "user_initial": user_initial_data,
        "preselect_date": target_date.strftime('%Y-%m-%d'),
        "preselect_session": request.POST.get('visit_session', ''),
        "today": today.strftime('%Y-%m-%d'),
        "all_workshops": available_workshops,
        "is_morning_full": is_morning_full,
        "is_afternoon_full": is_afternoon_full,
        "is_day_full": is_day_full,
    })


@login_required
def booking_edit_view(request, booking_id):
    """ให้ผู้ใช้งานแก้ไขข้อมูลการจองได้ เฉพาะก่อนผู้ดูแลระบบยืนยัน (สถานะ pending เท่านั้น)"""
    booking = get_object_or_404(Booking, pk=booking_id, Us_ID=request.user)

    if getattr(booking, "Re_status", None) != "pending":
        messages.error(request, "ไม่สามารถแก้ไขการจองได้ เนื่องจากผู้ดูแลระบบได้ยืนยันการจองแล้ว")
        return redirect('/user/dashboard/?section=booking')

    today = timezone.localdate()

    if request.method == "POST":
        fullname = (request.POST.get('fullname') or "").strip()
        email = (request.POST.get('email') or "").strip()
        phone = (request.POST.get('phone') or "").strip()
        visit_session = (request.POST.get('visit_session') or "").strip()
        selected_ws_ids = request.POST.getlist('workshop_ids')

        re_quantity_raw = request.POST.get('Re_quantity', 1)
        try:
            re_quantity = int(re_quantity_raw)
        except (TypeError, ValueError):
            re_quantity = 1

        selected_date_str = request.POST.get('Re_date')
        try:
            target_date = datetime.strptime(selected_date_str, '%Y-%m-%d').date() if selected_date_str else today
        except ValueError:
            target_date = today

        try:
            with transaction.atomic():
                if not visit_session:
                    raise ValueError("กรุณาเลือกช่วงเวลาเข้าชม (ช่วงเช้าหรือช่วงบ่าย)")

                # จำกัด 1 งานต่อช่วงเวลา/วัน (เช้า 1 บ่าย 1) โดยต้องไม่ชนกับรายการอื่น (ยกเว้นตัวเอง)
                session_conflict = (
                    Booking.objects.filter(Re_date=target_date, visit_session=visit_session)
                    .exclude(pk=booking.pk)
                    .exclude(Re_status__in=['rejected', 'cancelled'])
                    .exists()
                )
                if session_conflict:
                    if visit_session == 'morning':
                        raise ValueError("ช่วงเช้าของวันที่เลือกมีคณะอื่นจองเต็มแล้ว กรุณาเลือกช่วงบ่ายหรือวันอื่น")
                    elif visit_session == 'afternoon':
                        raise ValueError("ช่วงบ่ายของวันที่เลือกมีคณะอื่นจองเต็มแล้ว กรุณาเลือกช่วงเช้าหรือวันอื่น")
                    raise ValueError("ช่วงเวลาที่เลือกมีผู้จองเต็มแล้ว กรุณาเลือกช่วงเวลาอื่น")

                booking.fullname = fullname
                booking.email = email
                booking.phone = phone
                booking.Re_date = target_date
                booking.visit_session = visit_session
                booking.Re_quantity = max(1, re_quantity)
                booking.save(update_fields=[
                    "fullname", "email", "phone",
                    "Re_date", "visit_session", "Re_quantity",
                ])

                # อัปเดตรายการ Workshop ที่ผูกกับ Booking นี้
                WorkshopBooking.objects.filter(booking=booking).delete()
                if selected_ws_ids:
                    for ws_id in selected_ws_ids:
                        workshop_obj = Workshop.objects.select_for_update().get(id=ws_id)
                        current_bookings = WorkshopBooking.objects.filter(
                            workshop=workshop_obj,
                            date=target_date
                        ).count()

                        if current_bookings < workshop_obj.max_participants:
                            WorkshopBooking.objects.create(
                                booking=booking,
                                workshop=workshop_obj,
                                user=request.user,
                                date=target_date
                            )
                        else:
                            raise ValueError(f"กิจกรรม {workshop_obj.title} ในวันที่เลือกเต็มแล้ว")

            messages.success(request, "แก้ไขข้อมูลการจองเรียบร้อยแล้ว!")
            return redirect('/user/dashboard/?section=booking')

        except ValueError as e:
            messages.error(request, str(e))
        except Exception as e:
            messages.error(request, f"เกิดข้อผิดพลาดทางระบบ: {str(e)}")

    # GET หรือ POST ที่มี error: เตรียมข้อมูลแสดงผล
    user_initial_data = {
        'fullname': booking.fullname,
        'email': booking.email,
        'phone': booking.phone or '',
        'Re_quantity': booking.Re_quantity or 1,
    }

    selected_workshop_ids = set(
        str(x) for x in booking.workshop_items.exclude(workshop__isnull=True).values_list('workshop_id', flat=True)
    )

    available_workshops = Workshop.objects.filter(is_active=True).order_by('start_time')

    return render(request, "booking/booking_edit.html", {
        "booking": booking,
        "user_initial": user_initial_data,
        "preselect_date": (booking.Re_date or today).strftime('%Y-%m-%d'),
        "preselect_session": booking.visit_session or "",
        "today": today.strftime('%Y-%m-%d'),
        "all_workshops": available_workshops,
        "selected_workshop_ids": selected_workshop_ids,
    })


# =====================================================================
# BOOKING HISTORY (USER)
# =====================================================================

@login_required
def user_dashboard_view(request):
    section = request.GET.get('section', 'home')
    profile = getattr(request.user, 'profile', None)
    bookings = Booking.objects.filter(Us_ID=request.user).order_by('-Re_date')

    # ✅ ประวัติแบบประเมินการจอง
    # แสดงเป็น "หนึ่งแถวต่อหนึ่งครั้งที่ส่งแบบประเมิน" (submission)
    # และรวมผู้ที่ตอบแบบไม่ต้องล็อกอินผ่าน QR (user = NULL) สำหรับ booking ของ user คนนี้ด้วย
    responses = (
        BookingQuestionResponse.objects
        .filter(booking__Us_ID=request.user)
        .select_related('booking', 'booking__workshop')
        .annotate(score_int=Cast('answer', IntegerField()))   # answer เป็น string -> แปลงเป็น int
        .values('booking_id', 'booking__Re_date', 'booking__workshop__title', 'submission_id')
        .annotate(
            avg_score=Avg('score_int'),
            latest_at=Max('created_at')
        )
        .order_by('-latest_at')
    )

    return render(request, 'user/dashboard.html', {
        'section': section,
        'profile': profile,
        'bookings': bookings,
        'ratings': responses,   # ส่งให้ template ใช้ชื่อตัวเดิมได้เลย
    })



import logging
logger = logging.getLogger("django")

ALLOWED_CONTENT_TYPES = {"image/jpeg", "image/png", "image/webp"}
MAX_UPLOAD_SIZE = 2 * 1024 * 1024  # 2MB

from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect
from django.urls import reverse
from django.core.validators import validate_email
from django.core.exceptions import ValidationError
from django.contrib.auth import get_user_model

User = get_user_model()

@login_required
def user_profile_edit_view(request):
    # ถ้าไม่มีโปรไฟล์ ให้สร้างก่อน
    profile, _ = Profile.objects.get_or_create(user=request.user)

    if request.method == "POST":
        full_name = (request.POST.get("full_name") or "").strip()
        email = (request.POST.get("email") or "").strip().lower()
        phone = (request.POST.get("phone") or "").strip()
        new_image = request.FILES.get("image")

        logger.info(f"[PROFILE_EDIT] POST keys: {list(request.POST.keys())}")
        logger.info(f"[PROFILE_EDIT] FILES keys: {list(request.FILES.keys())}")
        logger.info(f"[PROFILE_EDIT] new_image: {new_image}")

        # =========================
        # 1) อัปเดต Profile fields
        # =========================
        profile.full_name = full_name
        profile.phone = phone

        # =========================
        # 2) อัปเดต User name (optional)
        # =========================
        try:
            if full_name:
                parts = full_name.split()
                request.user.first_name = parts[0] if parts else ""
                request.user.last_name = " ".join(parts[1:]) if len(parts) > 1 else ""
                request.user.save(update_fields=["first_name", "last_name"])
        except Exception as e:
            logger.warning(f"[PROFILE_EDIT] Failed to sync name to User: {e}")

        # =========================
        # 3) อัปเดต Email (User.email)
        # =========================
        if email:
            try:
                validate_email(email)
            except ValidationError:
                messages.error(request, "รูปแบบอีเมลไม่ถูกต้อง")
                return redirect(f"{reverse('user_dashboard')}?section=profile")

            # กัน email ซ้ำกับคนอื่น
            if User.objects.filter(email__iexact=email).exclude(pk=request.user.pk).exists():
                messages.error(request, "อีเมลนี้ถูกใช้งานแล้ว กรุณาใช้อีเมลอื่น")
                return redirect(f"{reverse('user_dashboard')}?section=profile")

            # เซฟเฉพาะตอนเปลี่ยนจริง
            if email != ((request.user.email or "").strip().lower()):
                request.user.email = email
                try:
                    request.user.save(update_fields=["email"])
                except Exception as e:
                    logger.error(f"[PROFILE_EDIT] Failed to save user email: {e}")
                    messages.error(request, "เกิดข้อผิดพลาดขณะบันทึกอีเมล โปรดลองใหม่")
                    return redirect(f"{reverse('user_dashboard')}?section=profile")

        # =========================
        # 4) รูปโปรไฟล์
        # =========================
        if new_image:
            content_type = getattr(new_image, "content_type", "") or ""
            if content_type not in ALLOWED_CONTENT_TYPES:
                messages.error(request, "รองรับเฉพาะไฟล์รูป JPG/PNG/WEBP เท่านั้น")
                return redirect(f"{reverse('user_dashboard')}?section=profile")

            if new_image.size > MAX_UPLOAD_SIZE:
                messages.error(request, "ไฟล์รูปต้องมีขนาดไม่เกิน 2MB")
                return redirect(f"{reverse('user_dashboard')}?section=profile")

            if profile.image:
                try:
                    profile.image.delete(save=False)
                except Exception as e:
                    logger.warning(f"[PROFILE_EDIT] Failed to delete old image: {e}")

            profile.image = new_image

        # =========================
        # 5) เซฟ Profile
        # =========================
        try:
            fields = ["full_name", "phone"]
            if new_image:
                fields.append("image")
            profile.save(update_fields=fields)
        except Exception as e:
            logger.error(f"[PROFILE_EDIT] Failed to save profile: {e}")
            messages.error(request, "เกิดข้อผิดพลาดขณะบันทึกข้อมูล โปรดลองใหม่หรือติดต่อผู้ดูแลระบบ")
            return redirect(f"{reverse('user_dashboard')}?section=profile")

        messages.success(request, "บันทึกโปรไฟล์เรียบร้อยแล้ว")
        return redirect(f"{reverse('user_dashboard')}?section=profile")

    # GET
    return render(request, "user/profile_edit.html", {"profile": profile})



@login_required
@require_POST
def user_profile_delete_image_view(request):
    profile = get_object_or_404(Profile, user=request.user)

    if profile.image:
        try:
            profile.image.delete(save=False)
        except Exception:
            pass
        profile.image = None
        profile.save(update_fields=["image"])

    messages.success(request, "ลบรูปโปรไฟล์เรียบร้อยแล้ว")
    return redirect(f"{reverse('user_dashboard')}?section=profile")




@login_required
def user_booking_history_view(request):
    bookings = Booking.objects.filter(Us_ID=request.user).order_by('-Re_date')
    return render(request, 'user/booking_history.html', {'bookings': bookings})

@login_required
@require_POST
def booking_cancel_view(request, booking_id):
    booking = get_object_or_404(Booking, pk=booking_id, Us_ID=request.user)

    # ✅ บังคับเหตุผล
    reason = (request.POST.get("cancel_reason") or "").strip()
    if not reason:
        messages.error(request, "กรุณาระบุเหตุผลการยกเลิกก่อนยืนยัน")
        return redirect('user_dashboard')

    # ✅ ยกเลิกได้เฉพาะ pending
    if booking.Re_status != 'pending':
        messages.error(request, "ไม่สามารถยกเลิกการจองที่ได้รับการอนุมัติหรือปฏิเสธแล้วได้")
        return redirect('user_dashboard')

    # ✅ เซฟสถานะ + เหตุผล
    booking.Re_status = 'cancelled'
    booking.cancel_reason = reason
    booking.cancelled_at = timezone.now()
    booking.save(update_fields=['Re_status', 'cancel_reason', 'cancelled_at'])

    messages.success(request, "ยกเลิกการจองเรียบร้อยแล้ว")
    return redirect('user_dashboard')



















# =====================================================================
# BOOKING DETAIL (USER / STAFF)
# =====================================================================

@login_required
def booking_detail_view(request, booking_id):
    """
    รายละเอียดการจอง (เจ้าของหรือ Staff/Admin เท่านั้น)
    """
    booking = get_object_or_404(Booking, pk=booking_id)

    # เจ้าของการจองหรือผู้ดูแลระบบสามารถเข้าดูได้เสมอ
    allowed = False
    if booking.Us_ID == request.user or is_staff_or_admin(request.user):
        allowed = True

    # ให้สิทธิ์วิทยากรที่ถูกมอบหมาย (speaker_assignment) ดูการจองได้ด้วย
    if not allowed:
        assignment = getattr(booking, 'speaker_assignment', None)
        if assignment and getattr(assignment, 'speaker', None) and getattr(assignment.speaker, 'user', None) == request.user:
            allowed = True

    if not allowed:
        messages.error(request, "คุณไม่มีสิทธิ์เข้าถึงข้อมูลการจองนี้")
        return redirect('home')

    # เตรียมข้อมูลแบบประเมิน: มีคำถามเปิดใช้งานไหม และสร้าง QR/URL สำหรับแบบประเมิน
    try:
        questions_exist = QuestionModel.objects.filter(is_active=True).exists()
    except Exception:
        questions_exist = False

    questionnaire_url = None
    qr_data = None
    if questions_exist:
        questionnaire_url = _questionnaire_public_path(booking.id)
        # ให้เป็นลิงก์เต็ม (tokenized สำหรับให้ผู้มาด้วยตอบได้โดยไม่ต้องสมัคร)
        full_q_url = request.build_absolute_uri(_questionnaire_public_path(booking.id))
        # If booking already has a saved QR image, use it; otherwise generate and save one
        qr_data = None
        if getattr(booking, 'qr_code', None) and booking.qr_code and 'questionnaire_v2' in (booking.qr_code.name or ''):
            try:
                qr_url = booking.qr_code.url
            except Exception:
                qr_url = None
            if qr_url:
                qr_data = qr_url

        if not qr_data:
            # generate PNG bytes via qrcode lib
            try:
                import qrcode
                import io as _io
                img = qrcode.make(full_q_url)
                buf = _io.BytesIO()
                img.save(buf, format='PNG')
                buf.seek(0)
                filename = f'booking_{booking.id}_questionnaire_v2.png'
                # save to booking.qr_code
                booking.qr_code.save(filename, ContentFile(buf.read()), save=True)
                qr_data = booking.qr_code.url
            except Exception:
                # fallback to data-uri
                qr_data = _generate_qr_data_uri(full_q_url)

    # ลิงก์ย้อนกลับ: วิทยากรกลับหน้าแผงควบคุม (งานรอดำเนินการ)
    # ผู้ใช้งานกลับหน้าแดชบอร์ด (ประวัติการจอง)
    is_speaker_user = Speaker.objects.filter(user=request.user).exists()
    back_to_history_url = (
        '/speaker/dashboard/#section-pending'
        if is_speaker_user
        else f"{reverse('user_dashboard')}?section=booking"
    )

    current_status = (getattr(booking, "Re_status", None) or "").strip()
    can_decide_booking = bool(is_staff_or_admin(request.user)) and (current_status in ("", "pending"))

    return render(request, 'booking/booking_detail.html', {
        'booking': booking,
        'questionnaire_available': questions_exist,
        'questionnaire_url': questionnaire_url,
        'questionnaire_qr': qr_data,
        'back_to_history_url': back_to_history_url,
        'can_decide_booking': can_decide_booking,
        'current_url': request.get_full_path(),
    })



def booking_questionnaire_view(request, booking_id):
    """แสดง/บันทึกแบบประเมินหลังการเข้าชมสำหรับการจองนั้นๆ"""
    booking = get_object_or_404(Booking, pk=booking_id)

    # Public (QR) access uses a signed token in querystring.
    token = (request.GET.get("t") or request.POST.get("t") or "").strip() or None
    is_privileged = bool(getattr(request.user, "is_authenticated", False)) and is_staff_or_admin(request.user)
    is_owner = bool(getattr(request.user, "is_authenticated", False)) and booking.Us_ID_id == request.user.id
    token_ok = _is_valid_questionnaire_token(booking.id, token)

    # ✅ ตรวจสิทธิ์: เจ้าของการจอง / staff/admin / หรือผู้มี token ถูกต้องจาก QR
    if not (is_owner or is_privileged or token_ok):
        messages.error(request, "ลิงก์แบบประเมินไม่ถูกต้องหรือคุณไม่มีสิทธิ์เข้าถึง")
        return redirect('home')

    # ✅ บังคับว่าต้องปิดงานโดยวิทยากร/เสร็จสิ้นก่อน ถึงทำแบบประเมินได้
    if getattr(booking, "Re_status", None) != "completed" and not is_privileged:
        messages.error(request, "ยังไม่สามารถทำแบบประเมินได้ (รอวิทยากรกดปิดงานก่อน)")
        if getattr(request.user, "is_authenticated", False):
            return redirect('booking_detail', booking_id=booking.id)
        return redirect('home')

    # ✅ ดึง "ชุดคำถาม" ที่จะแสดง/บันทึก
    # IMPORTANT: ใช้ signature จาก GET เพื่อให้แม้ admin เปิด/ปิดคำถามระหว่างทำแบบประเมิน
    # ผู้ใช้ยังส่งได้ตามชุดคำถามที่เห็นตอนเปิดหน้า
    question_sig = None
    questions = None

    # จัดลำดับหมวดคำถาม: ภาพรวมพิพิธภัณฑ์ -> ผ้าไหม -> วิทยากร
    category_order = Case(
        When(category="museum", then=Value(1)),
        When(category="silk", then=Value(2)),
        When(category="speaker", then=Value(3)),
        default=Value(99),
        output_field=IntegerField(),
    )
    if request.method == "POST":
        question_sig = (request.POST.get("qsig") or "").strip() or None
        question_ids = _load_questionnaire_question_ids(question_sig)
        if not question_ids:
            messages.error(request, "แบบฟอร์มหมดอายุหรือไม่ถูกต้อง กรุณาเปิดหน้าแบบประเมินใหม่")
            return redirect(request.path + (f"?t={quote_plus(token)}" if token else ""))
        questions = (
            QuestionModel.objects
            .filter(id__in=question_ids)
            .annotate(_cat_order=category_order)
            .order_by('_cat_order', 'id')
        )
    else:
        questions = (
            QuestionModel.objects
            .filter(is_active=True)
            .annotate(_cat_order=category_order)
            .order_by('_cat_order', 'id')
        )
        question_sig = _questionnaire_questions_signature(list(questions.values_list('id', flat=True)))

    if not questions.exists():
        messages.error(request, "แบบประเมินยังไม่ถูกเปิดใช้งาน")
        if getattr(request.user, "is_authenticated", False):
            return redirect('booking_detail', booking_id=booking.id)
        return redirect('home')

    # -----------------------------
    # POST: validate + save answers
    # -----------------------------
    if request.method == "POST":
        # ✅ 1) ตรวจว่าตอบครบทุกข้อก่อน
        missing = []
        answers = {}

        for q in questions:
            key = f"question_{q.id}"
            val = request.POST.get(key)
            if not val:
                missing.append(q.id)
            else:
                answers[q.id] = val

        if missing:
            messages.error(request, "กรุณาตอบให้ครบทุกข้อก่อนส่งแบบประเมิน")
            # ส่งกลับหน้าเดิม (จะไม่บันทึกอะไรลง DB)
            qr_data = _ensure_booking_qr(request, booking)
            return render(request, "booking/questionnaire.html", {
                "booking": booking,
                "questions": questions,
                "qr_data": qr_data,
                "missing": missing,  # (ถ้าจะเอาไปไฮไลท์ใน template)
                "token": token,
                "question_sig": question_sig,
            })

        # ✅ 1.5) ตรวจว่าเป็นคะแนน 1-5 เท่านั้น (กันแก้ request payload)
        invalid = []
        for qid, val in answers.items():
            if str(val) not in {"1", "2", "3", "4", "5"}:
                invalid.append(qid)

        if invalid:
            messages.error(request, "พบคำตอบที่ไม่ถูกต้อง (คะแนนต้องอยู่ระหว่าง 1–5)")
            qr_data = _ensure_booking_qr(request, booking)
            return render(request, "booking/questionnaire.html", {
                "booking": booking,
                "questions": questions,
                "qr_data": qr_data,
                "missing": [],
                "invalid": invalid,
                "token": token,
                "question_sig": question_sig,
            })

        # ✅ 2) บันทึกทุกครั้งที่ส่งแบบประเมิน (สร้าง record ใหม่ ไม่ทับของเดิม)
        submission_id = uuid.uuid4()
        with transaction.atomic():
            BookingQuestionResponse.objects.bulk_create([
                BookingQuestionResponse(
                    booking=booking,
                    user=request.user if getattr(request.user, "is_authenticated", False) else None,
                    question=q,
                    answer=str(answers[q.id]),
                    submission_id=submission_id,
                )
                for q in questions
            ])

        messages.success(request, "ขอบคุณที่ทำแบบประเมินค่ะ")
        qr_data = _ensure_booking_qr(request, booking)

        return render(request, "booking/questionnaire_thanks.html", {
            "booking": booking,
            "qr_data": qr_data,
        })

    # -----------------------------
    # GET: show questionnaire
    # -----------------------------
    qr_data = _ensure_booking_qr(request, booking)
    return render(request, "booking/questionnaire.html", {
        "booking": booking,
        "questions": questions,
        "qr_data": qr_data,
        "token": token,
        "question_sig": question_sig,
    })


def _ensure_booking_qr(request, booking):
    """สร้าง/ดึง QR ของ booking แบบ persistent"""
    try:
        # Always generate QR for the public tokenized questionnaire URL.
        full_q_url = request.build_absolute_uri(_questionnaire_public_path(booking.id))

        # ถ้ายังไม่มีไฟล์ qr_code หรือเป็น QR แบบเก่า ให้สร้างใหม่แล้ว save
        current_name = getattr(getattr(booking, "qr_code", None), "name", "") or ""
        needs_regen = (not getattr(booking, "qr_code", None)) or ("questionnaire_v2" not in current_name)
        if needs_regen:
            import qrcode
            import io as _io

            img = qrcode.make(full_q_url)
            buf = _io.BytesIO()
            img.save(buf, format="PNG")
            buf.seek(0)
            filename = f"booking_{booking.id}_questionnaire_v2.png"
            booking.qr_code.save(filename, ContentFile(buf.read()), save=True)

        return booking.qr_code.url if booking.qr_code else _generate_qr_data_uri(full_q_url)

    except Exception:
        return _generate_qr_data_uri(request.build_absolute_uri(_questionnaire_public_path(booking.id)))


@login_required
@user_passes_test(is_staff_or_admin)
def booking_responses_admin_view(request):
    """Admin view to inspect booking questionnaire responses and export CSV/PDF."""
    from django.http import HttpResponse
    import csv, datetime

    booking_id = request.GET.get('booking_id')

    # --- PDF Export ต่อการจอง (หนึ่งไฟล์ต่อ booking) ---
    if request.GET.get('export') == 'pdf':
        if not booking_id:
            messages.error(request, "กรุณาเลือกการจองจากหน้าสรุปก่อนดาวน์โหลด PDF")
            return redirect('booking_responses_summary')

        try:
            from reportlab.lib.pagesizes import A4
            from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
            from reportlab.lib import colors
            from reportlab.lib.styles import getSampleStyleSheet
            from reportlab.pdfbase import pdfmetrics
            from reportlab.pdfbase.ttfonts import TTFont
        except ImportError:
            return HttpResponse(
                "ต้องติดตั้งไลบรารี reportlab ก่อนใช้งานฟีเจอร์นี้ (pip install reportlab)",
                content_type="text/plain; charset=utf-8",
            )

        from collections import OrderedDict
        import io

        # รวมข้อมูลคำตอบแบบเดียวกับที่ใช้แสดงในหน้า HTML
        booking = get_object_or_404(Booking, pk=booking_id)
        responses_qs = (
            BookingQuestionResponse.objects
            .filter(booking_id=booking_id)
            .select_related('question', 'user', 'booking')
            .order_by('submission_id', 'user_id', 'question_id', 'created_at')
        )

        question_map = OrderedDict()
        for r in responses_qs:
            if r.question_id not in question_map:
                question_map[r.question_id] = r.question
        questions = list(question_map.values())

        respondent_map = OrderedDict()
        for r in responses_qs:
            if r.submission_id:
                key = f"sub-{r.submission_id}"
            elif r.user_id:
                key = f"user-{r.user_id}"
            else:
                key = f"row-{r.id}"
            if key not in respondent_map:
                respondent_map[key] = {
                    'user': r.user,
                    'answers': {},
                    'latest_at': r.created_at,
                }
            data = respondent_map[key]
            try:
                score_val = int(r.answer)
            except (TypeError, ValueError):
                score_val = None

            if score_val is not None:
                data['answers'][r.question_id] = score_val
            if r.created_at and (data['latest_at'] is None or r.created_at > data['latest_at']):
                data['latest_at'] = r.created_at

        respondent_rows = []
        for data in respondent_map.values():
            ordered_scores = []
            numeric_scores = []
            for q in questions:
                s = data['answers'].get(q.id)
                ordered_scores.append(s)
                if s is not None:
                    numeric_scores.append(s)

            avg_score = round(sum(numeric_scores) / len(numeric_scores), 2) if numeric_scores else None

            respondent_rows.append({
                'user': data['user'],
                'scores': ordered_scores,
                'answered_count': len(numeric_scores),
                'avg_score': avg_score,
                'latest_at': data['latest_at'],
            })

        # ลงทะเบียนฟอนต์ภาษาไทย (ถ้าพบในระบบ)
        import os

        base_font = "Helvetica"
        font_candidates = [
            ("THSarabunNew", "C:/Windows/Fonts/THSarabunNew.ttf"),
            ("THSarabun", "C:/Windows/Fonts/THSarabun.ttf"),
            ("THSarabunPSK", "C:/Windows/Fonts/THSarabunPSK.ttf"),
            ("Tahoma", "C:/Windows/Fonts/tahoma.ttf"),  # มีเกือบทุกเครื่อง และรองรับภาษาไทย
        ]

        for font_name, font_path in font_candidates:
            if os.path.exists(font_path):
                try:
                    pdfmetrics.registerFont(TTFont(font_name, font_path))
                    base_font = font_name
                    break
                except Exception:
                    continue

        buffer = io.BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=A4)
        styles = getSampleStyleSheet()
        # ปรับสไตล์ให้ใช้ฟอนต์ฐานที่รองรับภาษาไทย
        styles['Normal'].fontName = base_font
        styles['Heading2'].fontName = base_font
        story = []

        title = f"สรุปผลแบบประเมิน — การจองลำดับ {booking.id}"
        story.append(Paragraph(title, styles['Heading2']))
        if booking.Re_date:
            story.append(Paragraph(f"วันที่จอง: {booking.Re_date}", styles['Normal']))
        story.append(Spacer(1, 12))

        header = ["ลำดับ", "ผู้ประเมิน"]
        for idx, _q in enumerate(questions, start=1):
            header.append(f"ข้อ {idx}")
        header.extend(["เฉลี่ย", "จำนวนข้อที่ตอบ", "เวลา"])

        data_rows = [header]
        for idx, row in enumerate(respondent_rows, start=1):
            username = getattr(row['user'], 'username', '-') if row['user'] else '-'
            record = [idx, username]
            for score in row['scores']:
                record.append(score if score is not None else '-')
            record.append(row['avg_score'] if row['avg_score'] is not None else '-')
            record.append(row['answered_count'])
            if row['latest_at']:
                record.append(row['latest_at'].strftime('%d/%m/%Y %H:%M'))
            else:
                record.append('-')
            data_rows.append(record)

        table = Table(data_rows, repeatRows=1)
        table_style = [
            ('BACKGROUND', (0, 0), (-1, 0), colors.lightgrey),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.black),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('ALIGN', (1, 0), (1, -1), 'LEFT'),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
            ('FONTSIZE', (0, 0), (-1, -1), 9),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ]
        # ใช้ฟอนต์ฐานสำหรับทั้งตาราง (รองรับภาษาไทย)
        table_style.append(('FONTNAME', (0, 0), (-1, -1), base_font))
        table.setStyle(TableStyle(table_style))

        story.append(table)
        doc.build(story)

        pdf_value = buffer.getvalue()
        buffer.close()

        resp = HttpResponse(content_type='application/pdf')
        resp['Content-Disposition'] = f'attachment; filename="booking_{booking.id}_responses.pdf"'
        resp.write(pdf_value)
        return resp

    # --- CSV Export (ยังคงเผื่อไว้สำหรับการใช้งานเดิม) ---
    if request.GET.get('export') == 'csv':
        resp = HttpResponse(content_type='text/csv')
        resp['Content-Disposition'] = f'attachment; filename="booking_responses_{datetime.date.today()}.csv"'
        writer = csv.writer(resp)
        writer.writerow(['booking_id', 'user', 'question_id', 'question', 'answer', 'created_at'])
        qs = BookingQuestionResponse.objects.select_related('booking', 'question', 'user').all().order_by('booking_id', 'created_at')
        if booking_id:
            qs = qs.filter(booking_id=booking_id)
        for r in qs:
            writer.writerow([
                r.booking.id,
                r.user.username if r.user else '',
                r.question.id,
                r.question.question,
                r.answer,
                r.created_at,
            ])
        return resp

    # ถ้าเลือก booking เฉพาะ ให้สรุปผลแบบ "สรุปต่อคำถาม" สำหรับการจองนั้น ๆ
    if booking_id:
        from collections import OrderedDict, defaultdict
        import statistics

        booking = get_object_or_404(Booking, pk=booking_id)

        # ดึงคำตอบทั้งหมดของ booking นี้
        responses_qs = (
            BookingQuestionResponse.objects
            .filter(booking_id=booking_id)
            .select_related('question', 'user', 'booking')
            .order_by('question_id', 'created_at')
        )

        # เก็บลำดับคำถามตาม id เพื่อใช้เป็นหัวตาราง
        question_order = OrderedDict()
        # เก็บสถิติของแต่ละคำถาม
        stats_per_question = defaultdict(lambda: {
            'question': None,
            'scores': [],
            'respondents': set(),
        })

        for r in responses_qs:
            qid = r.question_id
            qstats = stats_per_question[qid]
            qstats['question'] = r.question
            question_order.setdefault(qid, r.question)

            # เก็บคะแนนเป็นตัวเลข 1-5 (ถ้าแปลงได้)
            try:
                score_val = int(r.answer)
            except (TypeError, ValueError):
                score_val = None

            if score_val is not None:
                qstats['scores'].append(score_val)
            if r.submission_id:
                qstats['respondents'].add(f"sub-{r.submission_id}")
            elif r.user_id:
                qstats['respondents'].add(f"user-{r.user_id}")

        # แปลงเป็น list เรียงตามลำดับคำถาม
        question_stats = []
        for idx, (qid, qobj) in enumerate(question_order.items(), start=1):
            data = stats_per_question[qid]
            scores = data['scores']
            if scores:
                avg_score = round(sum(scores) / len(scores), 2)
                try:
                    stddev = round(statistics.pstdev(scores), 2)
                except Exception:
                    stddev = 0.0
            else:
                avg_score = None
                stddev = None

            question_stats.append({
                'index': idx,
                'question': data['question'],
                'avg_score': avg_score,
                'stddev_score': stddev,
                'respondent_count': len(data['respondents']),
            })

        # จัดกลุ่ม/เรียงตามหมวดคำถาม เพื่อให้อ่านง่าย
        category_order_map = {"museum": 1, "silk": 2, "speaker": 3}
        question_stats.sort(
            key=lambda row: (
                category_order_map.get(getattr(row.get('question'), 'category', None), 99),
                getattr(row.get('question'), 'id', 0) or 0,
            )
        )
        for idx, row in enumerate(question_stats, start=1):
            row['index'] = idx

        return render(request, 'admin_panel/booking/booking_responses.html', {
            'booking': booking,
            'question_stats': question_stats,
        })

    # กรณีไม่ระบุ booking_id ให้แสดงรายการคำตอบแบบเดิม (ล่าสุดก่อน)
    responses_qs = BookingQuestionResponse.objects.select_related('booking', 'question', 'user').order_by('-created_at')
    responses = responses_qs[:1000]
    return render(request, 'admin_panel/booking/booking_responses.html', {
        'responses': responses,
        'booking': None,
    })


@login_required
@user_passes_test(is_staff_or_admin)
def booking_responses_summary_view(request):
    """Show bookings with counts of questionnaire responses and links to view/export per booking."""
    from django.db.models import Count
    from django.utils import timezone

    # อ่านรูปแบบการเรียงลำดับจาก query string
    # - newest: การจองล่าสุดก่อน (ค่าเริ่มต้น)
    # - oldest: การจองเก่าที่สุดก่อน
    order = request.GET.get('order', 'newest')

    base_qs = (
        Booking.objects.annotate(
            response_count=Count('question_responses')
        )
        .filter(response_count__gt=0)
    )

    if order == 'oldest':
        bookings = list(base_qs.order_by('created_at'))
    else:  # 'newest'
        bookings = list(base_qs.order_by('-created_at'))

    # เตรียมสถิติแบบละเอียดจากคำตอบของแบบประเมิน
    # - respondent_count: จำนวนผู้ใช้ที่ทำแบบประเมิน (distinct user)
    # - avg_score / stddev_score: ค่าเฉลี่ยและส่วนเบี่ยงเบนจากคะแนนที่แปลงจากตัวเลือก a-d
    from collections import defaultdict
    # แปลงคำตอบแบบ 1-5 เป็นคะแนนตัวเลข (5 = ดีมาก → 1 = น้อยมาก)
    answer_score = {
        '5': 5,
        '4': 4,
        '3': 3,
        '2': 2,
        '1': 1,
    }

    stats_map = defaultdict(lambda: {
        'respondents': set(),
        'scores': [],
    })
    all_scores = []

    # ดึงคำตอบทั้งหมดของทุก booking มากลุ่มใน Python
    all_responses = BookingQuestionResponse.objects.values('booking_id', 'answer', 'user_id', 'submission_id')
    for r in all_responses:
        bid = r['booking_id']
        stat = stats_map[bid]
        # เก็บผู้ที่ทำแบบประเมิน: นับเป็น "submission" ถ้ามี (รองรับ anonymous) ไม่เช่นนั้น fallback เป็น user
        if r.get('submission_id'):
            stat['respondents'].add(f"sub-{r['submission_id']}")
        elif r.get('user_id'):
            stat['respondents'].add(f"user-{r['user_id']}")
        # แปลง a-d เป็นคะแนนตัวเลข
        score = answer_score.get(r['answer'])
        if score is not None:
            stat['scores'].append(score)
            all_scores.append(score)

    # คำนวณค่าเฉลี่ยและส่วนเบี่ยงเบนต่อ booking แล้วผูกใส่ object
    for b in bookings:
        s = stats_map.get(b.id)
        if not s:
            b.respondent_count = 0
            b.avg_score = None
            b.stddev_score = None
            continue

        scores = s['scores']
        respondents = s['respondents']
        b.respondent_count = len(respondents)

        if scores:
            avg = sum(scores) / len(scores)
            try:
                stddev = statistics.pstdev(scores)
            except Exception:
                stddev = 0.0
            b.avg_score = round(avg, 2)
            b.stddev_score = round(stddev, 2)
        else:
            b.avg_score = None
            b.stddev_score = None

    total_bookings = len(bookings)
    total_respondents = sum(getattr(b, 'respondent_count', 0) or 0 for b in bookings)
    if all_scores:
        avg_all = round(sum(all_scores) / len(all_scores), 2)
    else:
        avg_all = None

    selected_order_label = "ใหม่ล่าสุดก่อน" if order != "oldest" else "เก่าที่สุดก่อน"
    today = timezone.localdate()

    return render(request, 'admin_panel/booking/booking_responses_summary.html', {
        'title': 'ข้อมูลการประเมิน',
        'today': today,
        'now': None,
        'single_container': True,
        'bookings': bookings,
        'order': order,
        'filters': {
            'order': order,
        },
        'selected_order_label': selected_order_label,
        'summary': {
            'total_bookings': total_bookings,
            'total_respondents': total_respondents,
            'avg_score': avg_all,
        }
    })


# =====================================================================
# ส่วนที่ 3 หมวดหมู่ระบบการจอง
# =====================================================================

@login_required
@user_passes_test(is_staff_or_admin)
def approve_bookings_view(request):
    sort = request.GET.get('sort', 'oldest')
    date = request.GET.get('date', '').strip()
    session = request.GET.get('session', '').strip()

    qs = Booking.objects.filter(
        Q(Re_status='pending') | Q(Re_status__isnull=True) | Q(Re_status='')
    )

    if date:
        qs = qs.filter(Re_date=date)

    if session in ('morning', 'afternoon'):
        qs = qs.filter(visit_session=session)

    if sort == 'newest':
        qs = qs.order_by('-created_at', '-id')
    else:
        qs = qs.order_by('created_at', 'id')

    approved_bookings = Booking.objects.filter(Re_status='approved').order_by('-created_at')[:20]

    return render(request, 'admin_panel/booking/approve_bookings.html', {
        'bookings': qs,
        'approved_history': approved_bookings,
        'sort': sort,
        'filter_date': date,
        'filter_session': session,
    })


# =====================================================================
# SPEAKER ASSIGNMENT MANAGEMENT
# =====================================================================

@login_required
@user_passes_test(is_staff_or_admin)
def manage_speakers_view(request):
    """
    รายการ Booking ที่อนุมัติแล้ว แต่ยังไม่ได้มอบหมายวิทยากร
    """
    pending_assignments = Booking.objects.filter(
        Re_status='approved'
    ).filter(
        Q(speaker_assignment__isnull=True) | Q(speaker_assignment__status='rejected')
    ).order_by('Re_date')

    # แสดงเฉพาะวิทยากรที่ยังมีบัญชีผู้ใช้และยังใช้งานได้
    speakers = Speaker.objects.filter(user__isnull=False, user__is_active=True)

    if request.method == 'POST':
        booking_id = request.POST.get('booking_id')
        speaker_id = request.POST.get('speaker_id')

        booking = get_object_or_404(Booking, id=booking_id)
        speaker = get_object_or_404(Speaker, id=speaker_id)

        # ถ้าวิทยากรปฏิเสธงานภายใน "วันนี้" แล้ว จะไม่ให้มอบหมาย "งานของวันนี้" ให้ซ้ำในวันเดียวกัน
        # (แต่ถ้างานเป็นวันอื่น ยังมอบหมายได้)
        today = timezone.localdate()
        if booking.Re_date and booking.Re_date == today and _speaker_rejected_today(speaker):
            messages.warning(request, "ไม่สามารถมอบหมายงานได้ เนื่องจากวิทยากรคนนี้ปฏิเสธงานภายในวันนี้แล้ว")
            return redirect('manage_speakers')

        # จำกัดจำนวนงานต่อวิทยากรต่อวัน (default = 2 งาน/วัน)
        if booking.Re_date:
            max_per_day = getattr(settings, 'SPEAKER_MAX_ASSIGNMENTS_PER_DAY', 2)
            try:
                max_per_day = int(max_per_day)
            except (TypeError, ValueError):
                max_per_day = 2
            if max_per_day < 1:
                max_per_day = 1

            active_statuses = ['pending', 'assigned', 'accepted', 'confirmed']
            active_count = (
                SpeakerAssignment.objects.filter(
                    speaker=speaker,
                    booking__Re_date=booking.Re_date,
                    status__in=active_statuses,
                )
                .exclude(booking=booking)
                .count()
            )
            if active_count >= max_per_day:
                messages.warning(request, f'ไม่สามารถมอบหมาย: วิทยากร {speaker.name} มีงานเต็มในวันที่ {booking.Re_date.strftime("%d %b %Y")}')
                return redirect('manage_speakers')

        schedule_text = ''
        if booking.Re_date:
            schedule_text = f"วันที่เข้าชม {booking.Re_date.strftime('%d/%m/%Y')}"

        SpeakerAssignment.objects.create(
            booking=booking,
            speaker=speaker,
            status='assigned',
            title=f"งาน Booking #{booking.id} ({booking.fullname})",
            schedule_text=schedule_text,
        )

        messages.success(
            request,
            f'มอบหมายคุณ {speaker.name} ดูแลการจองของ {booking.fullname} เรียบร้อยแล้ว'
        )
        return redirect('manage_speakers')

    return render(request, 'admin_panel/speakers/manage_speakers.html', {
        'pending_assignments': pending_assignments,
        'speakers': speakers,
        'title': 'จัดการวิทยากร',
    })

@login_required
@user_passes_test(is_staff_or_admin)
def speaker_assign_from_booking_view(request, booking_id):
    """
    มอบหมายวิทยากรจากหน้า Booking โดยตรง
    """
    booking = get_object_or_404(Booking, id=booking_id)
    # แสดงเฉพาะวิทยากรที่ยังมีบัญชีผู้ใช้และยังใช้งานได้
    speakers = Speaker.objects.filter(user__isnull=False, user__is_active=True).order_by('name')

    # Speaker availability (จำกัดจำนวนงานต่อวิทยากรต่อวัน; default = 2 งาน/วัน)
    full_speaker_ids = []
    rejected_today_speaker_ids = []
    try:
        if booking.Re_date:
            max_per_day = getattr(settings, 'SPEAKER_MAX_ASSIGNMENTS_PER_DAY', 2)
            try:
                max_per_day = int(max_per_day)
            except (TypeError, ValueError):
                max_per_day = 2
            if max_per_day < 1:
                max_per_day = 1

            active_statuses = ['pending', 'assigned', 'accepted', 'confirmed']
            full_speaker_ids = list(
                SpeakerAssignment.objects.filter(
                    booking__Re_date=booking.Re_date,
                    status__in=active_statuses,
                )
                .exclude(booking=booking)
                .values('speaker_id')
                .annotate(c=Count('assignment_id'))
                .filter(c__gte=max_per_day)
                .values_list('speaker_id', flat=True)
            )

            today = timezone.localdate()
            if booking.Re_date == today:
                day_start = datetime.combine(today, time.min)
                day_end = day_start + timedelta(days=1)
                if getattr(settings, "USE_TZ", False):
                    tz = timezone.get_current_timezone()
                    if timezone.is_naive(day_start):
                        day_start = timezone.make_aware(day_start, tz)
                    if timezone.is_naive(day_end):
                        day_end = timezone.make_aware(day_end, tz)

                rejected_today_speaker_ids = list(
                    SpeakerAssignment.objects.filter(status="rejected")
                    .filter(
                        Q(rejected_at__gte=day_start, rejected_at__lt=day_end)
                        | (Q(rejected_at__isnull=True) & Q(assigned_at__gte=day_start, assigned_at__lt=day_end))
                    )
                    .values_list('speaker_id', flat=True)
                    .distinct()
                )
    except Exception:
        full_speaker_ids = []
        rejected_today_speaker_ids = []

    if request.method == 'POST':
        # --- จุดที่แก้ไข 1: เปลี่ยนจาก 'speaker_id' เป็น 'speaker' ให้ตรงกับ name ใน HTML ---
        speaker_id = request.POST.get('speaker')

        # ดึง Object วิทยากร
        speaker = get_object_or_404(Speaker, id=speaker_id)

        # ถ้าวิทยากรปฏิเสธงานภายใน "วันนี้" แล้ว จะไม่ให้มอบหมาย "งานของวันนี้" ให้ซ้ำในวันเดียวกัน
        # (แต่ถ้างานเป็นวันอื่น ยังมอบหมายได้)
        today = timezone.localdate()
        if booking.Re_date and booking.Re_date == today and _speaker_rejected_today(speaker):
            messages.warning(request, "ไม่สามารถมอบหมายงานได้ เนื่องจากวิทยากรคนนี้ปฏิเสธงานภายในวันนี้แล้ว")
            return redirect('speaker_assign_from_booking', booking_id=booking.id)

        # รับค่าเพิ่มเติมจากฟอร์ม (ถ้ามี)
        title = request.POST.get('title')
        quantity = request.POST.get('quantity', '1 ท่าน')
        schedule_text = request.POST.get('schedule_text', '')
        note = request.POST.get('note', '')

        try:
            with transaction.atomic():
                # จำกัดจำนวนงานต่อวิทยากรต่อวัน (default = 2 งาน/วัน)
                if booking.Re_date:
                    max_per_day = getattr(settings, 'SPEAKER_MAX_ASSIGNMENTS_PER_DAY', 2)
                    try:
                        max_per_day = int(max_per_day)
                    except (TypeError, ValueError):
                        max_per_day = 2
                    if max_per_day < 1:
                        max_per_day = 1

                    active_statuses = ['pending', 'assigned', 'accepted', 'confirmed']
                    active_count = (
                        SpeakerAssignment.objects.filter(
                            speaker=speaker,
                            booking__Re_date=booking.Re_date,
                            status__in=active_statuses,
                        )
                        .exclude(booking=booking)
                        .count()
                    )
                    if active_count >= max_per_day:
                        messages.warning(request, f'ไม่สามารถมอบหมาย: วิทยากร {speaker.name} มีงานเต็มในวันที่ {booking.Re_date.strftime("%d %b %Y")}')
                        return redirect('speaker_assign_from_booking', booking_id=booking.id)

                # --- จุดที่แก้ไข 2: ปรับให้ตรงกับ Model SpeakerAssignment ล่าสุด ---
                assignment, created = SpeakerAssignment.objects.update_or_create(
                    booking=booking,
                    defaults={
                        'speaker': speaker,
                        'status': 'assigned',
                        'title': title or f"งาน Booking #{booking.id} ({booking.fullname})",
                        'quantity': quantity,
                        'schedule_text': schedule_text,
                        'note': note,
                    }
                )

                # อัปเดตสถานะการจอง (ถ้าต้องการ)
                booking.Re_status = 'confirmed'
                # บันทึกผู้ดำเนินการและเวลา (เพื่อให้หน้า booking detail แสดงผู้อนุมัติ/วันที่อนุมัติ)
                if not booking.decided_by_id:
                    booking.decided_by = request.user
                if not booking.decided_at:
                    booking.decided_at = timezone.now()

                booking.save(update_fields=['Re_status', 'decided_by', 'decided_at'])

                messages.success(
                    request,
                    f'มอบหมายงานให้คุณ {speaker.name} เรียบร้อยแล้ว'
                )
                # เช็คชื่อ URL ใน redirect ให้ตรงกับ urls.py ของคุณ (เช่น 'approve_bookings')
                return redirect('manage_speakers')

        except Exception as e:
            messages.error(request, f'เกิดข้อผิดพลาด: {e}')

    return render(request, 'admin_panel/booking/speaker_assign_from_booking.html', {
        'booking': booking,
        'speakers': speakers,
        'full_speaker_ids': full_speaker_ids,
        'rejected_today_speaker_ids': rejected_today_speaker_ids,
    })


@login_required
@user_passes_test(is_staff_or_admin)
def speaker_assignment_history_view(request):
    """หน้าประวัติการมอบหมายวิทยากรสำหรับแอดมิน"""
    assignments = (
        SpeakerAssignment.objects.select_related('speaker', 'booking')
        .order_by('-assigned_at', '-assignment_id')
    )

    return render(request, 'admin_panel/speakers/assignment_history.html', {
        'assignments': assignments,
    })

# =====================================================================
# QUESTION / CONTENT MANAGEMENT
# =====================================================================

@login_required
@user_passes_test(is_staff_or_admin)
def manage_questions_view(request):
    """รายการคำถามทั้งหมด"""
    questions = Question.objects.all().order_by('-created_at')
    return render(request, 'admin_panel/Question/admin_questions.html', {
        'questions': questions
    })


def question_rate_view(request, question_id):
    """หน้าสำหรับประเมินหัวข้อคำถามแบบ 5-4-3-2-1 และแสดงสถิติแบบง่ายๆ"""
    question = get_object_or_404(Question, pk=question_id)

    if request.method == 'POST':
        form = SurveyRatingForm(request.POST)
        if form.is_valid():
            sr = form.save(commit=False)
            sr.question = question
            if request.user.is_authenticated:
                sr.user = request.user
            sr.rating = int(form.cleaned_data['rating'])
            sr.save()
            messages.success(request, 'ขอบคุณสำหรับการประเมิน')
            return redirect('question_rate', question_id=question.id)
    else:
        form = SurveyRatingForm()

    qs = SurveyRating.objects.filter(question=question)
    ratings = [r.rating for r in qs if r.rating is not None]
    count = len(ratings)
    avg = None
    stddev = None
    if count > 0:
        avg = sum(ratings) / count
        try:
            stddev = statistics.pstdev(ratings)
        except Exception:
            stddev = 0.0

    suggestions_qs = qs.exclude(comment='').order_by('-created_at')
    suggestions_count = suggestions_qs.count()
    suggestions = [s.comment for s in suggestions_qs[:10]]

    return render(request, 'main/question_rate.html', {
        'question': question,
        'form': form,
        'count': count,
        'avg': round(avg, 2) if avg is not None else None,
        'stddev': round(stddev, 2) if stddev is not None else None,
        'suggestions_count': suggestions_count,
        'suggestions': suggestions,
    })


# =====================================================================
# MUSEUM PROFILE MANAGEMENT
# =====================================================================


def _sanitize_upload_error_text(text: str) -> str:
    # Avoid leaking any credentials that might appear in exception messages.
    if not text:
        return ""
    text = re.sub(r"cloudinary://[^\s]+", "cloudinary://***", text)
    text = re.sub(r"(?i)(api_secret\s*[:=]\s*)([^\s,;]+)", r"\1***", text)
    text = re.sub(r"(?i)(CLOUDINARY_URL\s*[:=]\s*)([^\s,;]+)", r"\1***", text)
    return text


def _classify_upload_error(e: Exception) -> str:
    msg = (str(e) or "").strip()
    low = msg.lower()

    if any(x in low for x in ["invalid signature", "unauthorized", "forbidden", "401", "403", "api key"]):
        return "ตรวจสอบค่า CLOUDINARY_URL / API Key / API Secret"
    if any(x in low for x in ["timeout", "timed out", "read timed out", "connection aborted", "connectionerror"]):
        return "เชื่อมต่อบริการอัปโหลดไม่สำเร็จ (timeout/เครือข่าย)"
    if any(x in low for x in ["too large", "413", "request entity too large"]):
        return "ไฟล์มีขนาดใหญ่เกินไป"
    if any(x in low for x in ["permission denied", "read-only file system", "readonly"]):
        return "เซิร์ฟเวอร์ไม่มีสิทธิ์เขียนไฟล์"

    if msg:
        return _sanitize_upload_error_text(msg)[:180]
    return "เกิดข้อผิดพลาดระหว่างอัปโหลด/บันทึกรูปภาพ"

@login_required
@user_passes_test(is_admin)
def admin_edit_museum_view(request):
    # ถ้ามีหลายแถว (เช่น เพิ่มผ่าน /admin/) ให้แก้ไขแถวล่าสุด
    museum = MuseumProfile.objects.order_by('-id').first()

    if request.method == 'POST':
        form = MuseumProfileForm(
            request.POST,
            request.FILES,
            instance=museum
        )

        if form.is_valid():
            try:
                form.save()
            except Exception as e:
                # Typically Cloudinary/network/storage errors. Don't crash the page.
                logger.exception(
                    "[MUSEUM_EDIT] Failed to save MuseumProfile for user=%s files=%s err=%s",
                    getattr(request.user, "username", None),
                    list(getattr(request, "FILES", {}).keys()),
                    e,
                )

                storage_label = "Cloudinary" if getattr(settings, "USE_CLOUDINARY", False) else "Local storage"
                hint = _classify_upload_error(e)

                # Try to salvage non-file fields so admin doesn't lose edits.
                try:
                    museum_obj = form.save(commit=False)
                    file_fields = ["logo", "hero_image", "gallery_image1", "gallery_image2", "gallery_image3"]
                    for f in file_fields:
                        if museum is not None:
                            setattr(museum_obj, f, getattr(museum, f))
                        else:
                            setattr(museum_obj, f, None)
                    museum_obj.save()
                    messages.warning(
                        request,
                        f"บันทึกข้อมูลสำเร็จ แต่บันทึกรูปภาพไม่สำเร็จ ({storage_label}: {hint})",
                    )
                    return redirect('admin_editmuseum')
                except Exception:
                    pass

                messages.error(
                    request,
                    f"บันทึกข้อมูล/รูปภาพไม่สำเร็จ ({storage_label}: {hint})",
                )
            else:
                messages.success(
                    request,
                    "บันทึกข้อมูลพิพิธภัณฑ์เรียบร้อยแล้ว"
                )
                # ใช้ชื่อ URL ให้ตรงกับ main/urls.py และ templates
                return redirect('admin_editmuseum')
        else:
            logger.warning(
                "MuseumProfileForm invalid for user=%s errors=%s",
                getattr(request.user, "username", None),
                form.errors,
            )
            messages.error(
                request,
                "ข้อมูลไม่ถูกต้อง กรุณาตรวจสอบอีกครั้ง"
            )
    else:
        form = MuseumProfileForm(instance=museum)

    return render(request, 'admin_panel/museum/admin_editmuseum.html', {
        'form': form,
        'museum': museum,
        'title': 'จัดการข้อมูลพิพิธภัณฑ์',
    })


# =====================================================================
# SILK PATTERN MANAGEMENT
# =====================================================================

@login_required
@user_passes_test(is_staff_or_admin)
def manage_silk_patterns_view(request):
    """หน้ารายการลายผ้าไหม"""
    from collections import defaultdict
    patterns = SilkPattern.objects.all().order_by('target_file', 'target_index')
    grouped_patterns = defaultdict(list)
    for p in patterns:
        grouped_patterns[p.target_file or 'ไม่ระบุไฟล์ .mind'].append(p)
    # ส่งเป็น list of tuples เพื่อให้วนใน template ได้ง่าย
    grouped_patterns = list(grouped_patterns.items())
    return render(request, 'admin_panel/Silk/manage_silk.html', {
        'grouped_patterns': grouped_patterns,
        'patterns': patterns,  # เผื่อ template ใช้ตัวเดิม
    })

# =====================================================================
# ส่วนที่ 4 หมวดหมู่จัดการหลังบ้านสำหรับ Admin
# =====================================================================






# =====================================================================
# ส่วนที่ 5 หมวดหมู่ API และ AJAX
# =====================================================================

def ajax_workshops_by_date_view(request):
    """
    API สำหรับดึงข้อมูล Workshop ตามวันที่ที่เลือก
    Return JSON: { workshops: [ {id, title, remaining}, ... ] }
    """
    date_str = request.GET.get('date')
    if not date_str:
        return JsonResponse({'workshops': []})

    # หากิจกรรมที่มีการจัดในวันที่เลือก (เทียบกับ start_date)
    # และสถานะต้องเป็น active
    workshops = Workshop.objects.filter(
        start_date=date_str,
        is_active=True
    )

    data = []
    for ws in workshops:
        # คำนวณที่นั่งที่ถูกจองไปแล้ว
        # (นับจำนวน WorkshopBooking ที่จองเข้ามาในกิจกรรมนี้)
        booked_count = WorkshopBooking.objects.filter(workshop=ws).count()
        remaining = ws.max_participants - booked_count

        # ส่งกลับเฉพาะกิจกรรมที่ยังมีที่นั่งว่าง
        if remaining > 0:
            data.append({
                'id': ws.id,
                'title': ws.title,
                'remaining': remaining
            })

    return JsonResponse({'workshops': data})

def booking_list_api(request):
    qs = Booking.objects.order_by('-Re_date')[:50]
    data = [{'id': b.id, 'fullname': b.fullname, 'status': b.Re_status} for b in qs]
    return JsonResponse({'bookings': data})


# =====================================================================
# ส่วนที่ 5 หมวดหมู่ API และ AJAX
# =====================================================================





# =====================================================================
# ส่วนที่ 6 หมวดหมู่ระบบผ้าไหม AR
# =====================================================================
# =====================================================================
# SILK PATTERN : DETAIL & COLLECTION
# =====================================================================

def silk_detail_view(request, pk):
    """
    หน้าแสดงรายละเอียดลายผ้า
    รองรับ pk / target_index / Si_ID
    """
    pk_str = str(pk).strip()
    silk = None

    if pk_str.isdigit():
        val = int(pk_str)
        silk = (
            SilkPattern.objects.filter(pk=val).first()
            or SilkPattern.objects.filter(
                target_index=val
            ).first()
        )
    else:
        silk = SilkPattern.objects.filter(
            Si_ID=pk_str
        ).first()

    if not silk:
        raise Http404(
            f"ไม่พบข้อมูลลายผ้า: {pk_str}"
        )

    ratings = (
        SilkPatternRating.objects
        .filter(silk=silk)
        .order_by('-created_at')
    )

    avg_score = 0
    # (ถ้ามี logic คำนวณคะแนน ใส่เพิ่มตรงนี้)

    # หาไฟล์โมเดล 3 มิติ สำหรับแสดง AR (ลำดับค้นหา)
    # 1) ฟิลด์ `model_3d` ของ SilkPattern
    # 2) ARAsset ที่มี slug ตรงกับ Si_ID หรือ Si_name
    # 3) ARShowcase ที่มี target_index ตรงกับ silk.target_index
    # 4) ค้นหาไฟล์ .glb ในโฟลเดอร์ media/ar_showcase/glb หรือ media/ar_models โดยใช้ชื่อไฟล์ที่มี Si_ID หรือชื่อ
    ar_model = {'src': None, 'usdz': None}

    # 1) ใช้ model_3d ถ้ามี
    try:
        if getattr(silk, 'model_3d') and getattr(silk.model_3d, 'url', None):
            ar_model['src'] = silk.model_3d.url
    except Exception:
        pass

    # 2) ตรวจ ARAsset
    if not ar_model['src']:
        try:
            asset = ARAsset.objects.filter(slug__in=[
                (silk.Si_ID or ''),
                (silk.Si_name or '').strip().lower().replace(' ', '-')
            ]).first()
            if asset and getattr(asset, 'glb', None) and getattr(asset.glb, 'url', None):
                ar_model['src'] = asset.glb.url
                if getattr(asset, 'usdz', None) and getattr(asset.usdz, 'url', None):
                    ar_model['usdz'] = asset.usdz.url
        except Exception:
            pass

    # 3) ตรวจ ARShowcase โดยใช้ target_index
    if not ar_model['src']:
        try:
            if silk.target_index is not None:
                showcase = ARShowcase.objects.filter(target_index=silk.target_index).first()
                if showcase and getattr(showcase, 'glb_file', None) and getattr(showcase.glb_file, 'url', None):
                    ar_model['src'] = showcase.glb_file.url
                    if getattr(showcase, 'usdz_file', None) and getattr(showcase.usdz_file, 'url', None):
                        ar_model['usdz'] = showcase.usdz_file.url
        except Exception:
            pass

    # 4) สแกนไฟล์ใน MEDIA_ROOT (fallback)
    if not ar_model['src']:
        import os
        from glob import glob
        try:
            media_root = settings.MEDIA_ROOT
            patterns = []
            if silk.Si_ID:
                patterns.append(f"**/*{silk.Si_ID}*.glb")
            if silk.Si_name:
                name_simple = silk.Si_name.strip().lower().replace(' ', '_')
                patterns.append(f"**/*{name_simple}*.glb")

            # search in common folders
            search_dirs = [
                os.path.join(media_root, 'ar_showcase', 'glb'),
                os.path.join(media_root, 'ar_models'),
                os.path.join(media_root, ''),
            ]

            for d in search_dirs:
                if not os.path.isdir(d):
                    continue
                for p in patterns:
                    for found in glob(os.path.join(d, p), recursive=True):
                        # convert to MEDIA_URL path
                        rel = os.path.relpath(found, media_root).replace('\\', '/')
                        ar_model['src'] = settings.MEDIA_URL + rel
                        break
                    if ar_model['src']:
                        break
                if ar_model['src']:
                    break
        except Exception:
            pass

    return render(
        request,
        'collections/silk_detail.html',
        {
            'silk': silk,
            'title': f'รายละเอียด: {silk.Si_name}',
            'ratings': ratings[:10],
            'avg_score': avg_score,
            'ar_model': ar_model,
        }
    )


def silk_detail(request, pattern_id):
    """
    Wrapper รองรับ pattern_id เป็น int หรือ string
    """
    if str(pattern_id).isdigit():
        return silk_detail_view(
            request,
            int(pattern_id)
        )

    silk = SilkPattern.objects.filter(
        Si_ID=pattern_id
    ).first()

    if not silk:
        raise Http404(
            f"ไม่พบข้อมูลลายผ้า: {pattern_id}"
        )

    return silk_detail_view(
        request,
        silk.pk
    )


# =====================================================================
# SILK PATTERN : API (AR / JSON)
# =====================================================================

def silkpattern_detail_api(request, target_index: int):
    """
    API ส่งข้อมูลลายผ้าให้ AR / Frontend
    """
    silk = get_object_or_404(
        SilkPattern,
        target_index=target_index
    )

    data = {
        'id': silk.id,
        'title': silk.title or silk.Si_name,
        'model_3d': (
            request.build_absolute_uri(
                silk.model_3d.url
            )
            if silk.model_3d else None
        ),
    }

    return JsonResponse(data)


# =====================================================================
# SILK PATTERN : AR SCAN (MindAR)
# =====================================================================

def silk_qr_view(request, pk):
    """สร้าง QR code (PNG) ชี้ไปยังหน้า AR เฉพาะผ้า
    คืนค่าเป็น HttpResponse image/png (ไม่บันทึกลง DB)
    """
    target_url = request.build_absolute_uri(reverse('silk_ar_detail', args=[pk]))
    try:
        import qrcode
        import io

        qr = qrcode.QRCode(box_size=6, border=2)
        qr.add_data(target_url)
        qr.make(fit=True)
        img = qr.make_image(fill_color='black', back_color='white')
        buf = io.BytesIO()
        img.save(buf, format='PNG')
        buf.seek(0)
        return HttpResponse(buf.read(), content_type='image/png')
    except Exception:
        # fallback: redirect to public QR image generator
        fallback = f"https://api.qrserver.com/v1/create-qr-code/?size=240x240&data={quote_plus(target_url)}"
        return redirect(fallback)


# =====================================================================
# ส่วนที่ 6 หมวดหมู่ระบบผ้าไหม AR
# =====================================================================





# =====================================================================
# ส่วนที่ 7 หมวดหมู่ระบบให้คะแนนการจอง
# =====================================================================

@login_required
def booking_rate_view(request, pk):
    booking = get_object_or_404(Booking, pk=pk)

    if booking.Us_ID != request.user:
        return redirect('home')

    if booking.Re_status != 'completed':
        messages.warning(request, "ต้องปิดงานก่อนจึงจะทำแบบประเมินได้")
        return redirect('booking_history')

    if request.method == 'POST':
        form = BookingRatingForm(request.POST, instance=booking)
        if form.is_valid():
            b = form.save(commit=False)
            b.rated_at = timezone.now()
            b.save()
            messages.success(request, "บันทึกคะแนนเรียบร้อย ขอบคุณครับ!")
            return redirect('booking_history')
    else:
        form = BookingRatingForm(instance=booking)

    return render(request, 'booking/booking_rate.html', {'booking': booking, 'form': form})

# =====================================================================
# ส่วนที่ 7 หมวดหมู่ระบบให้คะแนนการจอง
# =====================================================================






# =====================================================================
# ส่วนที่ 8 หมวดหมู่ระบบวิทยากร
# =====================================================================
def speaker_list_view(request):
    # แสดงเฉพาะวิทยากรที่ยังมีบัญชีผู้ใช้และยังใช้งานได้ (กันเคส user ถูกลบ -> Speaker.user = NULL)
    speakers = (
        Speaker.objects
        .select_related("user")
        .filter(user__isnull=False, user__is_active=True)
        .order_by("name")
    )
    return render(request, "speaker/list.html", {"speakers": speakers})


def speaker_detail_view(request, speaker_id):
    speaker = get_object_or_404(Speaker, id=speaker_id, user__isnull=False, user__is_active=True)
    assignments = SpeakerSchedule.objects.filter(speaker=speaker)
    return render(request, "speaker/detail.html", {
        "speaker": speaker,
        "assignments": assignments
    })


# =========================
# SPEAKER PORTAL (LOGIN)
# =========================
# เพิ่ม import ถ้ายังไม่มี

@login_required
@user_passes_test(is_speaker)
def speaker_dashboard(request):
    speaker = Speaker.objects.filter(user=request.user).first()
    if not speaker:
        messages.warning(request, "คุณไม่มีโปรไฟล์วิทยากร")
        return redirect("home")

    assignments = SpeakerAssignment.objects.filter(speaker=speaker).order_by("-assigned_at")

    # งานที่ใช้ในฟอร์มอัปโหลด (ให้สอดคล้องกับ speaker_upload_work_view)
    upload_assignments = (
        SpeakerAssignment.objects
        .select_related("booking", "booking__Us_ID")
        .filter(speaker=speaker, booking__isnull=False, status="completed")
        .order_by("-assigned_at")
    )

    pending_assignments = assignments.filter(status__in=["pending", "assigned"])
    accepted_assignments = assignments.filter(status__in=["accepted", "confirmed"])
    completed_assignments = assignments.filter(status="completed")

    # ✅ เพิ่มบรรทัดนี้
    rejected_assignments = assignments.filter(status="rejected")

    uploads = (
        SpeakerWorkUpload.objects
        .filter(speaker=speaker)
        .select_related("assignment", "assignment__booking")
        .prefetch_related("images")
        .order_by("-created_at")[:12]
    )

    # งานที่เพิ่งปิด (ใช้โชว์ข้อมูลการจองในหน้าอัปโหลดงาน)
    just_completed_assignment = None
    just_completed_booking = None
    completed_param = (request.GET.get("completed") or "").strip()
    if completed_param:
        try:
            from django.db.models import Q

            just_completed_assignment = (
                SpeakerAssignment.objects
                .select_related("booking", "booking__Us_ID")
                .filter(speaker=speaker, status="completed")
                .filter(Q(assignment_id=completed_param) | Q(pk=completed_param))
                .first()
            )
        except Exception:
            just_completed_assignment = None

        if just_completed_assignment:
            just_completed_booking = getattr(just_completed_assignment, "booking", None)

    report_ctx = _get_speaker_report_context(speaker)

    context = {
        "speaker": speaker,
        "assignments": assignments,
        "upload_assignments": upload_assignments,
        "pending_assignments": pending_assignments,
        "accepted_assignments": accepted_assignments,
        "completed_assignments": completed_assignments,

        # ✅ เพิ่มบรรทัดนี้
        "rejected_assignments": rejected_assignments,

        "uploads": uploads,
        "just_completed_assignment": just_completed_assignment,
        "just_completed_booking": just_completed_booking,
    }
    context.update(report_ctx)

    return render(request, "speaker/dashboard.html", context)

@login_required
@user_passes_test(is_speaker)
def speaker_pending_view(request):
    """งานที่ยังไม่ได้รับ (หน้าแยก)"""
    speaker = get_object_or_404(Speaker, user=request.user)

    assignments = (
        SpeakerAssignment.objects
        .filter(speaker=speaker, status__in=["pending", "assigned"])
        .select_related("booking", "speaker")
        .order_by("-assigned_at")
    )

    return render(request, "speaker/pending.html", {
        "speaker": speaker,
        "assignments": assignments,
        "title": "งานที่ยังไม่ได้รับ",
    })


@login_required
@user_passes_test(is_speaker)
def speaker_in_progress_view(request):
    """งานที่กำลังทำ (หน้าแยก)"""
    speaker = Speaker.objects.filter(user=request.user).first()
    if not speaker:
        messages.warning(request, "คุณไม่มีโปรไฟล์วิทยากร")
        return redirect("home")

    assignments = (
        SpeakerAssignment.objects
        .filter(speaker=speaker, status__in=["accepted", "confirmed"])
        .select_related("booking")
        .order_by("-assigned_at")
    )

    return render(request, "speaker/in_progress.html", {
        "speaker": speaker,
        "assignments": assignments,
        "title": "งานที่กำลังทำ",
    })


@login_required
@user_passes_test(is_speaker)
def speaker_completed_view(request):
    """งานที่เสร็จสิ้น (หน้าแยก)"""
    speaker = get_object_or_404(Speaker, user=request.user)

    assignments = (
        SpeakerAssignment.objects
        .filter(speaker=speaker, status="completed")
        .select_related("booking")
        .order_by("-assigned_at")
    )

    return render(request, "speaker/completed.html", {
        "speaker": speaker,
        "assignments": assignments,
        "title": "งานที่เสร็จสิ้น",
    })


# =========================
# REPORT HELPERS
# =========================
def _get_speaker_report_context(speaker):
    """คืนค่า context สำหรับรายงาน โดยล็อกเฉพาะข้อมูลของ speaker คนนี้เท่านั้น"""

    # งานที่ผูก booking จริง (ของวิทยากรคนนี้เท่านั้น)
    assignments = (
        SpeakerAssignment.objects
        .select_related("booking", "booking__Us_ID")
        .filter(speaker=speaker, booking__isnull=False)
        .order_by("-assigned_at")
    )

    # --------- 1) BookingQuestionResponse (แบบประเมินหลังเข้าชม) ----------
    # NOTE: ในโปรเจกต์นี้ข้อมูลประเมินที่ใช้งานจริงจะอยู่ในตารางนี้
    responses_qs = (
        BookingQuestionResponse.objects
        .select_related("booking", "question", "booking__speaker_assignment")
        # แสดงเฉพาะ “คำถามหมวดวิทยากร” ในรายงานวิทยากร
        .filter(booking__speaker_assignment__speaker=speaker, question__category="speaker")
    )

    booking_response_list = list(
        responses_qs
        .values(
            "booking_id",
            "booking__Re_date",
            "booking__visit_session",
            "booking__Re_quantity",
            "booking__Us_ID__username",
        )
        .annotate(
            response_count=Count("id"),
            last_answered_at=Max("created_at"),
        )
        .order_by("-booking__Re_date", "-last_answered_at")
    )

    total_answers = responses_qs.count()
    total_bookings = len(booking_response_list)
    avg_answers_per_booking = (total_answers / total_bookings) if total_bookings else 0

    booking_response_summary = {
        "total_answers": total_answers,
        "total_bookings": total_bookings,
        "avg_answers_per_booking": avg_answers_per_booking,
        "last_answered_at": responses_qs.aggregate(m=Max("created_at")).get("m"),
    }

    # สรุปต่อคำถาม: ต้องเรียงและนับข้อให้ตรงตาม "รายการคำถามในระบบ"
    # - แสดง 1 แถวต่อ 1 คำถาม (แม้บางข้อยังไม่มีคนตอบ)
    # - ค่าเฉลี่ยคำนวณจากคำตอบ 1–5 (แบบฟอร์มปัจจุบันส่งเป็นสตริงตัวเลข "1".."5")

    category_order = Case(
        When(category="museum", then=Value(1)),
        When(category="silk", then=Value(2)),
        When(category="speaker", then=Value(3)),
        default=Value(99),
        output_field=IntegerField(),
    )
    category_label_map = dict(getattr(Question, "CATEGORY_CHOICES", []) or [])

    all_questions = list(
        Question.objects
        .filter(category="speaker")
        .annotate(_cat_order=category_order)
        .order_by("_cat_order", "id")
        .values("id", "question", "category")
    )

    numeric_responses_qs = responses_qs.filter(answer__in=["1", "2", "3", "4", "5"])
    agg_rows = list(
        numeric_responses_qs
        .values("question_id")
        .annotate(
            cnt=Count("id"),
            avg_score=Avg(Cast("answer", IntegerField())),
        )
    )
    agg_map = {r["question_id"]: r for r in agg_rows}

    response_summary = []
    for q in all_questions:
        qid = q["id"]
        agg = agg_map.get(qid) or {}
        response_summary.append({
            "question_id": qid,
            "question__question": q["question"],
            "question__category": q.get("category"),
            "question__category_label": category_label_map.get(q.get("category"), ""),
            "cnt": agg.get("cnt", 0) or 0,
            "avg_score": agg.get("avg_score"),
        })

    return {
        "assignments": assignments,
        "booking_response_summary": booking_response_summary,
        "booking_response_list": booking_response_list,
        "response_summary": response_summary,
    }


@login_required
@user_passes_test(is_speaker)
def speaker_report_booking_detail(request, booking_id):
    speaker = Speaker.objects.filter(user=request.user).first()
    if not speaker:
        raise Http404()

    # ต้องเป็น booking ที่มอบหมายให้ speaker คนนี้เท่านั้น
    assignment = get_object_or_404(
        SpeakerAssignment,
        speaker=speaker,
        booking_id=booking_id,
    )

    booking = assignment.booking

    # 1) แบบ 10 ข้อ (SilkPatternRating)
    ratings = (
        SilkPatternRating.objects
        .filter(booking=booking)
        .order_by("-created_at")
    )

    # 2) แบบหลังเข้าชม (BookingQuestionResponse)
    category_order = Case(
        When(question__category="museum", then=Value(1)),
        When(question__category="silk", then=Value(2)),
        When(question__category="speaker", then=Value(3)),
        default=Value(99),
        output_field=IntegerField(),
    )
    responses = (
        BookingQuestionResponse.objects
        .select_related("question")
        # เฉพาะแบบประเมินหมวด “วิทยากร”
        .filter(booking=booking, question__category="speaker")
        .annotate(_cat_order=category_order)
        .order_by("_cat_order", "question_id", "created_at")
    )

    # map a/b/c/d -> ข้อความตัวเลือก
    choice_field = {"a": "option_a", "b": "option_b", "c": "option_c", "d": "option_d", "e": "option_e"}
    for r in responses:
        ans = (r.answer or "").strip().lower()
        if ans in choice_field:
            r.answer_display = getattr(r.question, choice_field[ans], None) or ans.upper()
        else:
            r.answer_display = r.answer or "-"

    return render(request, "speaker/report_booking_detail.html", {
        "speaker": speaker,
        "booking": booking,
        "ratings": ratings,
        "responses": responses,
    })

# =========================
# REPORT VIEW
# =========================
@login_required
@user_passes_test(is_speaker)
def speaker_report_view(request):
    """หน้ารายงานของวิทยากร (ล็อกเฉพาะคนที่ login เท่านั้น)"""
    speaker = get_object_or_404(Speaker, user=request.user)
    ctx = _get_speaker_report_context(speaker)
    ctx["speaker"] = speaker
    ctx["title"] = "การประเมิน (วิทยากร)"
    ctx["today"] = timezone.localdate()
    ctx["now"] = None
    return render(request, "speaker/report.html", ctx)


ALLOWED_CONTENT_TYPES = {"image/jpeg", "image/png", "image/webp"}
MAX_UPLOAD_SIZE = 2 * 1024 * 1024  # 2MB

@login_required
@user_passes_test(is_speaker)
def speaker_upload_work_view(request):
    speaker = Speaker.objects.filter(user=request.user).first()
    if not speaker:
        messages.error(request, "ไม่พบโปรไฟล์วิทยากร")
        return redirect("home")

    # งานที่รับผิดชอบ (ไว้ให้เลือกผูกกับชุดรูป)
    assignments = (
        SpeakerAssignment.objects
        .select_related("booking", "booking__Us_ID")
        .filter(speaker=speaker, booking__isnull=False, status="completed")
        .order_by("-assigned_at")
    )

    if request.method == "POST":
        next_url = (request.POST.get("next") or request.GET.get("next") or "").strip()
        if next_url and not url_has_allowed_host_and_scheme(
            url=next_url,
            allowed_hosts={request.get_host()},
            require_https=request.is_secure(),
        ):
            next_url = ""

        assignment_id = (request.POST.get("assignment_id") or "").strip()
        title = (request.POST.get("title") or "").strip()
        note = (request.POST.get("note") or "").strip()

        files = request.FILES.getlist("images")
        if not files:
            messages.error(request, "กรุณาเลือกรูปอย่างน้อย 1 รูป")
            return redirect(next_url or "speaker_upload_work")

        # ตรวจ assignment (ถ้ามี)
        assignment_obj = None
        if assignment_id:
            assignment_obj = assignments.filter(assignment_id=assignment_id).first()
            if not assignment_obj:
                messages.error(request, "ไม่พบงานที่เลือก หรือคุณไม่มีสิทธิ์ใช้งานงานนี้")
                return redirect(next_url or "speaker_upload_work")

        # validate files
        for f in files:
            ctype = getattr(f, "content_type", "") or ""
            if ctype not in ALLOWED_CONTENT_TYPES:
                messages.error(request, "รองรับเฉพาะไฟล์รูป JPG/PNG/WEBP เท่านั้น")
                return redirect(next_url or "speaker_upload_work")
            if f.size and f.size > MAX_UPLOAD_SIZE:
                messages.error(request, "ไฟล์รูปต้องมีขนาดไม่เกิน 2MB ต่อรูป")
                return redirect(next_url or "speaker_upload_work")

        # save
        with transaction.atomic():
            upload = SpeakerWorkUpload.objects.create(
                speaker=speaker,
                assignment=assignment_obj,
                title=title,
                note=note,
            )
            # IMPORTANT: avoid bulk_create with File/ImageField; it skips FieldFile saving
            for f in files:
                img = SpeakerWorkImage(upload=upload)
                img.image = f
                img.save()

        messages.success(request, "อัปโหลดรูปผลงานเรียบร้อยแล้ว")
        return redirect(next_url or "speaker_upload_work")

    # โชว์รายการล่าสุด
    uploads = (
        SpeakerWorkUpload.objects
        .filter(speaker=speaker)
        .select_related("assignment", "assignment__booking")
        .prefetch_related("images")
        .order_by("-created_at")[:12]
    )

    return render(request, "speaker/upload_work.html", {
        "speaker": speaker,
        "assignments": assignments,
        "uploads": uploads,
    })


# =========================
# ASSIGNMENT LIST / DETAIL
# =========================
@login_required
@user_passes_test(is_speaker)
def speaker_assignment_detail(request, assignment_id):
    assignment = get_object_or_404(SpeakerAssignment, assignment_id=assignment_id)

    # ✅ ล็อกสิทธิ์: ดูได้เฉพาะงานของตัวเอง
    if not assignment.speaker or not assignment.speaker.user or assignment.speaker.user != request.user:
        raise Http404("You do not have permission to view this assignment.")

    booking = getattr(assignment, "booking", None)
    return render(request, "speaker/assignment_detail.html", {
        "assignment": assignment,
        "booking": booking,
    })


# =========================
# ACTIONS (ACCEPT / COMPLETE)
# =========================
@login_required
@user_passes_test(is_speaker)
def accept_assignment(request, assignment_id):
    """Speaker รับงาน (รองรับทั้ง pk หรือ assignment_id)"""
    try:
        assignment = SpeakerAssignment.objects.get(pk=assignment_id, speaker__user=request.user)
    except (SpeakerAssignment.DoesNotExist, ValueError):
        assignment = get_object_or_404(SpeakerAssignment, assignment_id=assignment_id, speaker__user=request.user)

    if assignment.status not in ("pending", "assigned"):
        messages.warning(request, "ไม่สามารถรับงานได้ เนื่องจากสถานะไม่ใช่รอดำเนินการ")
        return redirect(f"{reverse('speaker_dashboard')}#section-pending")

    assignment.status = "accepted"
    assignment.save(update_fields=["status"])
    messages.success(request, "รับงานเรียบร้อยแล้ว")

    return redirect(f"{reverse('speaker_dashboard')}#section-pending")


@login_required
@user_passes_test(is_speaker)
def complete_assignment(request, assignment_id):
    """Speaker ปิดงาน (ต้อง accepted/confirmed ก่อน)"""
    try:
        assignment = SpeakerAssignment.objects.get(pk=assignment_id, speaker__user=request.user)
    except (SpeakerAssignment.DoesNotExist, ValueError):
        assignment = get_object_or_404(SpeakerAssignment, assignment_id=assignment_id, speaker__user=request.user)

    if assignment.status not in ("accepted", "confirmed"):
        messages.warning(request, "ไม่สามารถปิดงานได้ ต้องรับงานก่อนจึงจะปิดงานได้")
        redirect_id = getattr(assignment, "assignment_id", None) or assignment.id
        return redirect("speaker_assignment_detail", assignment_id=redirect_id)

    # ✅ ปิดงานได้เฉพาะ "วันเดียวกับวันที่งาน" เท่านั้น
    booking = getattr(assignment, "booking", None)
    booking_date = getattr(booking, "Re_date", None) if booking else None
    today = timezone.localdate()
    if booking_date and booking_date != today:
        messages.error(request, f"ยังไม่สามารถปิดงานได้ เนื่องจากวันนี้ไม่ตรงกับวันที่งาน ({booking_date.strftime('%d/%m/%Y')})")
        redirect_id = getattr(assignment, "assignment_id", None) or assignment.id
        return redirect("speaker_assignment_detail", assignment_id=redirect_id)

    assignment.status = "completed"
    assignment.save(update_fields=["status"])

    # อัปเดต booking ที่ผูกกับ assignment (OneToOne) ให้เสร็จสิ้นด้วย
    if assignment.booking:
        assignment.booking.Re_status = "completed"
        assignment.booking.save(update_fields=["Re_status"])
        messages.success(request, "ปิดงานเรียบร้อย")
    else:
        messages.warning(request, "ไม่พบ booking ที่เกี่ยวข้องกับ assignment นี้")

    redirect_id = getattr(assignment, "assignment_id", None) or assignment.id
    return redirect(f"{reverse('speaker_dashboard')}?completed={redirect_id}#section-upload")
# =====================================================================
# ส่วนที่ 8 หมวดหมู่ระบบวิทยากร
# =====================================================================






# =====================================================================
# ส่วนที่ 9 หมวดหมู่ระบบแดชบอร์ดผู้ดูแลระบบ (CLEAN VERSION)
# =====================================================================
# ---------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------
@login_required
@user_passes_test(is_staff_or_admin)
def admin_dashboard_view(request):
    """หน้า Dashboard ผู้ดูแลระบบ"""

    today = timezone.now().date()

    unassigned_bookings = Booking.objects.filter(
        Re_status='approved',
        speaker_assignment__isnull=True
    ).count()

    pending_assign_count = Booking.objects.filter(
        Re_status='approved'
    ).filter(
        Q(speaker_assignment__isnull=True) | Q(speaker_assignment__status='rejected')
    ).count()

    assigned_jobs_count = SpeakerAssignment.objects.filter(
        booking__isnull=False
    ).exclude(
        status__in=['rejected', 'cancelled']
    ).count()

    context = {
        'total_users': User.objects.count(),

        'pending_count': Booking.objects.filter(
            Q(Re_status='pending') | Q(Re_status__isnull=True) | Q(Re_status='')
        ).count(),

        'today_bookings_count': Booking.objects.filter(Re_date=today).count(),
        'unassigned_count': unassigned_bookings,
        'pending_assign_count': pending_assign_count,
        'assigned_jobs_count': assigned_jobs_count,

        'total_bookings': Booking.objects.count(),
        'total_patterns': SilkPattern.objects.count(),
        # นับเฉพาะวิทยากรที่ยังมีบัญชีผู้ใช้และยังใช้งานได้
        'active_speakers': Speaker.objects.filter(user__isnull=False, user__is_active=True).count(),

        'recent_bookings': Booking.objects.order_by('-created_at')[:5],
        'today': timezone.now(),
    }

    return render(request, 'admin_panel/admin_home.html', context)


@login_required
@user_passes_test(is_staff_or_admin)
def admin_report_view(request):
    """ศูนย์รวมรายงาน (ไว้คลิกเข้าไปดูรายงานแต่ละประเภท)"""

    context = {
        'today': timezone.localtime(),
    }

    return render(request, 'admin_panel/report/report.html', context)


@login_required
@user_passes_test(is_staff_or_admin)
def admin_report_pdf_view(request):
    """ส่งออกไฟล์ PDF รายงานสรุป (ย่อเอาแต่ข้อมูลสำคัญ)"""
    from django.http import HttpResponse

    try:
        from reportlab.lib.pagesizes import A4
        from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
        from reportlab.lib.styles import getSampleStyleSheet
        from reportlab.lib import colors
        from reportlab.pdfbase import pdfmetrics
        from reportlab.pdfbase.ttfonts import TTFont
    except ImportError:
        return HttpResponse(
            "ต้องติดตั้งไลบรารี reportlab ก่อนใช้งานฟีเจอร์นี้ (pip install reportlab)",
            content_type="text/plain; charset=utf-8",
        )

    # ใช้ข้อมูลสรุปแบบเดียวกับหน้า HTML แต่ย่อให้เหลือแต่หัวใจสำคัญ
    silk_total = SilkPattern.objects.count()
    workshop_total = Workshop.objects.count()
    booking_total = Booking.objects.count()
    survey_total = SurveyRating.objects.count()

    # ค่าเฉลี่ยคะแนนรวมทุกคำถาม (ถ้ามีข้อมูล)
    global_avg = SurveyRating.objects.aggregate(avg=Avg('rating'))['avg'] or 0

    # ข้อมูลพิพิธภัณฑ์สำหรับส่วนหัวรายงาน
    museum_profile = MuseumProfile.objects.order_by('-id').first()
    museum_name = museum_profile.name if museum_profile else "พิพิธภัณฑ์ผ้าไหม"
    museum_address = museum_profile.address or "" if museum_profile else ""
    museum_phone = museum_profile.phone or "" if museum_profile else ""

    # ข้อมูลเชิงลึกเพิ่มเติม (อ้างอิงโครงสร้างเดียวกับหน้า HTML report)
    silk_stats = {
        'total_patterns': silk_total,
        'total_silk_ratings': SilkPatternRating.objects.count(),
    }

    top_silk_patterns = (
        SilkPattern.objects
        .annotate(rating_count=Count('ratings'))
        .order_by('-rating_count', 'Si_name')[:5]
    )

    workshop_stats = {
        'total_workshops': workshop_total,
        'active_workshops': Workshop.objects.filter(is_active=True).count(),
        'total_workshop_bookings': WorkshopBooking.objects.count(),
    }

    top_workshops = (
        Workshop.objects
        .annotate(booking_count=Count('workshopbooking'))
        .order_by('-booking_count', 'title')[:5]
    )

    booking_stats = {
        'total_bookings': booking_total,
        'pending': Booking.objects.filter(Re_status='pending').count(),
        'approved': Booking.objects.filter(Re_status='approved').count(),
        'rejected': Booking.objects.filter(Re_status='rejected').count(),
    }

    today = timezone.now().date()
    six_months_ago = today - timedelta(days=180)
    bookings_by_month_qs = (
        Booking.objects.filter(Re_date__gte=six_months_ago)
        .annotate(month=TruncMonth('Re_date'))
        .values('month')
        .annotate(count=Count('id'))
        .order_by('month')
    )
    bookings_by_month = list(bookings_by_month_qs)

    survey_stats = list(
        SurveyRating.objects
        .values('question_id', 'question__question')
        .annotate(
            avg_rating=Avg('rating'),
            responses=Count('id'),
        )
        .order_by('question_id')
    )

    # เตรียม response ให้เปิดดูในเบราว์เซอร์ก่อน (inline) แล้วค่อยเลือกดาวน์โหลดได้
    response = HttpResponse(content_type='application/pdf')
    response['Content-Disposition'] = 'inline; filename="museum_summary_report.pdf"'

    page_width, page_height = A4

    doc = SimpleDocTemplate(
        response,
        pagesize=A4,
        leftMargin=40,
        rightMargin=40,
        topMargin=120,
        bottomMargin=40,
    )
    styles = getSampleStyleSheet()

    # ลงทะเบียนฟอนต์ภาษาไทย (ถ้าพบในระบบ)
    import os

    base_font = "Helvetica"
    font_candidates = [
        ("THSarabunNew", "C:/Windows/Fonts/THSarabunNew.ttf"),
        ("THSarabun", "C:/Windows/Fonts/THSarabun.ttf"),
        ("THSarabunPSK", "C:/Windows/Fonts/THSarabunPSK.ttf"),
        ("Tahoma", "C:/Windows/Fonts/tahoma.ttf"),  # มีเกือบทุกเครื่อง และรองรับภาษาไทย
    ]

    for font_name, font_path in font_candidates:
        if os.path.exists(font_path):
            try:
                pdfmetrics.registerFont(TTFont(font_name, font_path))
                base_font = font_name
                break
            except Exception:
                continue

    # ปรับสไตล์ให้ใช้ฟอนต์ฐานที่รองรับภาษาไทย
    styles['Normal'].fontName = base_font
    styles['Heading2'].fontName = base_font
    styles['Title'].fontName = base_font
    story = []

    # เว้นพื้นที่ส่วนหัวที่วาดด้วย canvas
    story.append(Spacer(1, 14))

    # ฟังก์ชันช่วยคำนวณเปอร์เซ็นต์
    def _fmt_percent(count, total):
        if not total:
            return "-"
        return f"{(count * 100.0 / total):.1f}%"

    # ------------------------------------------------------------------
    # 1) ข้อมูลภาพรวม
    # ------------------------------------------------------------------
    story.append(Paragraph("๑. ข้อมูลภาพรวม (Executive Summary)", styles['Heading2']))
    story.append(Spacer(1, 6))

    overview_data = [
        ["หมวดข้อมูล", "จำนวน (รายการ)", "หมายเหตุ"],
        ["ลายผ้าไหมในระบบ", f"{silk_stats['total_patterns']:,}", "จำนวนลายผ้าที่บันทึกในระบบทั้งหมด"],
        ["การให้คะแนนลายผ้า", f"{silk_stats['total_silk_ratings']:,}", "นับจากแบบประเมินลายผ้า (SilkPatternRating)"],
        ["กิจกรรม / เวิร์กช็อป", f"{workshop_stats['total_workshops']:,}", f"เปิดให้จอง {workshop_stats['active_workshops']:,} รายการ"],
        ["Workshop Booking", f"{workshop_stats['total_workshop_bookings']:,}", "จำนวนการเข้าร่วมกิจกรรมทั้งหมด"],
        ["การจองเข้าชมพิพิธภัณฑ์", f"{booking_stats['total_bookings']:,}", "รวมทุกสถานะการอนุมัติ"],
        ["แบบประเมินความพึงพอใจ", f"{survey_total:,}", f"คะแนนเฉลี่ยรวม {global_avg:.2f} จาก 5"],
    ]

    overview_table = Table(overview_data, hAlign='LEFT', colWidths=[160, 90, 230])
    overview_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.lightgrey),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.black),
        ('FONTNAME', (0, 0), (-1, -1), base_font),
        ('ALIGN', (1, 1), (1, -1), 'RIGHT'),
        ('ALIGN', (0, 0), (0, -1), 'LEFT'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
        ('FONTSIZE', (0, 0), (-1, -1), 9),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 6),
    ]))
    story.append(overview_table)

    # ------------------------------------------------------------------
    # 2) สถิติการจองเข้าชมพิพิธภัณฑ์
    # ------------------------------------------------------------------
    story.append(Spacer(1, 16))
    story.append(Paragraph("๒. สถิติการจองเข้าชมพิพิธภัณฑ์", styles['Heading2']))
    story.append(Spacer(1, 6))

    booking_status_data = [
        ["สถานะ", "จำนวน (รายการ)", "สัดส่วน"],
        ["รอดำเนินการ", f"{booking_stats['pending']:,}", _fmt_percent(booking_stats['pending'], booking_stats['total_bookings'])],
        ["อนุมัติแล้ว", f"{booking_stats['approved']:,}", _fmt_percent(booking_stats['approved'], booking_stats['total_bookings'])],
        ["ถูกปฏิเสธ", f"{booking_stats['rejected']:,}", _fmt_percent(booking_stats['rejected'], booking_stats['total_bookings'])],
    ]

    booking_status_table = Table(booking_status_data, hAlign='LEFT', colWidths=[160, 90, 80])
    booking_status_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.lightgrey),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.black),
        ('FONTNAME', (0, 0), (-1, -1), base_font),
        ('ALIGN', (1, 1), (2, -1), 'RIGHT'),
        ('ALIGN', (0, 0), (0, -1), 'LEFT'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
        ('FONTSIZE', (0, 0), (-1, -1), 9),
    ]))
    story.append(booking_status_table)

    # สถิติจำนวนการจองย้อนหลัง ๖ เดือน
    if bookings_by_month:
        story.append(Spacer(1, 8))
        story.append(Paragraph("สถิติจำนวนการจองย้อนหลัง ๖ เดือน", styles['Normal']))
        story.append(Spacer(1, 4))

        month_rows = [["เดือน", "จำนวนการจอง"]]
        for row in bookings_by_month:
            month_label = row['month'].strftime('%B %Y') if row['month'] else 'ไม่ระบุ'
            month_rows.append([month_label, f"{row['count']:,} รายการ"])

        month_table = Table(month_rows, hAlign='LEFT', colWidths=[200, 130])
        month_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.whitesmoke),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.black),
            ('FONTNAME', (0, 0), (-1, -1), base_font),
            ('ALIGN', (1, 1), (1, -1), 'RIGHT'),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
            ('FONTSIZE', (0, 0), (-1, -1), 9),
        ]))
        story.append(month_table)

    # ------------------------------------------------------------------
    # 3) สถิติแบบประเมินความพึงพอใจ
    # ------------------------------------------------------------------
    if survey_stats:
        story.append(Spacer(1, 16))
        story.append(Paragraph("๓. สถิติแบบประเมินความพึงพอใจ", styles['Heading2']))
        story.append(Spacer(1, 6))

        survey_table_data = [["ข้อคำถาม", "คะแนนเฉลี่ย (เต็ม 5)", "จำนวนคำตอบ"]]
        for item in survey_stats[:8]:  # แสดงสูงสุด 8 ข้อแรกเพื่อให้อ่านง่าย
            question_text = f"Q{item['question_id']}: {item['question__question']}"
            avg_text = f"{item['avg_rating']:.2f}" if item['avg_rating'] is not None else "-"
            survey_table_data.append([
                question_text,
                avg_text,
                f"{item['responses']:,} ครั้ง",
            ])

        survey_table = Table(survey_table_data, hAlign='LEFT', colWidths=[260, 80, 80])
        survey_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.lightgrey),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.black),
            ('FONTNAME', (0, 0), (-1, -1), base_font),
            ('ALIGN', (1, 1), (2, -1), 'RIGHT'),
            ('ALIGN', (0, 0), (0, -1), 'LEFT'),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
            ('FONTSIZE', (0, 0), (-1, -1), 8),
        ]))
        story.append(survey_table)

    # ฟังก์ชันส่วนหัว/ส่วนท้ายให้ดูเป็นเอกสารราชการมากขึ้น
    header_generated_at = timezone.now().strftime('%d/%m/%Y %H:%M น.')

    def _header_footer(canvas, doc):
        canvas.saveState()

        # กรอบรอบเนื้อหา (เลื่อนเส้นขอบด้านบนลงมาใกล้เนื้อหา)
        canvas.setLineWidth(0.7)
        box_left = 30
        box_right = page_width - 30
        box_bottom = 40
        box_top_margin = 135  # ระยะจากขอบบนลงมาที่ต้องการให้เป็นเส้นกรอบ
        box_height = page_height - box_top_margin - box_bottom
        canvas.rect(box_left, box_bottom, box_right - box_left, box_height)

        # ส่วนหัว - จัดรูปแบบหลายบรรทัดให้สั้น อ่านง่าย
        center_x = page_width / 2
        y = page_height - 46

        # ชื่อพิพิธภัณฑ์ (ตัวหนาเล็กน้อย)
        canvas.setFont(base_font, 16)
        canvas.drawCentredString(center_x, y, museum_name)

        # ชื่อรายงาน
        y -= 16
        canvas.setFont(base_font, 11)
        canvas.drawCentredString(center_x, y, "รายงานสรุประบบพิพิธภัณฑ์ผ้าไหม")

        # ที่อยู่ / โทรศัพท์ / อีเมล แยกเป็นหลายบรรทัด หากมีข้อมูล
        y -= 14
        canvas.setFont(base_font, 8.5)

        address_lines = []
        if museum_address:
            # ตัดบรรทัดตาม \n และตัดให้สั้นไม่เกิน ~75 ตัวอักษร
            for raw_line in str(museum_address).splitlines():
                line = raw_line.strip()
                if not line:
                    continue
                if len(line) > 75:
                    line = line[:72] + "..."
                address_lines.append(line)

        for line in address_lines[:2]:  # แสดงไม่เกิน 2 บรรทัด
            canvas.drawCentredString(center_x, y, line)
            y -= 11

        contact_parts = []
        if museum_phone:
            contact_parts.append(f"โทรศัพท์: {museum_phone}")
        if getattr(museum_profile, 'email', None):
            contact_parts.append(f"อีเมล: {museum_profile.email}")
        if contact_parts:
            canvas.drawCentredString(center_x, y, "  |  ".join(contact_parts))
            y -= 11

        # วันที่ออกรายงาน (มุมขวาบน)
        canvas.setFont(base_font, 9)
        canvas.drawRightString(page_width - 40, page_height - 46, f"ออกรายงานเมื่อ {header_generated_at}")

        # ลายเซ็นด้านล่างกระดาษ (ให้อยู่ภายในกรอบ)
        sig_y = box_bottom + 30
        col_width = (box_right - box_left - 40) / 3.0
        start_x = box_left + 20

        canvas.setFont(base_font, 9)
        canvas.drawCentredString(start_x + col_width * 0.5, sig_y + 18, "(ลงชื่อ) ...................................................")
        canvas.drawCentredString(start_x + col_width * 1.5, sig_y + 18, "(ลงชื่อ) ...................................................")
        canvas.drawCentredString(start_x + col_width * 2.5, sig_y + 18, "(ลงชื่อ) ...................................................")

        canvas.setFont(base_font, 9)
        canvas.drawCentredString(start_x + col_width * 0.5, sig_y, "ผู้จัดทำรายงาน")
        canvas.drawCentredString(start_x + col_width * 1.5, sig_y, "ผู้ตรวจสอบ")
        canvas.drawCentredString(start_x + col_width * 2.5, sig_y, "ผู้บริหารที่เกี่ยวข้อง")

        canvas.setFont(base_font, 9)
        canvas.drawCentredString(start_x + col_width * 0.5, sig_y - 16, "วันที่ ....../....../......")
        canvas.drawCentredString(start_x + col_width * 1.5, sig_y - 16, "วันที่ ....../....../......")
        canvas.drawCentredString(start_x + col_width * 2.5, sig_y - 16, "วันที่ ....../....../......")

        # หมายเลขหน้า (มุมขวาล่าง)
        canvas.setFont(base_font, 8)
        canvas.drawRightString(page_width - 40, 30, f"หน้า {doc.page}")

        canvas.restoreState()

    doc.build(story, onFirstPage=_header_footer, onLaterPages=_header_footer)
    return response


# ---------------------------------------------------------------------
# Booking Approval
# ---------------------------------------------------------------------
@login_required
@user_passes_test(is_staff_or_admin)
@require_POST
def update_booking_status(request, booking_id, status):
    booking = get_object_or_404(Booking, pk=booking_id)

    # Allow redirect back to a specific page (e.g., booking detail) safely
    from django.utils.http import url_has_allowed_host_and_scheme

    next_url = (request.POST.get('next') or '').strip()
    if not next_url:
        next_url = (request.META.get('HTTP_REFERER') or '').strip()

    def _safe_redirect(to_url: str):
        if to_url and url_has_allowed_host_and_scheme(
            url=to_url,
            allowed_hosts={request.get_host()},
            require_https=request.is_secure(),
        ):
            return redirect(to_url)
        return redirect('approve_bookings')

    status = (status or "").lower().strip()

    current_status = (getattr(booking, "Re_status", None) or "").strip()
    if current_status not in ("", "pending"):
        messages.error(request, "ไม่สามารถอนุมัติ/ปฏิเสธได้ เนื่องจากรายการนี้ไม่ได้อยู่ในสถานะรออนุมัติ")
        return _safe_redirect(next_url)

    if status == 'approved':
        booking.Re_status = 'approved'
        booking.decision_note = None  # (เลือกได้) ล้างเหตุผลเดิมถ้าเคยปฏิเสธมาก่อน

        SpeakerAssignment.objects.filter(booking=booking).update(status='confirmed')
        messages.success(request, f'อนุมัติ #{booking.id} และยืนยันวิทยากรแล้ว')

    elif status == 'rejected':
        reason = (request.POST.get('decision_note') or '').strip()

        if not reason:
            messages.error(request, 'กรุณากรอกเหตุผลการปฏิเสธก่อน')
            return _safe_redirect(next_url)

        booking.Re_status = 'rejected'
        booking.decision_note = reason  # ✅ เก็บเหตุผลไว้ที่นี่

        SpeakerAssignment.objects.filter(booking=booking).update(status='cancelled')
        messages.warning(request, f'ปฏิเสธ #{booking.id} แล้ว')

    else:
        raise Http404("Invalid status")

    booking.decided_by = request.user
    booking.decided_at = timezone.now()
    booking.save()

    return _safe_redirect(next_url)


# ---------------------------------------------------------------------
# User Management
# ---------------------------------------------------------------------
@login_required
@user_passes_test(is_staff_or_admin)
def manage_users_view(request):
    if request.method == 'POST':
        action = request.POST.get('action')

        if action == 'delete':
            uid = request.POST.get('user_id')
            user = User.objects.filter(id=uid).first()
            if user and user != request.user:
                # ถ้าเป็นวิทยากร ให้เช็คก่อนว่ามีงานที่รับอยู่หรือไม่
                speaker = Speaker.objects.filter(user=user).first()
                if speaker:
                    active_statuses = ['pending', 'assigned', 'accepted', 'confirmed']
                    has_active_assignments = speaker.assignments.filter(status__in=active_statuses).exists()
                    if has_active_assignments:
                        messages.error(request, 'ไม่สามารถลบวิทยากรคนนี้ได้ เนื่องจากยังมีงานที่ได้รับมอบหมายอยู่')
                        return redirect('manage_users')

                    # ✅ เพิ่ม: กันลบวิทยากรถ้ามีผลงาน หรือมีงาน completed แล้ว
                    has_work_uploads = speaker.work_uploads.exists()
                    has_completed_assignments = speaker.assignments.filter(status='completed').exists()
                    if has_work_uploads or has_completed_assignments:
                        messages.error(request, 'ไม่สามารถลบบัญชีวิทยากรได้ เนื่องจากมีประวัติผลงานหรือมีงานที่ปิดงานแล้ว')
                        return redirect('manage_users')

                try:
                    user.delete()
                    messages.success(request, 'ลบผู้ใช้เรียบร้อยแล้ว')
                except ProtectedError:
                    messages.error(request, 'ไม่สามารถลบผู้ใช้งานได้ เนื่องจากมีข้อมูลที่เกี่ยวข้อง (ประวัติการจอง/บัญชีวิทยากร)')
            else:
                messages.error(request, 'ไม่สามารถลบผู้ใช้นี้ได้')
            return redirect('manage_users')

        username = (request.POST.get('username') or '').strip()
        email = (request.POST.get('email') or '').strip()
        password = request.POST.get('password') or ''
        confirm_password = request.POST.get('confirm_password') or ''
        first_name = request.POST.get('first_name', '').strip()
        last_name = request.POST.get('last_name', '').strip()
        phone = (request.POST.get('phone') or '').strip()
        role = request.POST.get('role', 'member')

        admin_exists = User.objects.filter(is_superuser=True).exists()

        if password != confirm_password:
            messages.error(request, 'รหัสผ่านไม่ตรงกัน')
        elif role == 'admin' and admin_exists:
            messages.error(request, 'ไม่สามารถเพิ่มผู้ดูแลระบบเพิ่มได้ เนื่องจากมีผู้ดูแลระบบอยู่แล้ว')
        elif User.objects.filter(username=username).exists():
            messages.error(request, 'ชื่อผู้ใช้นี้มีอยู่แล้ว')
        else:
            try:
                with transaction.atomic():
                    user = User.objects.create_user(username=username, email=email, password=password)
                    user.first_name = first_name
                    user.last_name = last_name
                    user.is_staff = (role == 'admin')
                    user.is_superuser = (role == 'admin')
                    user.save()

                    profile, _ = Profile.objects.get_or_create(user=user)
                    profile.full_name = f"{first_name} {last_name}".strip()
                    profile.phone = phone
                    profile.role = role
                    profile.save()

                    if role == 'speaker':
                        Speaker.objects.get_or_create(
                            user=user,
                            defaults={'name': (profile.full_name or user.get_full_name() or user.username).strip()},
                        )
            except IntegrityError:
                messages.error(request, 'ชื่อผู้ใช้นี้มีอยู่แล้ว')
                return redirect('manage_users')

            messages.success(request, f'เพิ่มผู้ใช้ {username} เรียบร้อยแล้ว')

        return redirect('manage_users')

    users = User.objects.select_related('profile', 'speaker').order_by('-date_joined')
    admin_exists = users.filter(is_superuser=True).exists()
    return render(request, 'admin_panel/Users/admin_users.html', {
        'users': users,
        'member_count': users.count(),
        'staff_count': users.filter(is_staff=True).count(),
        # นับเฉพาะวิทยากรที่ผูกกับผู้ใช้จริง และบัญชียังเปิดใช้งาน
        'speaker_count': Speaker.objects.filter(user__isnull=False, user__is_active=True).count(),
        'can_add_admin': not admin_exists
    })


@login_required
@user_passes_test(is_staff_or_admin)
def manage_users_edit_view(request, user_id):
    user = get_object_or_404(User, id=user_id)
    profile, _ = Profile.objects.get_or_create(user=user)
    speaker = Speaker.objects.filter(user=user).first()

    if request.method == 'POST':
        user.first_name = request.POST.get('first_name', '')
        user.last_name = request.POST.get('last_name', '')
        user.email = request.POST.get('email', '')
        user.is_active = request.POST.get('is_active') == 'on'

        role = request.POST.get('role', 'member')

        if role == 'admin':
            existing_admins = User.objects.filter(is_superuser=True).exclude(id=user.id)
            if existing_admins.exists():
                messages.error(request, 'ไม่สามารถกำหนดผู้ดูแลระบบให้ผู้ใช้นี้ได้ เนื่องจากมีผู้ดูแลระบบอยู่แล้ว')
                return redirect('manage_users')
        user.is_staff = (role == 'admin')
        user.is_superuser = (role == 'admin')
        user.save()

        profile.full_name = f"{(user.first_name or '').strip()} {(user.last_name or '').strip()}".strip()
        profile.phone = request.POST.get('phone', '')
        profile.role = role
        uploaded_image = request.FILES.get('image')

        # Save profile image only for non-speaker accounts (speaker uses Speaker.profile_picture)
        if uploaded_image and role != 'speaker':
            profile.image = uploaded_image
        profile.save()

        if role == 'speaker':
            speaker, _created = Speaker.objects.get_or_create(
                user=user,
                defaults={
                    'name': (profile.full_name or user.get_full_name() or user.username).strip(),
                },
            )

            # Ensure speaker name is never empty (helps list/assign screens)
            if not (speaker.name or '').strip():
                speaker.name = (profile.full_name or user.get_full_name() or user.username).strip()

            if uploaded_image:
                speaker.profile_picture = uploaded_image

            speaker.save(update_fields=['name', 'profile_picture'] if uploaded_image else ['name'])

        # refresh speaker for rendering fallback below if redirect doesn't happen
        speaker = Speaker.objects.filter(user=user).first()

        messages.success(request, 'บันทึกข้อมูลเรียบร้อยแล้ว')
        return redirect('manage_users')

    effective_role = profile.role
    if speaker and effective_role != 'speaker':
        effective_role = 'speaker'

    return render(request, 'admin_panel/Users/admin_edituser.html', {
        'target_user': user,
        'profile': profile,
        'speaker': speaker,
        'effective_role': effective_role,
    })


@login_required
@user_passes_test(is_staff_or_admin)
def manage_users_delete_view(request, user_id):
    user = get_object_or_404(User, id=user_id)
    if user == request.user:
        messages.error(request, 'ไม่สามารถลบบัญชีของตัวเองได้')
    else:
        # ถ้าเป็นวิทยากร ให้เช็คก่อนว่ามีงานที่รับอยู่หรือไม่
        speaker = Speaker.objects.filter(user=user).first()
        if speaker:
            active_statuses = ['pending', 'assigned', 'accepted', 'confirmed']
            has_active_assignments = speaker.assignments.filter(status__in=active_statuses).exists()
            if has_active_assignments:
                messages.error(request, 'ไม่สามารถลบวิทยากรคนนี้ได้ เนื่องจากยังมีงานที่ได้รับมอบหมายอยู่')
                return redirect('manage_users')

            # ✅ เพิ่ม: กันลบวิทยากรถ้ามีผลงาน หรือมีงาน completed แล้ว
            has_work_uploads = speaker.work_uploads.exists()
            has_completed_assignments = speaker.assignments.filter(status='completed').exists()
            if has_work_uploads or has_completed_assignments:
                messages.error(request, 'ไม่สามารถลบบัญชีวิทยากรได้ เนื่องจากมีประวัติผลงานหรือมีงานที่ปิดงานแล้ว')
                return redirect('manage_users')

        try:
            user.delete()
            messages.success(request, 'ลบผู้ใช้งานเรียบร้อยแล้ว')
        except ProtectedError:
            messages.error(request, 'ไม่สามารถลบผู้ใช้งานได้ เนื่องจากมีข้อมูลที่เกี่ยวข้อง (ประวัติการจอง/บัญชีวิทยากร)')
    return redirect('manage_users')


# ---------------------------------------------------------------------
# Silk Pattern Management
# ---------------------------------------------------------------------
@login_required
@user_passes_test(is_staff_or_admin)
def manage_silk_patterns_add_view(request):
    import os
    import logging
    form = SilkPatternForm(request.POST or None, request.FILES or None)
    log = logging.getLogger(__name__)

    latest_si_id = (
        SilkPattern.objects.exclude(Si_ID__isnull=True)
        .exclude(Si_ID="")
        .order_by("-id")
        .values_list("Si_ID", flat=True)
        .first()
    )

    if request.method == 'POST' and form.is_valid():
        mind_file = request.FILES.get('mind_file')

        # normalize filename (prevent path traversal, keep it consistent)
        safe_mind_name = None
        if mind_file:
            safe_mind_name = os.path.basename(getattr(mind_file, 'name', '') or '').strip()

        # ตรวจสอบนามสกุลไฟล์ .mind ถ้ามีการอัปโหลด
        if mind_file and not safe_mind_name.lower().endswith('.mind'):
            form.add_error('mind_file', 'กรุณาอัปโหลดเฉพาะไฟล์นามสกุล .mind เท่านั้น')
        else:
            # ถ้ามีไฟล์ .mind ใหม่ ให้เซต target_file ใน instance ก่อน save
            if mind_file and safe_mind_name:
                form.instance.target_file = safe_mind_name[:100]
                mind_name = safe_mind_name
                exists = SilkPattern.objects.filter(target_file=mind_name).exists()
                if not exists:
                    form.instance.target_index = 0
            try:
                pattern = form.save()
            except Exception as e:
                log.exception("[SILK_ADD] Failed to save SilkPattern (upload/storage error): %s", e)
                messages.error(request, "บันทึกลายผ้าไม่สำเร็จ (อัปโหลดไฟล์มีปัญหา) โปรดลองใหม่")
                return render(request, 'admin_panel/Silk/admin_editsilk.html', {
                    'form': form,
                    'title': 'เพิ่มลายผ้าใหม่',
                    'latest_si_id': latest_si_id,
                })

            # ถ้ามีไฟล์ .mind ให้บันทึกลง static/main/targets
            if mind_file and safe_mind_name:
                try:
                    targets_dir = os.path.join(settings.BASE_DIR, 'main', 'static', 'main', 'targets')
                    os.makedirs(targets_dir, exist_ok=True)
                    dest_path = os.path.join(targets_dir, safe_mind_name)
                    with open(dest_path, 'wb+') as destination:
                        for chunk in mind_file.chunks():
                            destination.write(chunk)
                except Exception as e:
                    # Some hosts can be read-only; don't crash the whole request.
                    log.exception("[SILK_ADD] Failed to write .mind file to static targets: %s", e)
                    messages.warning(request, "อัปโหลดสำเร็จ แต่บันทึกไฟล์ .mind ลงเซิร์ฟเวอร์ไม่ได้ (บางโฮสต์เป็น read-only)")

            # คัดลอกไฟล์ image / model ไปเก็บซ้ำใน static/main/images และ static/main/models
            try:
                import os, shutil
                static_main_dir = os.path.join(settings.BASE_DIR, 'main', 'static', 'main')
                images_dir = os.path.join(static_main_dir, 'images')
                models_dir = os.path.join(static_main_dir, 'models')
                os.makedirs(images_dir, exist_ok=True)
                os.makedirs(models_dir, exist_ok=True)

                if pattern.image:
                    src = getattr(pattern.image, 'path', None)
                    if src and os.path.exists(src):
                        shutil.copy2(src, os.path.join(images_dir, os.path.basename(src)))

                for field_name in ['model_3d']:
                    f = getattr(pattern, field_name, None)
                    src = getattr(f, 'path', None) if f else None
                    if src and os.path.exists(src):
                        shutil.copy2(src, os.path.join(models_dir, os.path.basename(src)))
            except Exception:
                pass

            messages.success(request, 'เพิ่มลายผ้าไหมเรียบร้อยแล้ว')
            return redirect('manage_silk_patterns')

    return render(request, 'admin_panel/Silk/admin_editsilk.html', {
        'form': form,
        'title': 'เพิ่มลายผ้าใหม่',
        'latest_si_id': latest_si_id,
    })



@login_required
@user_passes_test(is_staff_or_admin)
def manage_silk_edit_view(request, pattern_id):
    import os
    import logging
    from .models import SilkPatternGalleryImage
    pattern = get_object_or_404(SilkPattern, id=pattern_id)
    form = SilkPatternForm(request.POST or None, request.FILES or None, instance=pattern)
    log = logging.getLogger(__name__)

    latest_si_id = (
        SilkPattern.objects.exclude(Si_ID__isnull=True)
        .exclude(Si_ID="")
        .order_by("-id")
        .values_list("Si_ID", flat=True)
        .first()
    )

    if request.method == 'POST' and form.is_valid():
        mind_file = request.FILES.get('mind_file')

        # normalize filename (prevent path traversal, keep it consistent)
        safe_mind_name = None
        if mind_file:
            safe_mind_name = os.path.basename(getattr(mind_file, 'name', '') or '').strip()

        if mind_file and not safe_mind_name.lower().endswith('.mind'):
            form.add_error('mind_file', 'กรุณาอัปโหลดเฉพาะไฟล์นามสกุล .mind เท่านั้น')
        else:
            # ถ้ามีไฟล์ .mind ใหม่ ให้เซต target_file ใน instance ก่อน save
            if mind_file and safe_mind_name:
                form.instance.target_file = safe_mind_name[:100]
                mind_name = safe_mind_name
                exists = SilkPattern.objects.filter(target_file=mind_name).exists()
                if not exists:
                    form.instance.target_index = 0
            try:
                pattern = form.save()
            except Exception as e:
                log.exception("[SILK_EDIT] Failed to save SilkPattern id=%s (upload/storage error): %s", pattern_id, e)
                messages.error(request, "บันทึกการแก้ไขไม่สำเร็จ (อัปโหลดไฟล์มีปัญหา) โปรดลองใหม่")
                gallery_images = pattern.gallery_images.all() if hasattr(pattern, 'gallery_images') else []
                return render(request, 'admin_panel/Silk/admin_editsilk.html', {
                    'form': form,
                    'title': f'แก้ไขข้อมูลผ้าไหม: {pattern.Si_name}',
                    'gallery_images': gallery_images,
                    'latest_si_id': latest_si_id,
                })

            # อัปโหลดรูป gallery images (หลายรูป)
            gallery_files = request.FILES.getlist('gallery_images')
            for f in gallery_files:
                try:
                    SilkPatternGalleryImage.objects.create(silkpattern=pattern, image=f)
                except Exception as e:
                    log.exception("[SILK_EDIT] Failed to save gallery image for pattern id=%s: %s", pattern_id, e)
                    messages.warning(request, "อัปโหลดรูปแกลเลอรีบางไฟล์ไม่สำเร็จ")

            if mind_file and safe_mind_name:
                try:
                    targets_dir = os.path.join(settings.BASE_DIR, 'main', 'static', 'main', 'targets')
                    os.makedirs(targets_dir, exist_ok=True)
                    dest_path = os.path.join(targets_dir, safe_mind_name)
                    with open(dest_path, 'wb+') as destination:
                        for chunk in mind_file.chunks():
                            destination.write(chunk)
                except Exception as e:
                    log.exception("[SILK_EDIT] Failed to write .mind file to static targets: %s", e)
                    messages.warning(request, "อัปโหลดสำเร็จ แต่บันทึกไฟล์ .mind ลงเซิร์ฟเวอร์ไม่ได้ (บางโฮสต์เป็น read-only)")

            # คัดลอกไฟล์ image / model ไปเก็บซ้ำใน static/main/images และ static/main/models
            try:
                import os, shutil
                static_main_dir = os.path.join(settings.BASE_DIR, 'main', 'static', 'main')
                images_dir = os.path.join(static_main_dir, 'images')
                models_dir = os.path.join(static_main_dir, 'models')
                os.makedirs(images_dir, exist_ok=True)
                os.makedirs(models_dir, exist_ok=True)

                if pattern.image:
                    src = getattr(pattern.image, 'path', None)
                    if src and os.path.exists(src):
                        shutil.copy2(src, os.path.join(images_dir, os.path.basename(src)))

                for field_name in ['model_3d']:
                    f = getattr(pattern, field_name, None)
                    src = getattr(f, 'path', None) if f else None
                    if src and os.path.exists(src):
                        shutil.copy2(src, os.path.join(models_dir, os.path.basename(src)))
            except Exception:
                pass

            messages.success(request, 'แก้ไขข้อมูลเรียบร้อยแล้ว')
            return redirect('manage_silk_patterns')

    # ดึงรูป gallery images ทั้งหมดของลายผ้านี้
    gallery_images = pattern.gallery_images.all() if hasattr(pattern, 'gallery_images') else []

    return render(request, 'admin_panel/Silk/admin_editsilk.html', {
        'form': form,
        'title': f'แก้ไขข้อมูลผ้าไหม: {pattern.Si_name}',
        'gallery_images': gallery_images,
        'latest_si_id': latest_si_id,
    })


@login_required
@user_passes_test(is_staff_or_admin)
def manage_silk_delete_view(request, pattern_id):
    pattern = get_object_or_404(SilkPattern, id=pattern_id)
    pattern.delete()
    messages.success(request, 'ลบข้อมูลเรียบร้อยแล้ว')
    return redirect('manage_silk_patterns')


# ---------------------------------------------------------------------
# Speaker Assignment
# ---------------------------------------------------------------------
@login_required
@user_passes_test(is_staff_or_admin)
def manage_questions_add_view(request):
    """ฟังก์ชันสำหรับเพิ่มคำถามใหม่จากหน้า Admin"""
    if request.method == 'POST':
        form = QuestionForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, 'เพิ่มคำถามเรียบร้อยแล้ว')
            return redirect('manage_questions')
    else:
        form = QuestionForm()

    return render(request, 'admin_panel/Question/form_questions.html', {
        'form': form,
        'title': 'เพิ่มคำถามใหม่'
    })


@login_required
@user_passes_test(is_staff_or_admin)
def manage_questions_edit_view(request, question_id):
    """ฟังก์ชันสำหรับแก้ไขคำถาม"""
    question = get_object_or_404(Question, id=question_id)
    if request.method == 'POST':
        form = QuestionForm(request.POST, instance=question)
        if form.is_valid():
            form.save()
            messages.success(request, 'แก้ไขคำถามเรียบร้อยแล้ว')
            return redirect('manage_questions')
    else:
        form = QuestionForm(instance=question)

    return render(request, 'admin_panel/Question/form_questions.html', {
        'form': form,
        'title': f'แก้ไขคำถาม: {question.id}'
    })

@login_required
@user_passes_test(is_staff_or_admin)
def manage_questions_delete_view(request, question_id):
    """ฟังก์ชันสำหรับลบคำถาม"""
    question = get_object_or_404(Question, id=question_id)
    try:
        question.delete()
        messages.success(request, 'ลบคำถามเรียบร้อยแล้ว')
    except ProtectedError:
        messages.error(request, 'ไม่สามารถลบคำถามนี้ได้ เนื่องจากมีผู้ตอบคำถามแล้ว')
    return redirect('manage_questions')

@login_required
def speaker_edit_view(request, speaker_id):
    # ดึงข้อมูลวิทยากร หรือส่งกลับหน้า 404 ถ้าไม่พบ
    speaker = get_object_or_404(Speaker, id=speaker_id)

    # ตรวจสอบสิทธิ์ (ป้องกันไม่ให้วิทยากรคนอื่นมาแก้ข้อมูลกันเอง)
    user_speaker = Speaker.objects.filter(user=request.user).first()
    if not user_speaker or user_speaker.id != speaker.id:
        return redirect('speaker_dashboard')

    if request.method == 'POST':
        # ตรงนี้ต้องใช้ Form สำหรับแก้ไขข้อมูล (ถ้ามี SpeakerForm)
        # ตัวอย่างการอัปเดตแบบง่าย:
        speaker.name = (request.POST.get('name') or '').strip()
        speaker.expertise = (request.POST.get('expertise') or '').strip()
        speaker.biography = (request.POST.get('biography') or '').strip()
        if 'profile_picture' in request.FILES:
            speaker.profile_picture = request.FILES['profile_picture']
        speaker.save()
        messages.success(request, 'บันทึกข้อมูลวิทยากรเรียบร้อยแล้ว')
        return redirect('speaker_dashboard')

    return render(request, 'speaker/speaker_edit.html', {'speaker': speaker})
# ---------------------------------------------------------------------
# Events (Workshop) Management - CRUD
# ---------------------------------------------------------------------

@login_required
@user_passes_test(is_staff_or_admin)
def admin_events_list_view(request):
    """1. หน้าแสดงรายการกิจกรรมทั้งหมด (Read)"""
    from django.db.models import Count

    workshops = (
        Workshop.objects.annotate(current_bookings=Count("workshopbooking"))
        .order_by("-id")
    )
    return render(request, "admin_panel/Evens/admin_events_list.html", {
        "workshops": workshops,
    })

# คัดลอกไปวางทับฟังก์ชันเดิมใน views.py

@login_required
@user_passes_test(is_staff_or_admin)
def admin_events_add_view(request):
    import logging
    log = logging.getLogger(__name__)
    if request.method == "POST":
        form = WorkshopForm(request.POST, request.FILES)
        if form.is_valid():
            try:
                workshop = form.save()
            except Exception as e:
                log.exception("[WORKSHOP_ADD] Failed to save Workshop (upload/storage error): %s", e)
                messages.error(request, "เพิ่มกิจกรรมไม่สำเร็จ (อัปโหลดไฟล์มีปัญหา) โปรดลองใหม่")
                return render(request, "admin_panel/Evens/admin_events_form.html", {
                    "title": "เพิ่มกิจกรรมใหม่",
                    "form": form,
                })
            # บันทึกรูปประกอบกิจกรรมหลายรูป (ถ้ามีอัปโหลดมา)
            gallery_files = request.FILES.getlist('gallery_images')
            for f in gallery_files:
                if f:
                    try:
                        WorkshopGalleryImage.objects.create(workshop=workshop, image=f)
                    except Exception as e:
                        log.exception("[WORKSHOP_ADD] Failed to save gallery image: %s", e)
                        messages.warning(request, "อัปโหลดรูปแกลเลอรีบางไฟล์ไม่สำเร็จ")
            messages.success(request, "เพิ่มกิจกรรมเรียบร้อยแล้ว")
            return redirect("admin_events_list")
    else:
        form = WorkshopForm()

    return render(request, "admin_panel/Evens/admin_events_form.html", {
        "title": "เพิ่มกิจกรรมใหม่",
        "form": form,
    })

@login_required
@user_passes_test(is_staff_or_admin)
def admin_events_edit_view(request, workshop_id):
    """3. หน้าแก้ไขกิจกรรม (Update)"""
    import logging
    log = logging.getLogger(__name__)
    workshop = get_object_or_404(Workshop, id=workshop_id)
    if request.method == "POST":
        # กรณีกดปุ่มลบรูปประกอบจากแกลเลอรี
        if 'delete_gallery_image' in request.POST:
            image_id = request.POST.get('delete_gallery_image')
            if image_id:
                image = get_object_or_404(WorkshopGalleryImage, id=image_id, workshop=workshop)
                image.delete()
                messages.success(request, 'ลบรูปประกอบกิจกรรมเรียบร้อยแล้ว')
            return redirect('admin_events_edit', workshop_id=workshop.id)

        form = WorkshopForm(request.POST, request.FILES, instance=workshop)
        if form.is_valid():
            try:
                workshop = form.save()
            except Exception as e:
                log.exception("[WORKSHOP_EDIT] Failed to save Workshop id=%s (upload/storage error): %s", workshop_id, e)
                messages.error(request, "บันทึกการแก้ไขไม่สำเร็จ (อัปโหลดไฟล์มีปัญหา) โปรดลองใหม่")
                return render(request, "admin_panel/Evens/admin_events_form.html", {
                    "form": form,
                    "workshop": workshop,
                    "title": f"แก้ไขกิจกรรม: {workshop.title}",
                })
            # เพิ่มรูปประกอบกิจกรรมเพิ่มเติม (ไม่ลบของเดิม)
            gallery_files = request.FILES.getlist('gallery_images')
            for f in gallery_files:
                if f:
                    try:
                        WorkshopGalleryImage.objects.create(workshop=workshop, image=f)
                    except Exception as e:
                        log.exception("[WORKSHOP_EDIT] Failed to save gallery image for workshop id=%s: %s", workshop_id, e)
                        messages.warning(request, "อัปโหลดรูปแกลเลอรีบางไฟล์ไม่สำเร็จ")
            messages.success(request, "แก้ไขข้อมูลกิจกรรมเรียบร้อยแล้ว")
            return redirect("admin_events_list") # กลับหน้า List
    else:
        form = WorkshopForm(instance=workshop)

    return render(request, "admin_panel/Evens/admin_events_form.html", {
        "form": form,
        "workshop": workshop,
        "title": f"แก้ไขกิจกรรม: {workshop.title}"
    })

@login_required
@user_passes_test(is_staff_or_admin)
def admin_events_delete_view(request, workshop_id):
    """4. ลบกิจกรรม (Delete)"""
    workshop = get_object_or_404(Workshop, id=workshop_id)
    try:
        workshop.delete()
        messages.success(request, 'ลบกิจกรรมเรียบร้อยแล้ว')
    except ProtectedError:
        messages.error(request, 'ไม่สามารถลบกิจกรรมนี้ได้ เนื่องจากมีการจองหรือกิจกรรมสิ้นสุดแล้ว')
    return redirect('admin_events_list')

@login_required
@user_passes_test(is_staff_or_admin)
def admin_delete_booking_view(request, booking_id):
    """ผู้ดูแลระบบลบรายการจอง"""
    booking = get_object_or_404(Booking, id=booking_id)
    try:
        booking.delete()
        messages.success(request, 'ลบรายการจองเรียบร้อยแล้ว')
    except ProtectedError:
        messages.error(request, 'ไม่สามารถลบการจองได้ เนื่องจากมีการมอบหมายวิทยากรหรือมีการทำแบบประเมินแล้ว')
    return redirect('approve_bookings')

def ar_test_view(request):
    # ดึงเฉพาะรายการที่มีไฟล์โมเดล (เก่า หรือ silk/mannequin) และมีการตั้งค่า target_index ไว้
    patterns = (
        SilkPattern.objects.exclude(target_index__isnull=True)
        .filter(Q(model_3d__isnull=False))
        .prefetch_related('gallery_images')
        .order_by('target_index')
    )

    # กำหนด transform เริ่มต้น (หมุน X 90 องศา, scale 1.2, ขยับขึ้น 0.1)
    default_transform = {
        "scale": 1.2,
        "position": {"x": 0, "y": 0.1, "z": 0},
        "rotation": {"x": 90, "y": 0, "z": 0}
    }

    # ถ้า query param ระบุไฟล์ .mind ให้ใช้ไฟล์นั้นเป็นเป้าหมายหลัก
    mind_param = request.GET.get('mind')

    # เลือกไฟล์ .mind ที่ใช้ (ตามพารามิเตอร์หรือไฟล์ล่าสุด)
    import os, re, glob
    target_file_url = None
    chosen_target = None
    static_targets_dir = os.path.join(settings.BASE_DIR, 'main', 'static', 'main', 'targets')

    # list all .mind files for UI switching
    mind_files = []
    try:
        mind_paths = glob.glob(os.path.join(static_targets_dir, '*.mind'))
        mind_paths_sorted = sorted(mind_paths, key=os.path.getmtime, reverse=True)
        mind_files = [os.path.basename(p) for p in mind_paths_sorted]
    except Exception:
        mind_files = []

    try:
        if mind_param:
            candidate = os.path.join(static_targets_dir, mind_param)
            if os.path.exists(candidate):
                chosen_target = mind_param
                target_file_url = request.build_absolute_uri(settings.STATIC_URL + f'main/targets/{chosen_target}')

        if not target_file_url:
            # Prefer the most recently modified .mind file (covers targets.mind and targetsX.mind)
            files = glob.glob(os.path.join(static_targets_dir, '*.mind'))
            if files:
                newest_path = max(files, key=os.path.getmtime)
                chosen_target = os.path.basename(newest_path)
                target_file_url = request.build_absolute_uri(settings.STATIC_URL + f'main/targets/{chosen_target}')
    except Exception:
        target_file_url = None

    # ถ้าไม่พบไฟล์ ให้ fallback ไปที่ targets0.mind ดังเดิม
    if not target_file_url:
        chosen_target = 'targets0.mind'
        target_file_url = request.build_absolute_uri(settings.STATIC_URL + 'main/targets/targets0.mind')

    # ถ้าใน DB มีการระบุ target_file ให้กรองให้ตรงกับไฟล์ .mind ที่เลือก
    # และรวมรายการที่ยังไม่ถูกตั้งค่า target_file (เพื่อให้แสดงทุกลายที่เพิ่ม)
    try:
        if chosen_target:
            with_target = patterns.filter(target_file=chosen_target)
            if with_target.exists():
                patterns = with_target | patterns.filter(target_file__isnull=True) | patterns.filter(target_file='')
    except Exception:
        pass

    # [FIX] ตรวจสอบว่าเป็นไฟล์ targetsX.mind แบบแยกหรือไม่
    # UPDATE: ยกเลิกการกรอง ID จากชื่อไฟล์ ให้ถือว่า targetsX.mind เป็นแค่ Version ของไฟล์รวม
    single_target_id = -1
    # if chosen_target:
    #     m = re.search(r'targets(\d+)\.mind$', chosen_target)
    #     if m:
    #         single_target_id = int(m.group(1))

    patterns_list = []
    ordered_patterns = list(patterns.order_by('target_index'))
    for p in ordered_patterns:
        # สร้าง URL ให้เป็น absolute เพื่อหลีกเลี่ยงปัญหา CORS/relative path
        base_model_url = request.build_absolute_uri(p.model_3d.url) if getattr(p, 'model_3d', None) else ''
        silk_model_url = base_model_url
        mannequin_model_url = ''
        # ถ้าใน DB มีค่า transform เฉพาะ ให้ใช้ค่าเหล่านั้น (รองรับ JSON text หรือค่าตายตัว)
        transform_val = default_transform
        try:
            if getattr(p, 'transform', None):
                # ถ้าเป็น string พยายาม parse เป็น JSON
                if isinstance(p.transform, str) and p.transform.strip():
                    transform_val = json.loads(p.transform)
                elif isinstance(p.transform, dict):
                    transform_val = p.transform
        except Exception:
            transform_val = default_transform

        # [FIX] Logic การ map index
        p_idx = int(p.target_index) if p.target_index is not None else 0
        final_index = p_idx

        # ข้าม Logic กรอง Single Target เพื่อให้โหลดครบทุกอัน
        # if single_target_id != -1:
        #     if p_idx != single_target_id:
        #         continue
        #     final_index = 0

        image_url = request.build_absolute_uri(p.reference.url) if getattr(p, 'reference', None) else ''
        images = []
        if image_url:
            images.append(image_url)
        try:
            for gi in p.gallery_images.all().order_by('created_at'):
                if getattr(gi, 'image', None):
                    images.append(request.build_absolute_uri(gi.image.url))
        except Exception:
            pass
        # unique, keep order
        images = list(dict.fromkeys([x for x in images if x]))

        patterns_list.append({
            'index': final_index,
            'source_index': p_idx,
            # model_url ยังคงไว้เพื่อ backward compatibility (ใช้ silk_model เป็นหลัก)
            'model_url': silk_model_url,
            'silk_model_url': silk_model_url,
            'mannequin_model_url': mannequin_model_url,
            'name': p.Si_name,
            # ฟิลด์ดิบทั้งหมดของลายผ้า (ใช้สำหรับแสดงรายละเอียดหลังสแกน AR)
            'si_id': p.Si_ID,
            'si_type': p.Si_type,
            'si_color': p.Si_color,
            'si_address': p.Si_address,
            'si_history': p.Si_history,
            'si_main_artist': getattr(p, 'Si_main_artist', '') or '',
            'si_assistant_artists': getattr(p, 'Si_assistant_artists', '') or '',
            'si_contact_phone': getattr(p, 'Si_contact_phone', '') or '',
            # สรุปสั้นใต้ชื่อ: ใช้ประเภท/สีผ้า ไม่ดึงประวัติยาวเพื่อเลี่ยงข้อมูลซ้ำ
            'detail': p.Si_type or p.Si_color or "ผ้าไหมไทยลวดลายเอกลักษณ์",
            'transform': transform_val,
            'target_file': p.target_file or '',
            'image_url': image_url,
            # รูปเพิ่มเติม (ถ้ามี) สำหรับหน้า "รูปผ้าไหมเพิ่มเติม"
            'images': images,
        })

    # แปลงข้อมูลเป็น JSON เพื่อให้ JavaScript นำไปใช้ต่อได้ง่าย
    patterns_json = json.dumps(patterns_list, cls=DjangoJSONEncoder)

    context = {
        'patterns_json': patterns_json,
        'target_file_url': target_file_url,
        'chosen_target': chosen_target,
        'mind_files': mind_files,
    }
    return render(request, 'main/ar_view.html', context)

@login_required
@user_passes_test(is_staff_or_admin)
@require_POST
def silk_gallery_image_delete(request, image_id):
    img = get_object_or_404(SilkPatternGalleryImage, id=image_id)

    try:
        # ลบไฟล์จริงใน storage ก่อน
        if img.image:
            img.image.delete(save=False)

        # ลบ record ใน DB
        img.delete()

        return JsonResponse({"ok": True})
    except Exception as e:
        return JsonResponse({"ok": False, "error": str(e)}, status=400)
# =====================================================================
# ส่วนที่ 9 หมวดหมู่ระบบแดชบอร์ดผู้ดูแลระบบ (CLEAN VERSION)
# =====================================================================
# ==============================
# Work Gallery (Admin)
# ==============================
from django.contrib.auth.decorators import login_required, user_passes_test
from django.db.models import Q

def work_gallery_view(request):
    from .models import Speaker, SpeakerWorkUpload

    q = (request.GET.get("q") or "").strip()
    speaker_id = (request.GET.get("speaker") or "").strip()

    uploads = (
        SpeakerWorkUpload.objects
        .select_related("speaker", "assignment")
        .prefetch_related("images")
        .all()
    )

    # ถ้า SpeakerAssignment ของคุณมี FK ไป Booking ชื่อ booking
    # จะช่วยให้ template เรียก upload.assignment.booking ได้
    try:
        uploads = uploads.select_related("assignment__booking")
    except Exception:
        pass

    if speaker_id.isdigit():
        uploads = uploads.filter(speaker_id=int(speaker_id))

    if q:
        uploads = uploads.filter(
            Q(title__icontains=q)
            | Q(note__icontains=q)
            | Q(speaker__name__icontains=q)
        )

    # แสดงเฉพาะวิทยากรที่ยังมีบัญชีผู้ใช้และยังใช้งานได้
    speakers = Speaker.objects.filter(user__isnull=False, user__is_active=True).order_by("name")

    return render(request, "main/work_gallery.html", {
        "uploads": uploads,
        "speakers": speakers,
        "q": q,
        "speaker_id": speaker_id,
        "title": "แกลเลอรี่ผลงานวิทยากร",
    })
from django.utils import timezone
from django.db.models import Count, Sum
from django.shortcuts import render
from django.contrib.auth.decorators import login_required, user_passes_test

from .models import Booking


def is_staff_or_admin(user):
    return user.is_authenticated and (user.is_staff or user.is_superuser)


@login_required
@user_passes_test(is_staff_or_admin)
def admin_booking_visit_report_view(request):
    today = timezone.localdate()

    # รับค่ากรองจาก GET
    start_date = (request.GET.get("start_date") or "").strip()
    end_date = (request.GET.get("end_date") or "").strip()
    status = (request.GET.get("status") or "").strip()

    # ดึงข้อมูล
    qs = Booking.objects.select_related("workshop").all()

    # กรองช่วงวันที่
    if start_date:
        qs = qs.filter(Re_date__gte=start_date)
    if end_date:
        qs = qs.filter(Re_date__lte=end_date)

    # กรองสถานะ
    if status:
        qs = qs.filter(Re_status=status)

    qs = qs.order_by("-Re_date", "-id")
    # Freeze dataset so summary and table always match the exact same rows.
    bookings = list(qs)

    # choices สถานะ
    try:
        status_choices = list(Booking._meta.get_field("Re_status").choices)
    except Exception:
        status_choices = Booking.STATUS_CHOICES

    selected_status_label = "ทั้งหมด"
    if status:
        for value, label in status_choices:
            if value == status:
                selected_status_label = label
                break

    # Summary หลัก (คำนวณจากชุดข้อมูลเดียวกับที่แสดงในตาราง)
    total_bookings = len(bookings)
    total_people = sum((b.Re_quantity or 0) for b in bookings)

    # นับแยกตามสถานะ
    status_count_map = {}
    for b in bookings:
        key = b.Re_status
        status_count_map[key] = status_count_map.get(key, 0) + 1

    # ทำ list สำหรับแสดงผลใน template แบบชัวร์ ไม่ต้องใช้ get_item
    status_summary = []
    accounted = 0
    for value, label in status_choices:
        count = status_count_map.get(value, 0)
        accounted += count
        status_summary.append({"value": value, "label": label, "count": count})

    # เผื่อมีข้อมูลเก่าหรือค่าว่าง/ไม่อยู่ใน choices จะทำให้ยอดรวมไม่ตรงกัน
    other_count = total_bookings - accounted
    if other_count > 0:
        status_summary.append(
            {
                "value": "__other__",
                "label": "อื่นๆ / ไม่ทราบสถานะ",
                "count": other_count,
            }
        )

    context = {
        "title": "ข้อมูลการจอง",
        "today": today,
        # ซ่อนเวลาในหัวรายงานหน้านี้ (base template จะแสดงเวลาเมื่อมี now)
        "now": None,
        "single_container": True,
        "bookings": bookings,
        "status_choices": status_choices,
        "selected_status_label": selected_status_label,
        "filters": {
            "start_date": start_date,
            "end_date": end_date,
            "status": status,
        },
        "total_bookings": total_bookings,
        "total_people": total_people,
        "summary": {
            "total": total_bookings,
            "total_people": total_people,
            "approved": status_count_map.get("approved", 0),
            "completed": status_count_map.get("completed", 0),
        },
        "status_summary": status_summary,
    }

    return render(request, "admin_panel/report/booking_visit_report.html", context)


@login_required
@user_passes_test(is_staff_or_admin)
def admin_users_report_view(request):
    from django.contrib.auth import get_user_model
    from django.db.models import Q
    from django.utils import timezone

    UserModel = get_user_model()
    today = timezone.localdate()

    order = (request.GET.get("order") or "newest").strip().lower()
    if order not in {"newest", "oldest"}:
        order = "newest"

    # filter by role via query string ?role=member|speaker|admin
    # รองรับของเดิมที่เคยใช้ชื่อ param เป็น status ด้วย
    role = (request.GET.get("role") or request.GET.get("status") or "all").strip().lower()
    if role not in {"all", "member", "speaker", "admin"}:
        role = "all"

    users_qs = UserModel.objects.all()

    # role filter (optional)
    if role == "speaker":
        users_qs = users_qs.filter(profile__role="speaker")
    elif role == "admin":
        users_qs = users_qs.filter(
            Q(profile__role="admin") | Q(is_staff=True) | Q(is_superuser=True)
        ).distinct()
    elif role == "member":
        users_qs = users_qs.filter(
            Q(is_staff=False)
            & Q(is_superuser=False)
            & (Q(profile__role="member") | Q(profile__isnull=True))
        ).distinct()

    total_users = users_qs.count()

    speaker_count = users_qs.filter(profile__role="speaker").count()
    admin_count = (
        users_qs.filter(Q(profile__role="admin") | Q(is_staff=True) | Q(is_superuser=True))
        .distinct()
        .count()
    )
    member_count = (
        users_qs.filter(
            Q(is_staff=False)
            & Q(is_superuser=False)
            & (Q(profile__role="member") | Q(profile__isnull=True))
        )
        .distinct()
        .count()
    )

    users = (
        users_qs.select_related("profile")
        .order_by("date_joined" if order == "oldest" else "-date_joined")
    )[:50]

    role_label_map = {
        "member": "ผู้ใช้งาน",
        "speaker": "วิทยากร",
        "admin": "ผู้ดูแลระบบ",
    }
    for u in users:
        profile = getattr(u, "profile", None)
        role = getattr(profile, "role", None)
        if role == "admin" or getattr(u, "is_staff", False) or getattr(u, "is_superuser", False):
            u.profile_role_label = role_label_map["admin"]
        else:
            u.profile_role_label = role_label_map.get(role, role or "-")

    role_filter_label_map = {
        "all": "ทั้งหมด",
        "member": "ผู้ใช้งาน",
        "speaker": "วิทยากร",
        "admin": "ผู้ดูแลระบบ",
    }
    selected_role_label = role_filter_label_map.get(role, "ทั้งหมด")

    context = {
        "title": "ข้อมูลผู้ใช้งาน",
        "today": today,
        "now": None,
        "single_container": True,
        "users": users,
        "filters": {
            "role": role,
            "order": order,
        },
        "selected_role_label": selected_role_label,
        "summary": {
            "total": total_users,
            "member": member_count,
            "speaker": speaker_count,
            "admin": admin_count,
        },
    }
    return render(request, "admin_panel/report/users_report.html", context)


@login_required
@user_passes_test(is_staff_or_admin)
def admin_silk_report_view(request):
    from django.utils import timezone

    from .models import SilkPattern, SilkPatternRating

    today = timezone.localdate()

    total_patterns = SilkPattern.objects.count()

    top_patterns = SilkPattern.objects.order_by("Si_ID")

    context = {
        "title": "ข้อมูลผ้าไหม",
        "today": today,
        "now": None,
        "single_container": True,
        "top_patterns": top_patterns,
        "summary": {
            "total_patterns": total_patterns,
        },
    }
    return render(request, "admin_panel/report/silk_report.html", context)


@login_required
@user_passes_test(is_staff_or_admin)
def admin_events_report_view(request):
    from django.db.models import Count
    from django.utils import timezone

    from .models import Workshop, WorkshopBooking

    today = timezone.localdate()

    # Filter by booking created date to avoid accumulating multi-year data
    period = (request.GET.get("period") or "").strip().lower() or "3m"
    if period not in {"3m", "1y", "all"}:
        period = "3m"

    range_start = None
    range_end = timezone.now()
    if period == "3m":
        range_start = today - timedelta(days=90)
        period_label = "3 เดือนล่าสุด"
    elif period == "1y":
        range_start = today - timedelta(days=365)
        period_label = "1 ปีล่าสุด"
    else:
        period_label = "ทั้งหมด"

    range_start_dt = None
    range_end_dt = None
    if range_start:
        range_start_dt = datetime.combine(range_start, time.min)
        range_end_dt = datetime.combine(today + timedelta(days=1), time.min)
        if getattr(settings, "USE_TZ", False):
            tz = timezone.get_current_timezone()
            if timezone.is_naive(range_start_dt):
                range_start_dt = timezone.make_aware(range_start_dt, tz)
            if timezone.is_naive(range_end_dt):
                range_end_dt = timezone.make_aware(range_end_dt, tz)

    total_workshops = Workshop.objects.count()
    active_workshops = Workshop.objects.filter(is_active=True).count()

    bookings_qs = WorkshopBooking.objects.all()
    if range_start_dt and range_end_dt:
        bookings_qs = bookings_qs.filter(created_at__gte=range_start_dt, created_at__lt=range_end_dt)

    total_bookings = bookings_qs.count()

    if range_start_dt and range_end_dt:
        booking_count_expr = Count(
            "workshopbooking",
            filter=Q(workshopbooking__created_at__gte=range_start_dt, workshopbooking__created_at__lt=range_end_dt),
        )
    else:
        booking_count_expr = Count("workshopbooking")

    top_workshops = (
        Workshop.objects.annotate(booking_count=booking_count_expr)
        .order_by("-booking_count", "title")
    )

    if period != "all":
        top_workshops = top_workshops.filter(booking_count__gt=0)

    top_workshops = top_workshops[:20]

    context = {
        "title": "ข้อมูลกิจกรรม",
        "today": today,
        "now": None,
        "single_container": True,
        "top_workshops": top_workshops,
        "period": period,
        "period_label": period_label,
        "range_start": range_start,
        "range_end": today,
        "summary": {
            "total_workshops": total_workshops,
            "active_workshops": active_workshops,
            "total_bookings": total_bookings,
        },
    }
    return render(request, "admin_panel/report/events_report.html", context)