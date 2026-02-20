# =====================================================================
# museum/views.py
# =====================================================================
"""
Views สำหรับระบบพิพิธภัณฑ์ผ้าไหม
- Public Pages
- Utilities / Decorators
- Auth Helpers
"""

# =====================================================================
# IMPORTS
# =====================================================================
import json
from datetime import datetime, time, timedelta
from urllib.parse import quote_plus
from django.core.serializers.json import DjangoJSONEncoder

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import authenticate, login, logout, get_user_model
from django.contrib.auth.decorators import login_required, user_passes_test
from django.db import transaction, IntegrityError
from django.db.utils import OperationalError
from django.db.models import Q
from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse
from django.core.files.base import ContentFile
from django.conf import settings
from django.utils import timezone
from django.views.decorators.http import require_POST
from django.http import JsonResponse, Http404
from django.db.models import Max
from .models import Workshop, Booking, WorkshopBooking

User = get_user_model()

# =====================================================================
# MODELS
# =====================================================================
from .models import (
    SilkPattern, Booking, WorkshopBooking, Reservation, ARAsset,
    MuseumProfile, Speaker, SpeakerAssignment, SilkPatternRating,
    SpeakerSchedule, Profile, Workshop, Question
)

# =====================================================================
# FORMS
# =====================================================================
from .forms import (
    LoginForm, SignUpForm, UserEditForm,
    SilkPatternForm, BookingForm, QuestionForm, WorkshopForm,
    MuseumProfileForm,
    ForgotPasswordForm, SetNewPasswordForm,
    SpeakerAssignFromBookingForm, BookingRatingForm
)
from .forms import SurveyRatingForm
# For questionnaire handling
from .models import BookingQuestionResponse, Question as QuestionModel
from .models import SurveyRating
import statistics
import io
import base64


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

def is_admin(user):
    """ตรวจสอบว่าเป็นแอดมินหรือไม่"""
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


def is_speaker(user):
    """
    ตรวจสอบสิทธิ์วิทยากร:
    - Staff / Superuser
    - อยู่ใน Group 'Speaker'
    - มีข้อมูลในตาราง Speaker
    """
    if not user.is_authenticated:
        return False
    return (
        user.is_staff
        or user.is_superuser
        or user.groups.filter(name='Speaker').exists()
        or Speaker.objects.filter(user=user).exists()
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

def ar_showcase_view(request):
    """หน้าแสดงตัวอย่าง AR 5 รูปแบบ"""
    showcases = ARShowcase.objects.all().order_by('target_index')
    return render(request, 'main/ar_showcase.html', {
        'showcases': showcases,
        'title': 'AR Experiences'
    })


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


# รองรับ URL เก่า

def silk_collection(request):
    return collections_view(request)







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

            # สร้าง Profile อัตโนมัติ
            Profile.objects.get_or_create(user=user)

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
                messages.error(request, "ไม่พบข้อมูลผู้ใช้")

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

    museum = MuseumProfile.objects.first()

    return render(request, 'main/base.html', {
        'ar_items': ar_items,
        'museum': museum,
    })


def about_view(request):
    """หน้าเกี่ยวกับพิพิธภัณฑ์"""
    museum = MuseumProfile.objects.first()
    ar_items = _get_latest_ar_items(request, limit=4)

    return render(request, 'museum/about.html', {
        'museum': museum,
        'ar_items': ar_items,
    })


def exhibitions_view(request):
    """หน้านิทรรศการ"""
    return render(request, 'museum/exhibitions.html')


def contact_view(request):
    """หน้าติดต่อ"""
    if request.method == 'POST':
        messages.info(
            request,
            'กรุณาติดต่อผ่านช่องทางโซเชียลที่แสดงบนหน้าได้เลยค่ะ'
        )
        return redirect('contact')

    return render(
        request,
        'museum/contact/contact.html',
        _social_context()
    )


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

    return render(request, 'workshops/workshops_list.html', {
        'workshop': workshop_main,
        'rounds': rounds, # ส่ง 'rounds' ไปแสดงผลใน HTML
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
                ).exclude(Re_status='rejected').exists()
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

                # ถ้าผ่านหมดถึงจะ Success
                messages.success(request, "บันทึกข้อมูลการจองเรียบร้อยแล้ว!")
                return redirect('booking_history')

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
    })

@login_required
@user_passes_test(lambda u: u.is_staff)
def assign_speaker_view(request, booking_id):
    """
    ฟังก์ชันสำหรับ Admin มอบหมายวิทยากรให้กับการจอง
    """
    booking = get_object_or_404(Booking, id=booking_id)
    
    if request.method == "POST":
        speaker_id = request.POST.get('speaker_id')
        title = request.POST.get('title', 'นำชมพิพิธภัณฑ์')
        note = request.POST.get('note', '')

        speaker = get_object_or_404(Speaker, id=speaker_id)
        # ตรวจสอบว่าวิทยากรมีงานในวันเดียวกันหรือยัง (จำกัด 1 งาน/วัน)
        if booking.Re_date:
            conflict = SpeakerAssignment.objects.filter(
                speaker=speaker,
                booking__Re_date=booking.Re_date,
                status__in=['pending', 'assigned', 'accepted', 'confirmed']
            ).exists()
            if conflict:
                messages.warning(request, f'ไม่สามารถมอบหมาย: วิทยากร {speaker.name} มีงานเต็มในวันที่ {booking.Re_date.strftime("%d %b %Y")}')
                return redirect('manage_assignments')

        # บันทึกลง SpeakerAssignment (ใช้ OneToOneField ตาม Model ของคุณ)
        assignment, created = SpeakerAssignment.objects.update_or_create(
            booking=booking,
            defaults={
                'speaker': speaker,
                'title': title,
                'note': note,
                'status': 'assigned'
            }
        )
        
        # อัปเดตสถานะการจองหลักให้สมาชิกทราบ
        booking.Re_status = 'confirmed'
        booking.save()

        messages.success(request, f"มอบหมายวิทยากร {speaker.name} สำเร็จ")
        return redirect('manage_assignments')

    speakers = Speaker.objects.all()
    return render(request, "admin_panel/assign_speaker.html", {
        "booking": booking,
        "speakers": speakers
    })
