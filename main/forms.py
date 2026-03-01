from django import forms
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.forms.widgets import ClearableFileInput

# =========================================================
# Custom Widget: Hide "Currently: <path>" for file fields
# =========================================================
class HideCurrentFileInput(ClearableFileInput):
    """
    ปิดการแสดงผล "Currently: main/...." (path) ที่ Django ชอบโชว์ใต้ input file
    โดยใช้ template widget ของเราเอง
    """
    template_name = "widgets/hide_current_file_input.html"


# =========================================================
# IMPORT MODELS
# =========================================================
from .models import (
    Profile, Speaker,
    Booking, WorkshopBooking, Workshop, Reservation,
    SilkPattern, SilkPatternRating,
    SpeakerAssignment,
    MuseumProfile,
    Question,
    SurveyRating,
)

# =========================================================
# 1) AUTH & USER FORMS
# =========================================================
class SignUpForm(forms.ModelForm):
    def clean_username(self):
        username = self.cleaned_data.get('username')
        if username and User.objects.filter(username=username).exists():
            raise ValidationError("ชื่อผู้ใช้นี้ถูกใช้แล้ว กรุณาเลือกชื่อใหม่")
        return username
    # 1. เพิ่มช่องกรอกเบอร์โทรศัพท์
    phone = forms.CharField(
        label="เบอร์โทรศัพท์",
        max_length=20,
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': '0xx-xxx-xxxx'})
    )

    password1 = forms.CharField(
        label="รหัสผ่าน",
        widget=forms.PasswordInput(attrs={'class': 'form-control'})
    )
    confirm_password = forms.CharField(
        label="ยืนยันรหัสผ่าน",
        widget=forms.PasswordInput(attrs={'class': 'form-control'})
    )

    class Meta:
        model = User
        fields = ['username', 'email', 'first_name', 'last_name']
        widgets = {
            'username': forms.TextInput(attrs={'class': 'form-control'}),
            'email': forms.EmailInput(attrs={'class': 'form-control'}),
            'first_name': forms.TextInput(attrs={'class': 'form-control'}),
            'last_name': forms.TextInput(attrs={'class': 'form-control'}),
        }

    def clean(self):
        cleaned_data = super().clean()
        if cleaned_data.get("password1") != cleaned_data.get("confirm_password"):
            raise ValidationError("รหัสผ่านไม่ตรงกัน")
        return cleaned_data

    def save(self, commit=True):
        # 1. สร้าง User ตามปกติ
        user = super().save(commit=False)
        user.set_password(self.cleaned_data["password1"])

        if commit:
            user.save()

            # 2. บันทึกเบอร์โทรลง Profile (ต้องทำหลังจาก user.save())
            # ตรวจสอบว่ามี profile หรือไม่ (ปกติจะมีจาก signals.py)
            if hasattr(user, 'profile'):
                profile = user.profile
                profile.phone = self.cleaned_data['phone']
                profile.save()

        return user


class LoginForm(forms.Form):
    username = forms.CharField(
        label="ชื่อผู้ใช้",
        widget=forms.TextInput(attrs={'class': 'form-control'})
    )
    password = forms.CharField(
        label="รหัสผ่าน",
        widget=forms.PasswordInput(attrs={'class': 'form-control'})
    )


class ForgotPasswordForm(forms.Form):
    email = forms.EmailField(
        label="อีเมล",
        widget=forms.EmailInput(attrs={'class': 'form-control'})
    )


class SetNewPasswordForm(forms.Form):
    new_password = forms.CharField(
        label="รหัสผ่านใหม่",
        widget=forms.PasswordInput(attrs={'class': 'form-control'})
    )
    confirm_password = forms.CharField(
        label="ยืนยันรหัสผ่านใหม่",
        widget=forms.PasswordInput(attrs={'class': 'form-control'})
    )

    def clean(self):
        cleaned_data = super().clean()
        if cleaned_data.get("new_password") != cleaned_data.get("confirm_password"):
            raise ValidationError("รหัสผ่านไม่ตรงกัน")
        return cleaned_data


