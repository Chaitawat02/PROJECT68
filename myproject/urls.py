"""
URL configuration for myproject project.
"""
from django.contrib import admin
from django.urls import path, include, re_path
from django.views.generic.base import RedirectView
from django.views.static import serve
from django.conf import settings
from django.conf.urls.static import static

urlpatterns = [
    path('admin/', admin.site.urls),
    
    # จัดการ Login Redirect ให้ตรงกับ settings.py
    path('accounts/login/', RedirectView.as_view(url='/login/', permanent=False)),
    
    # ดึง URLs ทั้งหมดจากแอป main มาใช้งาน
    path('', include('main.urls')),
]

# ส่วนสำคัญมากสำหรับการทำ CRUD:
# เปิดให้ Django เข้าถึงไฟล์ที่อัปโหลดผ่าน Admin (Media Files)
if settings.DEBUG:
    # ระหว่างพัฒนา ให้ Django เสิร์ฟ static/media ตามปกติ
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
else:
    # ใน Production (เช่น Render) static จะเสิร์ฟโดย WhiteNoise จาก STATIC_ROOT
    # ส่วน media ให้ Django เสิร์ฟผ่าน view นี้ (เหมาะกับโปรเจกต์ขนาดเล็ก)
    if getattr(settings, "MEDIA_ROOT", None):
        urlpatterns += [
            re_path(r'^media/(?P<path>.*)$', serve, {'document_root': settings.MEDIA_ROOT}),
        ]