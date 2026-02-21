"""
main/forms.py
"""
from django import forms
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError

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
    class Meta:
        model = Workshop
        fields = [
            'title', 'description', 'start_date', 'end_date', 
            'start_time', 'end_time', 'session_period', 'location', 'duration',
            'max_participants', 'is_active', 'inactive_reason', 'image', 'detail_image'
        ]
        widgets = {
            'start_date': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
            'end_date': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
            'start_time': forms.TimeInput(attrs={'type': 'time', 'class': 'form-control'}),
            'end_time': forms.TimeInput(attrs={'type': 'time', 'class': 'form-control'}),
            'session_period': forms.Select(attrs={'class': 'form-select'}),
            'description': forms.Textarea(attrs={'rows': 4, 'class': 'form-control'}),
            'title': forms.TextInput(attrs={'class': 'form-control'}),
            'location': forms.TextInput(attrs={'class': 'form-control'}),
            'duration': forms.TextInput(attrs={'class': 'form-control'}),
            'max_participants': forms.NumberInput(attrs={'class': 'form-control'}),
            'inactive_reason': forms.TextInput(attrs={'class': 'form-control'}),
            'image': forms.ClearableFileInput(attrs={'class': 'form-control'}),
            'detail_image': forms.ClearableFileInput(attrs={'class': 'form-control'}),
        }

# =========================================================
# 3) SILK / MUSEUM / RATING FORMS
# =========================================================
class SilkPatternForm(forms.ModelForm):
    class Meta:
        model = SilkPattern
        # อัปเดตเป็นชื่อฟิลด์ใหม่ตาม Model
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
            'reference': forms.ClearableFileInput(attrs={'class': 'form-control'}),
            'target_index': forms.NumberInput(attrs={'class': 'form-control'}),
            'target_file': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'เช่น targets0.mind'}),
            'model_3d': forms.ClearableFileInput(attrs={'class': 'form-control'}),
            'image': forms.ClearableFileInput(attrs={'class': 'form-control'}),
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
            'name': forms.TextInput(attrs={'class': 'form-control'}),
            'history': forms.Textarea(attrs={'rows': 5, 'class': 'form-control'}),
            'address': forms.Textarea(attrs={'rows': 3, 'class': 'form-control'}),
            'opening_hours': forms.TextInput(attrs={'class': 'form-control'}),
            'phone': forms.TextInput(attrs={'class': 'form-control'}),
            'email': forms.EmailInput(attrs={'class': 'form-control'}),
            'hero_image': forms.ClearableFileInput(attrs={'class': 'form-control'}),
            'gallery_image1': forms.ClearableFileInput(attrs={'class': 'form-control'}),
            'gallery_image2': forms.ClearableFileInput(attrs={'class': 'form-control'}),
            'gallery_image3': forms.ClearableFileInput(attrs={'class': 'form-control'}),
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
        # เหลือแค่ฟิลด์ที่มีอยู่ใน Model จริงๆ
        fields = ['question', 'option_a', 'option_b', 'option_c', 'option_d', 'option_e', 'is_active']
        widgets = {
            'question': forms.Textarea(attrs={'rows': 3, 'placeholder': 'ระบุหัวข้อการประเมิน...'}),
            # สเกลถูกล็อกเป็น 5-4-3-2-1 แก้ไขได้เฉพาะหัวข้อคำถาม
            'option_a': forms.TextInput(attrs={'placeholder': '5', 'readonly': 'readonly'}),
            'option_b': forms.TextInput(attrs={'placeholder': '4', 'readonly': 'readonly'}),
            'option_c': forms.TextInput(attrs={'placeholder': '3', 'readonly': 'readonly'}),
            'option_d': forms.TextInput(attrs={'placeholder': '2', 'readonly': 'readonly'}),
            'option_e': forms.TextInput(attrs={'placeholder': '1', 'readonly': 'readonly'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # ล็อกค่า option ให้เป็น 5-4-3-2-1 และปิดไม่ให้แก้ไขในฟอร์ม
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
                # ให้แสดงค่าใน input ทันที
                self.fields[name].widget.attrs['value'] = value

    def save(self, commit=True):
        """บันทึกคำถามโดยบังคับสเกลตัวเลือกเป็น 5-4-3-2-1 เสมอ"""
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
    comment = forms.CharField(required=False, widget=forms.Textarea(attrs={'rows':3}), label='ข้อเสนอแนะ (ถ้ามี)')

    class Meta:
        model = SurveyRating
        fields = ['rating', 'comment']