class UserForm(forms.ModelForm):
    password = forms.CharField(widget=forms.PasswordInput, required=False)

    class Meta:
        model = User
        fields = ['username', 'email', 'first_name', 'last_name', 'password']

    def save(self, commit=True):
        user = super().save(commit=False)
        if self.cleaned_data.get('password'):
            user.set_password(self.cleaned_data['password'])
        if commit:
            user.save()
        return user


class UserEditForm(forms.ModelForm):
    email = forms.EmailField(label='อีเมล', widget=forms.EmailInput(attrs={'class': 'form-control'}))
    first_name = forms.CharField(label='ชื่อจริง', widget=forms.TextInput(attrs={'class': 'form-control'}))
    last_name = forms.CharField(label='นามสกุล', widget=forms.TextInput(attrs={'class': 'form-control'}))

    class Meta:
        model = User
        fields = ['first_name', 'last_name', 'email']


class UserRoleEditForm(forms.ModelForm):
    role = forms.ChoiceField(
        choices=[('member', 'Member'), ('staff', 'Staff'), ('speaker', 'Speaker')],
        label="สิทธิ์การใช้งาน",
        required=False,
        widget=forms.Select(attrs={'class': 'form-select'})
    )

    class Meta:
        model = User
        fields = ['username', 'email', 'first_name', 'last_name', 'is_active']
        widgets = {
            'username': forms.TextInput(attrs={'class': 'form-control', 'readonly': True}),
            'email': forms.EmailInput(attrs={'class': 'form-control'}),
            'first_name': forms.TextInput(attrs={'class': 'form-control'}),
            'last_name': forms.TextInput(attrs={'class': 'form-control'}),
        }

# =========================================================
# 2) BOOKING & WORKSHOP FORMS
# =========================================================
class BookingForm(forms.ModelForm):
    class Meta:
        model = Booking
        fields = ['Re_date', 'Re_quantity', 'workshop', 'fullname', 'email', 'phone']
        widgets = {
            'Re_date': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
            'Re_quantity': forms.TextInput(attrs={'class': 'form-control'}),
            'workshop': forms.Select(attrs={'class': 'form-select'}),
            'fullname': forms.TextInput(attrs={'class': 'form-control'}),
            'email': forms.EmailInput(attrs={'class': 'form-control'}),
            'phone': forms.TextInput(attrs={'class': 'form-control'}),
        }


class WorkshopBookingForm(forms.ModelForm):
    class Meta:
        model = WorkshopBooking
        fields = ['workshop', 'date']
        widgets = {
            'workshop': forms.Select(attrs={'class': 'form-select'}),
            'date': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
        }


