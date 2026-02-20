"""
Django settings for myproject project.
"""

from pathlib import Path
import os
import mimetypes # นำเข้า module สำหรับจัดการชนิดไฟล์

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent

# =====================================================================
# SECURITY SETTINGS
# =====================================================================
SECRET_KEY = 'django-insecure-qd+n9(-*!z45t_9@)@460^jzuzz=qm7!mw#k35d(=z09kc4v5('

# เปิด Debug ไว้สำหรับการพัฒนา
DEBUG = True

# ---------------------------------------------------------------------
# [CRITICAL UPDATE] ตั้งค่าให้เข้าถึงได้จากทุกที่ (เพื่อให้มือถือเข้าได้)
# ---------------------------------------------------------------------
ALLOWED_HOSTS = ['*']

# ---------------------------------------------------------------------
# [CRITICAL UPDATE] อนุญาต Ngrok สำหรับ HTTPS (เพื่อให้กล้อง AR เปิดได้)
# ---------------------------------------------------------------------
CSRF_TRUSTED_ORIGINS = [
    'https://*.ngrok-free.app',
    'https://*.ngrok.io',
    'http://localhost:8000',
    'http://127.0.0.1:8000',
]

# =====================================================================
# APPLICATION DEFINITION
# =====================================================================
INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'main', # แอปหลักของคุณ
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'myproject.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
                'django.template.context_processors.media', # จำเป็นสำหรับการเรียก URL ไฟล์ Media
                'main.context_processors.museum_context',
            ],
        },
    },
]

WSGI_APPLICATION = 'myproject.wsgi.application'

# =====================================================================
# DATABASE SETTINGS (MySQL)
# =====================================================================
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.mysql",
        "NAME": "thaisilk_db",
        "USER": "root",
        "PASSWORD": "1234",
        "HOST": "localhost",
        "PORT": "3306",
        "OPTIONS": {
            "charset": "utf8mb4",
            "init_command": "SET sql_mode='STRICT_TRANS_TABLES'",
        },
        "CONN_MAX_AGE": 60,
    }
}

# =====================================================================
# PASSWORD VALIDATION
# =====================================================================
AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
]

# =====================================================================
# INTERNATIONALIZATION
# =====================================================================
LANGUAGE_CODE = 'th'
TIME_ZONE = 'Asia/Bangkok'
USE_I18N = True
USE_TZ = True

# =====================================================================
# STATIC & MEDIA FILES SETTINGS
# =====================================================================

# Static files (CSS, JavaScript, Images)
STATIC_URL = '/static/'
STATICFILES_DIRS = [
    BASE_DIR / "static",
]
STATIC_ROOT = BASE_DIR / "staticfiles"

# Media files (ไฟล์ที่อัปโหลดผ่าน Admin: ลายผ้า, โมเดล 3D)
MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'

# เพิ่มขีดจำกัดขนาดไฟล์อัปโหลด (50MB) รองรับไฟล์ 3D ใหญ่ๆ
DATA_UPLOAD_MAX_MEMORY_SIZE = 52428800  
FILE_UPLOAD_MAX_MEMORY_SIZE = 52428800  

# =====================================================================
# AUTHENTICATION SETTINGS
# =====================================================================
LOGIN_URL = '/login/'
LOGIN_REDIRECT_URL = 'home'
LOGOUT_REDIRECT_URL = 'login'

# =====================================================================
# EXTRA CONFIGURATION
# =====================================================================
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# ---------------------------------------------------------------------
# [CRITICAL FIX] บังคับ MIME Type ให้ถูกต้อง
# เพื่อแก้ปัญหา Browser โหลดไฟล์ .mind หรือ .glb ไม่ได้
# ---------------------------------------------------------------------
mimetypes.add_type("text/javascript", ".js", True)
mimetypes.add_type("model/gltf-binary", ".glb", True)
mimetypes.add_type("application/octet-stream", ".mind", True)