# =====================================================================
# BOOKING HISTORY (USER)
# =====================================================================

@login_required
def booking_history_view(request):
    """
    ประวัติการจองของผู้ใช้
    """
    # ดึงการจองหลักของผู้ใช้
    bookings = Booking.objects.filter(
        Us_ID=request.user
    ).order_by('-created_at')

    # ดึง WorkshopBooking ที่ยังไม่ผูกกับ Booking (orphan workshops)
    orphan_workshops = WorkshopBooking.objects.filter(
        user=request.user,
        booking__isnull=True
    ).order_by('-date')

    return render(request, 'booking/booking_history.html', {
        'bookings': bookings,
        'orphan_workshops': orphan_workshops,
    })


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
        questionnaire_url = reverse('booking_questionnaire', args=[booking.id])
        # ให้เป็นลิงก์เต็ม
        full_q_url = request.build_absolute_uri(questionnaire_url)
        # If booking already has a saved QR image, use it; otherwise generate and save one
        qr_data = None
        if getattr(booking, 'qr_code', None):
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
                filename = f'booking_{booking.id}_questionnaire.png'
                # save to booking.qr_code
                booking.qr_code.save(filename, ContentFile(buf.read()), save=True)
                qr_data = booking.qr_code.url
            except Exception:
                # fallback to data-uri
                qr_data = _generate_qr_data_uri(full_q_url)

    return render(request, 'booking/booking_detail.html', {
        'booking': booking,
        'questionnaire_available': questions_exist,
        'questionnaire_url': questionnaire_url,
        'questionnaire_qr': qr_data,
    })


@login_required
def booking_questionnaire_view(request, booking_id):
    """แสดงแบบประเมินหลังการเข้าชมสำหรับการจองนั้นๆ และบันทึกคำตอบ"""
    booking = get_object_or_404(Booking, pk=booking_id)

    # ตรวจสิทธิ์: เจ้าของการจองหรือ staff/admin เท่านั้น (วิทยากรไม่จำเป็นต้องทำแบบประเมิน)
    if booking.Us_ID != request.user and not is_staff_or_admin(request.user):
        messages.error(request, "คุณไม่มีสิทธิ์เข้าถึงแบบประเมินนี้")
        return redirect('home')

    # ดึงคำถามที่เปิดใช้งาน
    questions = QuestionModel.objects.filter(is_active=True).order_by('id')

    if request.method == 'POST':
        # ล้างคำตอบเดิมของผู้ใช้สำหรับ booking นี้ (ถ้าต้องการเก็บซ้ำ ให้เปลี่ยนเป็น append)
        BookingQuestionResponse.objects.filter(booking=booking, user=request.user).delete()

        for q in questions:
            key = f'question_{q.id}'
            val = request.POST.get(key)
            if val:
                BookingQuestionResponse.objects.create(
                    booking=booking,
                    question=q,
                    answer=val,
                    user=request.user
                )

        messages.success(request, 'ขอบคุณที่ทำแบบประเมินค่ะ')
        # Ensure a persistent QR image exists for this booking (one booking -> one QR)
        try:
            full_q_url = request.build_absolute_uri(request.path)
            if not getattr(booking, 'qr_code', None):
                import qrcode
                import io as _io
                img = qrcode.make(full_q_url)
                buf = _io.BytesIO()
                img.save(buf, format='PNG')
                buf.seek(0)
                filename = f'booking_{booking.id}_questionnaire.png'
                booking.qr_code.save(filename, ContentFile(buf.read()), save=True)
            qr_data = booking.qr_code.url if booking.qr_code else _generate_qr_data_uri(full_q_url)
        except Exception:
            qr_data = _generate_qr_data_uri(request.build_absolute_uri(request.path))

        return render(request, 'booking/questionnaire_thanks.html', {
            'booking': booking,
            'qr_data': qr_data,
        })

    # For GET, prefer an existing persistent booking.qr_code; generate/save if missing
    try:
        full_q_url = request.build_absolute_uri(request.path)
        if not getattr(booking, 'qr_code', None):
            import qrcode
            import io as _io
            img = qrcode.make(full_q_url)
            buf = _io.BytesIO()
            img.save(buf, format='PNG')
            buf.seek(0)
            filename = f'booking_{booking.id}_questionnaire.png'
            booking.qr_code.save(filename, ContentFile(buf.read()), save=True)
        qr_data = booking.qr_code.url if booking.qr_code else _generate_qr_data_uri(full_q_url)
    except Exception:
        qr_data = _generate_qr_data_uri(request.build_absolute_uri(request.path))

    return render(request, 'booking/questionnaire.html', {
        'booking': booking,
        'questions': questions,
        'qr_data': qr_data,
    })


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
            .order_by('user_id', 'question_id', 'created_at')
        )

        question_map = OrderedDict()
        for r in responses_qs:
            if r.question_id not in question_map:
                question_map[r.question_id] = r.question
        questions = list(question_map.values())

        respondent_map = OrderedDict()
        for r in responses_qs:
            key = r.user_id or f"anon-{r.id}"
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
        base_font = "Helvetica"
        try:
            # พยายามใช้ TH Sarabun New ซึ่งมักมีใน Windows ภาษาไทย
            pdfmetrics.registerFont(TTFont('THSarabunNew', 'C:/Windows/Fonts/THSarabunNew.ttf'))
            base_font = 'THSarabunNew'
        except Exception:
            # ถ้าหาไฟล์ฟอนต์ไม่เจอ จะใช้ Helvetica ตามเดิม
            base_font = "Helvetica"

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
            if r.user_id:
                qstats['respondents'].add(r.user_id)

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

    # อ่านรูปแบบการเรียงลำดับจาก query string
    # - newest: การจองล่าสุดก่อน (ค่าเริ่มต้น)
    # - oldest: การจองเก่าที่สุดก่อน
    order = request.GET.get('order', 'newest')

    base_qs = Booking.objects.annotate(
        response_count=Count('question_responses')
    )

    if order == 'oldest':
        bookings = base_qs.order_by('created_at')
    else:  # 'newest'
        bookings = base_qs.order_by('-created_at')

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

    # ดึงคำตอบทั้งหมดของทุก booking มากลุ่มใน Python
    all_responses = BookingQuestionResponse.objects.values('booking_id', 'answer', 'user_id')
    for r in all_responses:
        bid = r['booking_id']
        stat = stats_map[bid]
        # เก็บ user ที่ทำแบบประเมิน (ถ้ามีข้อมูลผู้ใช้)
        if r['user_id']:
            stat['respondents'].add(r['user_id'])
        # แปลง a-d เป็นคะแนนตัวเลข
        score = answer_score.get(r['answer'])
        if score is not None:
            stat['scores'].append(score)

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

    return render(request, 'admin_panel/booking/booking_responses_summary.html', {
        'bookings': bookings,
        'order': order,
    })