class WorkshopForm(forms.ModelForm):
    # ✅ ฟิกให้กรอกเป็นตัวเลขเท่านั้น (หน่วย: นาที)
    duration = forms.IntegerField(
        required=False,
        min_value=1,
        label="ระยะเวลารวม (นาที)",
        widget=forms.NumberInput(attrs={
            'type': 'number',
            'class': 'form-control',
            'min': '1',
            'step': '1',
            'placeholder': 'เช่น 90'
        })
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # ✅ ถ้า record เก่า duration เป็นข้อความ ให้ดึง “เลข” ตัวแรกมาใส่ initial
        if self.instance and self.instance.pk and self.instance.duration:
            import re
            m = re.search(r"\d+", str(self.instance.duration))
            if m:
                self.fields["duration"].initial = int(m.group(0))

    def save(self, commit=True):
        instance = super().save(commit=False)

        minutes = self.cleaned_data.get("duration")
        # ✅ เก็บลง DB เป็น “ตัวเลขล้วน” (หมายถึงนาที)
        instance.duration = str(minutes) if minutes is not None else ""

        if commit:
            instance.save()
            self.save_m2m()
        return instance

    class Meta:
        model = Workshop
        fields = [
            'title', 'description', 'start_date', 'end_date',
            'start_time', 'end_time', 'location', 'duration',
            'is_active', 'inactive_reason', 'image', 'detail_image'
        ]
        widgets = {
            'start_date': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
            'end_date': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
            'start_time': forms.TimeInput(attrs={'type': 'time', 'class': 'form-control'}),
            'end_time': forms.TimeInput(attrs={'type': 'time', 'class': 'form-control'}),
            'description': forms.Textarea(attrs={'rows': 4, 'class': 'form-control'}),
            'title': forms.TextInput(attrs={'class': 'form-control'}),
            'location': forms.TextInput(attrs={'class': 'form-control'}),

            'inactive_reason': forms.TextInput(attrs={'class': 'form-control'}),
            'image': HideCurrentFileInput(attrs={'class': 'form-control'}),
            'detail_image': HideCurrentFileInput(attrs={'class': 'form-control'}),
        }

# =========================================================
# 3) SILK / MUSEUM / RATING FORMS
# =========================================================
class SilkPatternForm(forms.ModelForm):
    def clean(self):
        cleaned_data = super().clean()
        # ใช้ชื่อไฟล์จาก mind_file ถ้ามี mind_file อัปโหลดใหม่
        mind_file = self.files.get('mind_file') if hasattr(self, 'files') else None
        if mind_file:
            target_file = mind_file.name
        else:
            target_file = cleaned_data.get('target_file')

        target_index = cleaned_data.get('target_index')

        # ตรวจสอบความซ้ำของ (target_file, target_index) เฉพาะในไฟล์เดียวกัน
        if target_file is not None and target_index is not None:
            qs = SilkPattern.objects.filter(target_file=target_file, target_index=target_index)
            if self.instance.pk:
                qs = qs.exclude(pk=self.instance.pk)
            if qs.exists():
                self.add_error(
                    'target_index',
                    'ลำดับนี้ถูกใช้ไปแล้วในไฟล์ .mind นี้ (Target Index ซ้ำในไฟล์เดียวกัน)'
                )
        return cleaned_data

    # ฟิลด์เสริมสำหรับอัปโหลดไฟล์ .mind ไปเก็บใน static/main/targets
    mind_file = forms.FileField(
        required=False,
        label="ไฟล์ .mind (Target File)",
        widget=HideCurrentFileInput(attrs={'class': 'form-control'}),
        help_text="อัปโหลดไฟล์ .mind จะถูกเก็บใน static/main/targets และตั้งชื่อให้กับช่อง Target File อัตโนมัติ",
    )

    class Meta:
        model = SilkPattern
        fields = [
            'Si_ID', 'Si_name', 'Si_address', 'Si_type',
            'Si_color', 'Si_history', 'reference',
            'target_index', 'target_file', 'model_3d', 'image'
        ]
        widgets = {
            'Si_ID': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'เช่น SILK001'}),
            'Si_name': forms.TextInput(attrs={'class': 'form-control'}),
            'Si_address': forms.TextInput(attrs={'class': 'form-control'}),
            'Si_type': forms.TextInput(attrs={'class': 'form-control'}),
            'Si_color': forms.TextInput(attrs={'class': 'form-control'}),
            'Si_history': forms.Textarea(attrs={'class': 'form-control', 'rows': 4}),

            # ✅ เปลี่ยนเป็น HideCurrentFileInput (ไม่โชว์ path)
            'reference': HideCurrentFileInput(attrs={'class': 'form-control'}),

            'target_index': forms.NumberInput(attrs={'class': 'form-control'}),
            'target_file': forms.TextInput(
                attrs={'class': 'form-control', 'placeholder': 'เช่น targets0.mind', 'readonly': 'readonly'}
            ),

            # ✅ เปลี่ยนเป็น HideCurrentFileInput (ไม่โชว์ path)
            'model_3d': HideCurrentFileInput(attrs={'class': 'form-control'}),
            'image': HideCurrentFileInput(attrs={'class': 'form-control'}),
        }


