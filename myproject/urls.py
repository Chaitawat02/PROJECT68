"""
URL configuration for myproject project.
"""
from django.contrib import admin
from django.urls import path, include
from django.views.generic.base import RedirectView
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
# เปิดให้ Django เข้าถึงไฟล์ที่อัปโหลดผ่าน Admin (Media Files) ในช่วงพัฒนา (DEBUG=True)
if settings.DEBUG:
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)