# =====================================================================
# ส่วนที่ 3 หมวดหมู่ระบบการจอง
# =====================================================================





# =====================================================================
# ส่วนที่ 4 หมวดหมู่จัดการหลังบ้านสำหรับ Admin
# =====================================================================
# =====================================================================
# BOOKING MANAGEMENT (Admin)
# =====================================================================

@login_required
@user_passes_test(is_staff_or_admin)
def approve_bookings_view(request):
    pending_bookings = Booking.objects.filter(
        Q(Re_status='pending') | Q(Re_status__isnull=True) | Q(Re_status='')
    ).order_by('created_at')
    
    approved_bookings = Booking.objects.filter(
        Re_status='approved'
    ).order_by('-created_at')[:20]

    return render(request, 'admin_panel/booking/approve_bookings.html', {
        'bookings': pending_bookings,
        'approved_history': approved_bookings
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
        Re_status='approved',
        speaker_assignment__isnull=True
    ).order_by('Re_date')

    speakers = Speaker.objects.all()

    if request.method == 'POST':
        booking_id = request.POST.get('booking_id')
        speaker_id = request.POST.get('speaker_id')

        booking = get_object_or_404(Booking, id=booking_id)
        speaker = get_object_or_404(Speaker, id=speaker_id)

        # จำกัด 1 งานต่อวิทยากรต่อวัน: ถ้าวิทยากรมีงานในวันเดียวกันให้แจ้งเตือน
        if booking.Re_date:
            conflict = SpeakerAssignment.objects.filter(
                speaker=speaker,
                booking__Re_date=booking.Re_date,
                status__in=['pending', 'assigned', 'accepted', 'confirmed']
            ).exists()
            if conflict:
                messages.warning(request, f'ไม่สามารถมอบหมาย: วิทยากร {speaker.name} มีงานเต็มในวันที่ {booking.Re_date.strftime("%d %b %Y")}')
                return redirect('manage_speakers')

        SpeakerAssignment.objects.create(
            booking=booking,
            speaker=speaker,
            status='assigned'
        )

        messages.success(
            request,
            f'มอบหมายคุณ {speaker.name} ดูแลการจองของ {booking.fullname} เรียบร้อยแล้ว'
        )
        return redirect('manage_speakers')

    return render(request, 'admin_panel/speakers/manage_speakers.html', {
        'pending_assignments': pending_assignments,
        'speakers': speakers,
        'title': 'จัดการวิทยากร'
    })

@login_required
@user_passes_test(is_staff_or_admin)
def speaker_assign_from_booking_view(request, booking_id):
    """
    มอบหมายวิทยากรจากหน้า Booking โดยตรง
    """
    booking = get_object_or_404(Booking, id=booking_id)
    speakers = Speaker.objects.all()

    if request.method == 'POST':
        # --- จุดที่แก้ไข 1: เปลี่ยนจาก 'speaker_id' เป็น 'speaker' ให้ตรงกับ name ใน HTML ---
        speaker_id = request.POST.get('speaker') 
        
        # ดึง Object วิทยากร
        speaker = get_object_or_404(Speaker, id=speaker_id)

        # รับค่าเพิ่มเติมจากฟอร์ม (ถ้ามี)
        title = request.POST.get('title')
        quantity = request.POST.get('quantity', '1 ท่าน')
        schedule_text = request.POST.get('schedule_text', '')
        note = request.POST.get('note', '')

        try:
            with transaction.atomic():
                # จำกัด 1 งานต่อวิทยากรต่อวัน: ถ้าวิทยากรมีงานในวันเดียวกันให้แจ้งเตือน
                if booking.Re_date:
                    conflict = SpeakerAssignment.objects.filter(
                        speaker=speaker,
                        booking__Re_date=booking.Re_date,
                        status__in=['pending', 'assigned', 'accepted', 'confirmed']
                    ).exists()
                    if conflict:
                        messages.warning(request, f'ไม่สามารถมอบหมาย: วิทยากร {speaker.name} มีงานเต็มในวันที่ {booking.Re_date.strftime("%d %b %Y")}')
                        return redirect('speaker_assign_from_booking', booking_id=booking.id)

                # --- จุดที่แก้ไข 2: ปรับให้ตรงกับ Model SpeakerAssignment ล่าสุด ---
                assignment, created = SpeakerAssignment.objects.update_or_create(
                    booking=booking,
                    defaults={
                        'speaker': speaker,
                        'status': 'assigned',
                        'title': title or f"วิทยากรสำหรับคณะคุณ {booking.fullname}",
                        'quantity': quantity,
                        'schedule_text': schedule_text,
                        'note': note,
                    }
                )

                # อัปเดตสถานะการจอง (ถ้าต้องการ)
                booking.Re_status = 'approved' # หรือ 'confirmed' ตามที่คุณตั้งค่าไว้
                booking.save()

                messages.success(
                    request, 
                    f'มอบหมายงานให้คุณ {speaker.name} เรียบร้อยแล้ว (รหัส: {assignment.assignment_id})'
                )
                # เช็คชื่อ URL ใน redirect ให้ตรงกับ urls.py ของคุณ (เช่น 'approve_bookings')
                return redirect('approve_bookings')

        except Exception as e:
            messages.error(request, f'เกิดข้อผิดพลาด: {e}')

    return render(request, 'admin_panel/booking/speaker_assign_from_booking.html', {
        'booking': booking,
        'speakers': speakers
    })


@login_required
@user_passes_test(is_staff_or_admin)
def speaker_assign_form_view(request, speaker_id):
    """
    ฟอร์มมอบหมายงานจากฝั่ง Speaker
    """
    speaker = get_object_or_404(Speaker, id=speaker_id)
    booking_id = request.GET.get('booking_id')
    booking = Booking.objects.filter(pk=booking_id).first() if booking_id else None

    if request.method == 'POST':
        form = SpeakerAssignFromBookingForm(request.POST)
        if form.is_valid():
            assign = form.save(commit=False)
            assign.speaker = speaker

            selected_booking = form.cleaned_data.get('booking') or booking
            if selected_booking:
                assign.booking = selected_booking
                if not assign.title:
                    assign.title = f"นำชม (Booking #{selected_booking.id})"

            assign.assigned_by = request.user
            assign.save()

            messages.success(request, 'มอบหมายงานสำเร็จ')
            return redirect(
                'speaker_assign_confirm',
                assignment_id=assign.id
            )
    else:
        form = SpeakerAssignFromBookingForm(
            initial={'booking': booking}
        )

    return render(request, "museum/speaker/speaker_assign_form.html", {
        "form": form,
        "speaker": speaker,
        "booking": booking
    })


@login_required
def speaker_assign_confirm_view(request, assignment_id):
    """
    หน้ายืนยันผลการมอบหมาย + ประวัติวิทยากร
    """
    assign = get_object_or_404(SpeakerAssignment, id=assignment_id)
    history = assign.speaker.assignments.all().order_by('-assigned_at')

    return render(request, "museum/speaker/speaker_assign_confirm.html", {
        "assignment": assign,
        "history": history
    })

@login_required
def speaker_assignment_detail_view(request, assignment_id):
    # ดึงข้อมูลงาน ถ้าไม่เจอส่ง 404
    assignment = get_object_or_404(SpeakerAssignment, id=assignment_id)
    
    # ตรวจสอบสิทธิ์ (ป้องกันวิทยากรแอบดูงานของคนอื่น)
    if not request.user.is_staff and assignment.speaker.user != request.user:
        messages.error(request, "คุณไม่มีสิทธิ์เข้าถึงข้อมูลงานนี้")
        return redirect('speaker_dashboard')

    return render(request, 'main/assignment_detail.html', {
        'assignment': assignment,
        'booking': assignment.booking  # ส่ง booking ไปด้วยตามที่ template ต้องการ
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

@login_required
@user_passes_test(is_admin)
def admin_edit_museum_view(request):
    museum = MuseumProfile.objects.first()

    if request.method == 'POST':
        form = MuseumProfileForm(
            request.POST,
            request.FILES,
            instance=museum
        )

        if form.is_valid():
            form.save()
            messages.success(
                request,
                "บันทึกข้อมูลพิพิธภัณฑ์เรียบร้อยแล้ว"
            )
            # ใช้ชื่อ URL ให้ตรงกับ main/urls.py และ templates
            return redirect('admin_editmuseum')
        else:
            messages.error(
                request,
                "ข้อมูลไม่ถูกต้อง กรุณาตรวจสอบอีกครั้ง"
            )
    else:
        form = MuseumProfileForm(instance=museum)

    return render(request, 'admin_panel/museum/admin_editmuseum.html', {
        'form': form,
        'museum': museum
    })


# =====================================================================
# SILK PATTERN MANAGEMENT
# =====================================================================

@login_required
@user_passes_test(is_staff_or_admin)
def manage_silk_patterns_view(request):
    """หน้ารายการลายผ้าไหม"""
    patterns = SilkPattern.objects.all().order_by('target_index')
    return render(request, 'admin_panel/Silk/manage_silk.html', {
        'patterns': patterns
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
# SILK PATTERN : CREATE / REGISTER
# =====================================================================

@login_required
def silk_register_view(request):
    """
    หน้าลงทะเบียนลายผ้าไหม
    (User / Staff ใช้งานได้ตามสิทธิ์)
    """
    next_index = (
        SilkPattern.objects.aggregate(
            m=Max('target_index')
        )['m'] or -1
    ) + 1

    if request.method == 'POST':
        form = SilkPatternForm(
            request.POST,
            request.FILES
        )
        if form.is_valid():
            try:
                form.save()
                messages.success(
                    request,
                    'บันทึกข้อมูลผ้าไหมสำเร็จ'
                )
                return redirect('silk_register')
            except Exception as e:
                messages.error(
                    request,
                    f'บันทึกไม่สำเร็จ: {e}'
                )
        else:
            messages.error(
                request,
                'ตรวจสอบฟอร์มอีกครั้ง'
            )
    else:
        form = SilkPatternForm(
            initial={'target_index': next_index}
        )

    items = SilkPattern.objects.all()

    return render(
        request,
        'museum/silk/silk_register.html',
        {
            'form': form,
            'items': items,
            'targets_mind_url': (
                settings.STATIC_URL +
                'museum/ar/targets.mind'
            ),
        }
    )


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
# SILK PATTERN : RATING
# =====================================================================

def silk_pattern_rating_view(request, pk):
    """
    ดูรายการเรตติ้งของลายผ้าไหม
    """
    silk = (
        SilkPattern.objects
        .filter(target_index=pk)
        .first()
        or SilkPattern.objects
        .filter(pk=pk)
        .first()
    )

    if not silk:
        raise Http404

    ratings = (
        SilkPatternRating.objects
        .filter(silk=silk)
        .order_by('-created_at')[:50]
    )

    return render(
        request,
        "museum/silk/silk_pattern_rating.html",
        {
            "silk": silk,
            "ratings": ratings
        }
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

def silk_ar_scan_view(request):
    """หน้า AR Scan (MindAR)"""
    silk_list = []
    for s in SilkPattern.objects.order_by('target_index'):
        silk_list.append({
            "pk": s.pk,
            "target_index": s.target_index,
            "Si_ID": s.Si_ID,
            "name": s.Si_name,
            "address": s.Si_address,
            "type": s.Si_type,
            "color": s.Si_color,
            "history": s.Si_history,
            "image_url": request.build_absolute_uri(s.reference.url) if s.reference else "",
            "model_url": request.build_absolute_uri(s.model_3d.url) if s.model_3d else "",
            "detail_url": request.build_absolute_uri(reverse('silk_detail', args=[s.pk]))
        })

    return render(request, "museum/silk/silk_ar_scan.html", {
        "silk_json": json.dumps(silk_list, ensure_ascii=False)
    })


def silk_ar_view(request, pk):
    """หน้า AR สำหรับผ้าไหมแต่ละรายการ (single item)
    แสดงโมเดล 3D ผ่าน model-viewer และ overlay ข้อมูลที่มา
    """
    s = get_object_or_404(SilkPattern, pk=pk)
    context = {
        'silk': s,
        'model_url': request.build_absolute_uri(s.model_3d.url) if s.model_3d else '',
        'image_url': request.build_absolute_uri(s.reference.url) if s.reference else '',
    }
    return render(request, 'museum/silk/silk_ar_detail.html', context)


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
    
    if booking.Re_status != 'approved':
        messages.warning(request, "ต้องได้รับการอนุมัติก่อนจึงจะให้คะแนนได้")
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
def speaker_home(request):
    """หน้าหลักวิทยากร (Public)"""
    return render(request, 'speaker/speaker_base.html')

def speaker_list_view(request):
    speakers = Speaker.objects.select_related("user").order_by("name")
    return render(request, "speaker/list.html", {"speakers": speakers})

def speaker_detail_view(request, speaker_id):
    speaker = get_object_or_404(Speaker, id=speaker_id)
    # ตารางงาน (เฉพาะที่ Complete แล้วหรือ Public)
    assignments = SpeakerSchedule.objects.filter(speaker=speaker) 
    return render(request, "speaker/detail.html", {
        "speaker": speaker, "assignments": assignments
    })

def speaker_schedule_view(request):
    qs = SpeakerAssignment.objects.select_related("speaker").filter(status='accepted').order_by("assigned_at")
    return render(request, "speaker/speaker_schedule.html", {"assignments": qs})


# --- Speaker Portal (สำหรับคนที่เป็นวิทยากร) ---
@login_required
@user_passes_test(is_speaker)
def speaker_dashboard(request):
    try:
        speaker = Speaker.objects.get(user=request.user)
    except Speaker.DoesNotExist:
        # กรณีเป็น Staff แต่อาจไม่มี Record Speaker
        messages.warning(request, "คุณไม่มีโปรไฟล์วิทยากร")
        return redirect('home')

    # แยกงานตามสถานะเพื่อแสดงแยกในแดชบอร์ด
    assignments = SpeakerAssignment.objects.filter(speaker=speaker).order_by('-assigned_at')
    # Treat 'assigned' (set by admin) as pending from speaker's perspective
    pending_assignments = assignments.filter(status__in=['pending', 'assigned'])
    accepted_assignments = assignments.filter(status__in=['accepted', 'confirmed'])
    completed_assignments = assignments.filter(status='completed')

    return render(request, 'speaker/dashboard.html', {
        'speaker': speaker,
        'assignments': assignments,
        'pending_assignments': pending_assignments,
        'accepted_assignments': accepted_assignments,
        'completed_assignments': completed_assignments,
    })

@login_required
@user_passes_test(is_speaker)
def speaker_assignment_list(request):
    speaker = get_object_or_404(Speaker, user=request.user)
    status = request.GET.get('status')
    assignments = SpeakerAssignment.objects.filter(speaker=speaker)
    if status:
        assignments = assignments.filter(status=status)
    return render(request, 'speaker/speaker_assign.html', {
        'assignments': assignments, 'current_status': status, 'speaker': speaker,
    })


@login_required
@user_passes_test(is_speaker)
def speaker_assignment_detail(request, assignment_id):
    # ลองหาแบบไม่เช็ค user ดูก่อน
    assignment = get_object_or_404(SpeakerAssignment, assignment_id=assignment_id)
    
    # ตรวจสอบว่าใครเป็นเจ้าของงานนี้ (พิมพ์ออกมาดูที่ Terminal)
    if assignment.speaker and assignment.speaker.user:
        print(f"Owner is: {assignment.speaker.user.username}")
        print(f"Current User is: {request.user.username}")
    else:
        print("This assignment has no user linked to the speaker!")

    # ถ้าเจ้าของไม่ตรงกัน แต่อยากให้เข้าดูได้แค่เจ้าของ ให้เช็คแบบนี้แทน
    if assignment.speaker.user != request.user:
        raise Http404("You do not have permission to view this assignment.")

    booking = getattr(assignment, 'booking', None)
    return render(request, 'speaker/assignment_detail.html', {
        'assignment': assignment,
        'booking': booking,
    })

@login_required
@user_passes_test(is_speaker)
def accept_assignment(request, assignment_id):
    """Allow the assigned speaker to accept a pending assignment.

    Supports lookup by numeric PK or by string `assignment_id`.
    Only the speaker who owns the assignment may accept it.
    """
    # Try numeric PK first, restricting to assignments belonging to this user
    try:
        assignment = SpeakerAssignment.objects.get(pk=assignment_id, speaker__user=request.user)
    except (SpeakerAssignment.DoesNotExist, ValueError):
        assignment = get_object_or_404(SpeakerAssignment, assignment_id=assignment_id, speaker__user=request.user)

    # Only allow accepting when currently pending/assigned
    if assignment.status not in ('pending', 'assigned'):
        messages.warning(request, 'ไม่สามารถรับงานได้ เนื่องจากสถานะไม่ใช่รอดำเนินการ')
        redirect_id = getattr(assignment, 'assignment_id', None) or assignment.id
        return redirect('speaker_assignment_detail', assignment_id=redirect_id)

    assignment.status = 'accepted'
    assignment.save()
    messages.success(request, "รับงานเรียบร้อยแล้ว")

    redirect_id = getattr(assignment, 'assignment_id', None) or assignment.id
    return redirect('speaker_assignment_detail', assignment_id=redirect_id)

@login_required
@user_passes_test(is_speaker)
def complete_assignment(request, assignment_id):
    """Mark an assignment complete — only by its assigned speaker and only
    when it has previously been accepted.
    """
    try:
        assignment = SpeakerAssignment.objects.get(pk=assignment_id, speaker__user=request.user)
    except (SpeakerAssignment.DoesNotExist, ValueError):
        assignment = get_object_or_404(SpeakerAssignment, assignment_id=assignment_id, speaker__user=request.user)

    # Only allow completion if assignment was accepted/confirmed already
    if assignment.status not in ('accepted', 'confirmed'):
        messages.warning(request, 'ไม่สามารถปิดงานได้ ต้องรับงานก่อนจึงจะปิดงานได้')
        redirect_id = getattr(assignment, 'assignment_id', None) or assignment.id
        return redirect('speaker_assignment_detail', assignment_id=redirect_id)

    assignment.status = 'completed'
    assignment.save()
    messages.success(request, 'ปิดงานเรียบร้อย')
    return redirect('speaker_dashboard')

# =====================================================================
# ส่วนที่ 8 หมวดหมู่ระบบวิทยากร
# =====================================================================






# =====================================================================
# ส่วนที่ 9 หมวดหมู่ระบบแอดมินแดชบอร์ด (CLEAN VERSION)
# =====================================================================
# ---------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------
@login_required
@user_passes_test(is_staff_or_admin)
def admin_dashboard_view(request):
    """หน้า Dashboard แอดมิน"""

    today = timezone.now().date()

    unassigned_bookings = Booking.objects.filter(
        Re_status='approved',
        speaker_assignment__isnull=True
    ).count()

    context = {
        'total_users': User.objects.count(),

        'pending_count': Booking.objects.filter(
            Q(Re_status='pending') | Q(Re_status__isnull=True) | Q(Re_status='')
        ).count(),

        'today_bookings_count': Booking.objects.filter(Re_date=today).count(),
        'unassigned_count': unassigned_bookings,

        'total_bookings': Booking.objects.count(),
        'total_patterns': SilkPattern.objects.count(),
        'active_speakers': Speaker.objects.count(),

        'recent_bookings': Booking.objects.order_by('-created_at')[:5],
        'today': timezone.now(),
    }

    return render(request, 'admin_panel/admin_home.html', context)


# ---------------------------------------------------------------------
# Booking Approval
# ---------------------------------------------------------------------
@login_required
@user_passes_test(is_staff_or_admin)
def update_booking_status(request, booking_id, status):
    booking = get_object_or_404(Booking, pk=booking_id)

    if status == 'approved':
        booking.Re_status = 'approved'
        SpeakerAssignment.objects.filter(
            booking=booking
        ).update(status='confirmed')
        messages.success(request, f'อนุมัติ #{booking.id} และยืนยันวิทยากรแล้ว')

    elif status == 'rejected':
        booking.Re_status = 'rejected'
        SpeakerAssignment.objects.filter(
            booking=booking
        ).update(status='cancelled')
        messages.warning(request, f'ปฏิเสธ #{booking.id} แล้ว')

    booking.decided_by = request.user
    booking.decided_at = timezone.now()
    booking.save()

    return redirect('approve_bookings')


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
                user.delete()
                messages.success(request, 'ลบผู้ใช้เรียบร้อยแล้ว')
            else:
                messages.error(request, 'ไม่สามารถลบผู้ใช้นี้ได้')
            return redirect('manage_users')

        username = request.POST.get('username')
        email = request.POST.get('email')
        password = request.POST.get('password')
        first_name = request.POST.get('first_name', '').strip()
        last_name = request.POST.get('last_name', '').strip()
        role = request.POST.get('role', 'member')

        if User.objects.filter(username=username).exists():
            messages.error(request, 'ชื่อผู้ใช้นี้มีอยู่แล้ว')
        else:
            with transaction.atomic():
                user = User.objects.create_user(username=username, email=email, password=password)
                user.first_name = first_name
                user.last_name = last_name
                user.is_staff = (role == 'admin')
                user.is_superuser = (role == 'admin')
                user.save()

                profile, _ = Profile.objects.get_or_create(user=user)
                profile.full_name = f"{first_name} {last_name}"
                profile.role = role
                profile.save()

                if role == 'speaker':
                    Speaker.objects.get_or_create(user=user, defaults={'name': profile.full_name})

            messages.success(request, f'เพิ่มผู้ใช้ {username} เรียบร้อยแล้ว')

        return redirect('manage_users')

    users = User.objects.select_related('profile').order_by('-date_joined')
    return render(request, 'admin_panel/Users/admin_users.html', {
        'users': users,
        'member_count': users.count(),
        'staff_count': users.filter(is_staff=True).count(),
        'speaker_count': Speaker.objects.count()
    })


@login_required
@user_passes_test(is_staff_or_admin)
def manage_users_edit_view(request, user_id):
    user = get_object_or_404(User, id=user_id)
    profile, _ = Profile.objects.get_or_create(user=user)

    if request.method == 'POST':
        user.first_name = request.POST.get('first_name', '')
        user.last_name = request.POST.get('last_name', '')
        user.email = request.POST.get('email', '')
        user.is_active = request.POST.get('is_active') == 'on'

        role = request.POST.get('role', 'member')
        user.is_staff = (role == 'admin')
        user.is_superuser = (role == 'admin')
        user.save()

        profile.phone = request.POST.get('phone', '')
        profile.role = role
        if 'image' in request.FILES:
            profile.image = request.FILES['image']
        profile.save()

        if role == 'speaker' and not Speaker.objects.filter(user=user).exists():
            Speaker.objects.create(user=user, name=user.get_full_name())

        messages.success(request, 'บันทึกข้อมูลเรียบร้อยแล้ว')
        return redirect('manage_users')

    return render(request, 'admin_panel/Users/admin_edituser.html', {
        'target_user': user,
        'profile': profile
    })


@login_required
@user_passes_test(is_staff_or_admin)
def manage_users_delete_view(request, user_id):
    user = get_object_or_404(User, id=user_id)
    if user == request.user:
        messages.error(request, 'ไม่สามารถลบบัญชีของตัวเองได้')
    else:
        user.delete()
        messages.success(request, 'ลบผู้ใช้งานเรียบร้อยแล้ว')
    return redirect('manage_users')


# ---------------------------------------------------------------------
# Silk Pattern Management
# ---------------------------------------------------------------------
@login_required
@user_passes_test(is_staff_or_admin)
def manage_silk_patterns_add_view(request):
    form = SilkPatternForm(request.POST or None, request.FILES or None)
    if request.method == 'POST' and form.is_valid():
        form.save()
        messages.success(request, 'เพิ่มลายผ้าไหมเรียบร้อยแล้ว')
        return redirect('manage_silk_patterns')

    return render(request, 'admin_panel/Silk/admin_editsilk.html', {
        'form': form,
        'title': 'เพิ่มลายผ้าใหม่'
    })


@login_required
@user_passes_test(is_staff_or_admin)
def manage_silk_edit_view(request, pattern_id):
    pattern = get_object_or_404(SilkPattern, id=pattern_id)
    form = SilkPatternForm(request.POST or None, request.FILES or None, instance=pattern)

    if request.method == 'POST' and form.is_valid():
        form.save()
        messages.success(request, 'แก้ไขข้อมูลเรียบร้อยแล้ว')
        return redirect('manage_silk_patterns')

    return render(request, 'admin_panel/Silk/admin_editsilk.html', {
        'form': form,
        'title': f'แก้ไขลายผ้า: {pattern.Si_name}'
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
def manage_assignments_view(request):
    pending_assignments = Booking.objects.filter(
        Re_status='approved',
        speaker_assignment__isnull=True
    ).order_by('Re_date')

    return render(request, 'museum/admin/manage_speakers.html', {
        'pending_assignments': pending_assignments,
        'speakers': Speaker.objects.all(),
    })

@login_required
@user_passes_test(lambda u: u.is_staff)
def admin_edit_events_view(request):
    """
    หน้า Admin สำหรับจัดการกิจกรรม / workshop
    """
    workshops = Workshop.objects.all().order_by("-id")

    return render(
        request,
        "admin_panel/Evens/admin_events_list.html",
        {
            "workshops": workshops,
        }
    )

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
    question.delete()
    messages.success(request, 'ลบคำถามเรียบร้อยแล้ว')
    return redirect('manage_questions')

def speaker_edit_view(request, speaker_id):
    # ดึงข้อมูลวิทยากร หรือส่งกลับหน้า 404 ถ้าไม่พบ
    speaker = get_object_or_404(Speaker, id=speaker_id)
    
    # ตรวจสอบสิทธิ์ (ป้องกันไม่ให้วิทยากรคนอื่นมาแก้ข้อมูลกันเอง)
    if request.user.speaker.id != speaker.id:
        return redirect('speaker_dashboard')

    if request.method == 'POST':
        # ตรงนี้ต้องใช้ Form สำหรับแก้ไขข้อมูล (ถ้ามี SpeakerForm)
        # ตัวอย่างการอัปเดตแบบง่าย:
        speaker.name = request.POST.get('name')
        speaker.expertise = request.POST.get('expertise')
        if 'profile_picture' in request.FILES:
            speaker.profile_picture = request.FILES['profile_picture']
        speaker.save()
        return redirect('speaker_dashboard')

    return render(request, 'speaker/speaker_edit.html', {'speaker': speaker})
# ---------------------------------------------------------------------
# Events (Workshop) Management - CRUD
# ---------------------------------------------------------------------

@login_required
@user_passes_test(is_staff_or_admin)
def admin_events_list_view(request):
    """1. หน้าแสดงรายการกิจกรรมทั้งหมด (Read)"""
    workshops = Workshop.objects.all().order_by("-id")
    return render(request, "admin_panel/Evens/admin_events_list.html", {
        "workshops": workshops,
    })

# คัดลอกไปวางทับฟังก์ชันเดิมใน views.py

@login_required
@user_passes_test(is_staff_or_admin)
def admin_events_add_view(request):
    if request.method == "POST":
        workshop = Workshop()
        workshop.title = request.POST.get('title')
        workshop.description = request.POST.get('description')
        workshop.location = request.POST.get('location')
        workshop.duration = request.POST.get('duration')
        
        # จัดการตัวเลขและวันที่
        try:
            workshop.max_participants = int(request.POST.get('max_participants', 20))
        except:
            workshop.max_participants = 20
            
        workshop.start_date = request.POST.get('start_date') or None
        workshop.end_date = request.POST.get('end_date') or None
        workshop.start_time = request.POST.get('start_time') or None
        workshop.end_time = request.POST.get('end_time') or None
        workshop.is_active = 'is_active' in request.POST
        workshop.inactive_reason = request.POST.get('inactive_reason', '')

        # บันทึกรูปภาพ
        if 'image' in request.FILES:
            workshop.image = request.FILES['image']
        
        workshop.save()
        messages.success(request, "เพิ่มกิจกรรมเรียบร้อยแล้ว")
        return redirect("admin_events_list")
    
    return render(request, "admin_panel/Evens/admin_events_form.html", {"title": "เพิ่มกิจกรรมใหม่"})

# ส่วนการดึงข้อมูลไปแสดง (Logic สำคัญที่ทำให้ขึ้นทั้งเดือน)
def workshop_list_view(request):
    # รับวันที่ที่ต้องการดูจาก URL หรือ Default เป็นวันนี้
    target_date = request.GET.get('date', timezone.now().date())
    
    # แก้จาก Workshop.objects.filter(start_date=target_date) เป็นด้านล่างนี้:
    workshops = Workshop.objects.filter(
        start_date__lte=target_date, # เริ่มก่อนหรือตรงกับวันที่เลือก
        end_date__gte=target_date    # จบหลังหรือตรงกับวันที่เลือก
    )
    return render(request, 'your_template.html', {'workshops': workshops})

@login_required
@user_passes_test(is_staff_or_admin)
def admin_events_edit_view(request, workshop_id):
    """3. หน้าแก้ไขกิจกรรม (Update)"""
    workshop = get_object_or_404(Workshop, id=workshop_id)
    if request.method == "POST":
        form = WorkshopForm(request.POST, request.FILES, instance=workshop)
        if form.is_valid():
            form.save()
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
    workshop.delete()
    messages.success(request, 'ลบกิจกรรมเรียบร้อยแล้ว')
    return redirect('admin_events_list')

@login_required
@user_passes_test(is_staff_or_admin)
def manage_speakers_add_view(request):
    """แอดมินเพิ่มวิทยากรคนใหม่"""
    if request.method == 'POST':
        # สมมติว่ามีการเลือก User มาผูกกับ Speaker
        user_id = request.POST.get('user_id')
        name = request.POST.get('name')
        bio = request.POST.get('bio')
        
        user = get_object_or_404(User, id=user_id)
        Speaker.objects.create(user=user, name=name, bio=bio)
        
        messages.success(request, 'เพิ่มวิทยากรเรียบร้อยแล้ว')
        return redirect('manage_speakers')
    
    # ดึง User ที่ยังไม่เป็น Speaker มาให้เลือก
    available_users = User.objects.exclude(speaker__isnull=False)
    return render(request, 'admin_panel/speakers/admin_speaker_form.html', {
        'available_users': available_users,
        'title': 'เพิ่มวิทยากร'
    })

@login_required
@user_passes_test(is_staff_or_admin)
def manage_speakers_edit_view(request, speaker_id):
    """แอดมินแก้ไขข้อมูลวิทยากร"""
    speaker = get_object_or_404(Speaker, id=speaker_id)
    if request.method == 'POST':
        speaker.name = request.POST.get('name')
        speaker.bio = request.POST.get('bio')
        if 'image' in request.FILES:
            speaker.image = request.FILES['image']
        speaker.save()
        messages.success(request, 'แก้ไขข้อมูลวิทยากรเรียบรšíอยแล้ว')
        return redirect('manage_speakers')

    return render(request, 'admin_panel/speakers/admin_speaker_form.html', {
        'speaker': speaker,
        'title': f'แก้ไขวิทยากร: {speaker.name}'
    })

@login_required
@user_passes_test(is_staff_or_admin)
def manage_speakers_delete_view(request, speaker_id):
    """แอดมินลบวิทยากร"""
    speaker = get_object_or_404(Speaker, id=speaker_id)
    speaker.delete()
    messages.success(request, 'ลบวิทยากรเรียบร้อยแล้ว')
    return redirect('manage_speakers')

@login_required
@user_passes_test(is_staff_or_admin)
def admin_delete_booking_view(request, booking_id):
    """แอดมินลบรายการจอง"""
    booking = get_object_or_404(Booking, id=booking_id)
    booking.delete()
    messages.success(request, 'ลบรายการจองเรียบร้อยแล้ว')
    return redirect('approve_bookings')

def ar_test_view(request):
    # ดึงเฉพาะรายการที่มีไฟล์โมเดล (เก่า หรือ silk/mannequin) และมีการตั้งค่า target_index ไว้
    patterns = SilkPattern.objects.exclude(target_index__isnull=True).filter(
        Q(model_3d__isnull=False) |
        Q(silk_model_3d__isnull=False) |
        Q(mannequin_model_3d__isnull=False)
    ).order_by('target_index')

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
    try:
        if mind_param:
            candidate = os.path.join(static_targets_dir, mind_param)
            if os.path.exists(candidate):
                chosen_target = mind_param
                target_file_url = request.build_absolute_uri(settings.STATIC_URL + f'main/targets/{chosen_target}')

        if not target_file_url:
            # [UPDATED] Prioritize 'targets.mind' (combined file) first!
            combined_path = os.path.join(static_targets_dir, 'targets.mind')
            if os.path.exists(combined_path):
                 chosen_target = 'targets.mind'
                 target_file_url = request.build_absolute_uri(settings.STATIC_URL + 'main/targets/targets.mind')
            else:
                 # If no combined file, look for numbered files (targetsX.mind)
                 files = glob.glob(os.path.join(static_targets_dir, 'targets*.mind'))
                 if files:
                    def extract_num(path):
                        m = re.search(r'targets(\d+)\.mind$', path)
                        return int(m.group(1)) if m else -1

                    files_sorted = sorted(files, key=lambda p: (extract_num(p), os.path.getmtime(p)), reverse=True)
                    chosen_target = os.path.basename(files_sorted[0])
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
        # model เดิม (ถ้ามี) ใช้เป็น fallback ของ silk_model
        base_model_url = request.build_absolute_uri(p.model_3d.url) if getattr(p, 'model_3d', None) else ''
        silk_model_url = request.build_absolute_uri(p.silk_model_3d.url) if getattr(p, 'silk_model_3d', None) else base_model_url
        mannequin_model_url = request.build_absolute_uri(p.mannequin_model_3d.url) if getattr(p, 'mannequin_model_3d', None) else ''
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
            # สรุปสั้นใต้ชื่อ: ใช้ประเภท/สีผ้า ไม่ดึงประวัติยาวเพื่อเลี่ยงข้อมูลซ้ำ
            'detail': p.Si_type or p.Si_color or "ผ้าไหมไทยลวดลายเอกลักษณ์",
            'transform': transform_val,
            'target_file': p.target_file or '',
            'image_url': request.build_absolute_uri(p.reference.url) if getattr(p, 'reference', None) else ''
        })

    # แปลงข้อมูลเป็น JSON เพื่อให้ JavaScript นำไปใช้ต่อได้ง่าย
    patterns_json = json.dumps(patterns_list, cls=DjangoJSONEncoder)

    context = {
        'patterns_json': patterns_json,
        'target_file_url': target_file_url,
    }
    return render(request, 'main/ar_view.html', context)
# =====================================================================
# ส่วนที่ 9 หมวดหมู่ระบบแอดมินแดชบอร์ด (CLEAN VERSION)
# =====================================================================