class MuseumProfileForm(forms.ModelForm):
    class Meta:
        model = MuseumProfile
        fields = [
            'name', 'history', 'address',
            'opening_hours', 'phone', 'email',
            'hero_image', 'gallery_image1', 'gallery_image2', 'gallery_image3',
        ]
        widgets = {
            'name': forms.TextInput(attrs={
                'class': 'w-full rounded-2xl border border-gray-200 bg-white px-5 py-4 text-gray-800 font-semibold '
                         'focus:border-amber-500 focus:ring-amber-500',
            }),
            'history': forms.Textarea(attrs={
                'rows': 5,
                'class': 'w-full rounded-2xl border border-gray-200 bg-white px-5 py-4 text-gray-800 font-semibold '
                         'leading-relaxed resize-none focus:border-amber-500 focus:ring-amber-500',
            }),
            'address': forms.Textarea(attrs={
                'rows': 3,
                'class': 'w-full rounded-2xl border border-gray-200 bg-white px-5 py-4 text-gray-800 font-semibold '
                         'leading-relaxed resize-none focus:border-amber-500 focus:ring-amber-500',
            }),
            'opening_hours': forms.TextInput(attrs={
                'class': 'w-full rounded-2xl border border-gray-200 bg-white px-5 py-4 text-gray-800 font-semibold '
                         'focus:border-amber-500 focus:ring-amber-500',
            }),
            'phone': forms.TextInput(attrs={
                'class': 'w-full rounded-2xl border border-gray-200 bg-white px-5 py-4 text-gray-800 font-semibold '
                         'focus:border-amber-500 focus:ring-amber-500',
            }),
            'email': forms.EmailInput(attrs={
                'class': 'w-full rounded-2xl border border-gray-200 bg-white px-5 py-4 text-gray-800 font-semibold '
                         'focus:border-amber-500 focus:ring-amber-500',
            }),

            # ✅ HideCurrentFileInput (ไม่โชว์ path) + แต่งด้วย Tailwind
            'hero_image': HideCurrentFileInput(attrs={
                'class': 'block w-full rounded-2xl border border-gray-200 bg-white px-4 py-3 text-sm text-gray-600 '
                         'file:mr-4 file:py-2 file:px-4 file:rounded-full file:border-0 '
                         'file:text-sm file:font-semibold file:bg-amber-50 file:text-amber-700 '
                         'hover:file:bg-amber-100 cursor-pointer',
            }),
            'gallery_image1': HideCurrentFileInput(attrs={
                'class': 'block w-full rounded-2xl border border-gray-200 bg-white px-4 py-3 text-sm text-gray-600 '
                         'file:mr-4 file:py-2 file:px-4 file:rounded-full file:border-0 '
                         'file:text-sm file:font-semibold file:bg-amber-50 file:text-amber-700 '
                         'hover:file:bg-amber-100 cursor-pointer',
            }),
            'gallery_image2': HideCurrentFileInput(attrs={
                'class': 'block w-full rounded-2xl border border-gray-200 bg-white px-4 py-3 text-sm text-gray-600 '
                         'file:mr-4 file:py-2 file:px-4 file:rounded-full file:border-0 '
                         'file:text-sm file:font-semibold file:bg-amber-50 file:text-amber-700 '
                         'hover:file:bg-amber-100 cursor-pointer',
            }),
            'gallery_image3': HideCurrentFileInput(attrs={
                'class': 'block w-full rounded-2xl border border-gray-200 bg-white px-4 py-3 text-sm text-gray-600 '
                         'file:mr-4 file:py-2 file:px-4 file:rounded-full file:border-0 '
                         'file:text-sm file:font-semibold file:bg-amber-50 file:text-amber-700 '
                         'hover:file:bg-amber-100 cursor-pointer',
            }),
        }


class BookingRatingForm(forms.ModelForm):
    class Meta:
        model = SilkPatternRating
        fields = [
            'group_type',
            'q1_display', 'q2_knowledge', 'q3_quality',
            'q4_variety', 'q5_colors', 'q6_ar_experience',
            'q7_guide', 'q8_facility', 'q9_price',
            'q10_recommend', 'comment'
        ]
        widgets = {
            'group_type': forms.Select(attrs={'class': 'form-select'}),
            'comment': forms.Textarea(attrs={'rows': 3, 'class': 'form-control'}),
        }

# =========================================================
# 4) SPEAKER & QUESTION FORMS
# =========================================================
class SpeakerAssignFromBookingForm(forms.ModelForm):
    class Meta:
        model = SpeakerAssignment
        fields = ['speaker', 'title', 'note', 'status']
        widgets = {
            'speaker': forms.Select(attrs={'class': 'form-select'}),
            'title': forms.TextInput(attrs={'class': 'form-control'}),
            'note': forms.Textarea(attrs={'rows': 3, 'class': 'form-control'}),
            'status': forms.Select(attrs={'class': 'form-select'}),
        }


class QuestionForm(forms.ModelForm):
    class Meta:
        model = Question
        fields = ['question', 'option_a', 'option_b', 'option_c', 'option_d', 'option_e', 'is_active']
        widgets = {
            'question': forms.Textarea(attrs={'rows': 3, 'placeholder': 'ระบุหัวข้อการประเมิน...'}),
            'option_a': forms.TextInput(attrs={'placeholder': '5', 'readonly': 'readonly'}),
            'option_b': forms.TextInput(attrs={'placeholder': '4', 'readonly': 'readonly'}),
            'option_c': forms.TextInput(attrs={'placeholder': '3', 'readonly': 'readonly'}),
            'option_d': forms.TextInput(attrs={'placeholder': '2', 'readonly': 'readonly'}),
            'option_e': forms.TextInput(attrs={'placeholder': '1', 'readonly': 'readonly'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        fixed_options = {
            'option_a': '5',
            'option_b': '4',
            'option_c': '3',
            'option_d': '2',
            'option_e': '1',
        }

        for name, value in fixed_options.items():
            if name in self.fields:
                self.fields[name].initial = value
                self.fields[name].disabled = True
                self.fields[name].widget.attrs['value'] = value

    def save(self, commit=True):
        instance = super().save(commit=False)
        instance.option_a = '5'
        instance.option_b = '4'
        instance.option_c = '3'
        instance.option_d = '2'
        instance.option_e = '1'

        if commit:
            instance.save()
        return instance


class SurveyRatingForm(forms.ModelForm):
    RATING_CHOICES = [
        (5, '5'),
        (4, '4'),
        (3, '3'),
        (2, '2'),
        (1, '1'),
    ]

    rating = forms.ChoiceField(choices=RATING_CHOICES, widget=forms.RadioSelect, label='คะแนน')
    comment = forms.CharField(required=False, widget=forms.Textarea(attrs={'rows': 3}), label='ข้อเสนอแนะ (ถ้ามี)')

    class Meta:
        model = SurveyRating
        fields = ['rating', 'comment']

class ProfileEditForm(forms.ModelForm):
    class Meta:
        model = Profile
        fields = ["full_name", "phone", "image"]
        widgets = {
            "full_name": forms.TextInput(attrs={"class": "w-full px-4 py-2 rounded-xl border border-gray-300"}),
            "phone": forms.TextInput(attrs={"class": "w-full px-4 py-2 rounded-xl border border-gray-300"}),
            # image ใช้ input file ปกติได้ (template คุณจัดสไตล์เองอยู่แล้ว)
        }
