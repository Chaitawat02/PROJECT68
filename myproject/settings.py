"""
Django settings for myproject project.
"""

from pathlib import Path
import os
import mimetypes

BASE_DIR = Path(__file__).resolve().parent.parent

# =====================================================================
# SECURITY SETTINGS
# =====================================================================

# อ่านค่า SECRET_KEY จาก Environment (ต้องตั้งค่าในโฮสต์)
SECRET_KEY = os.environ.get(
    'DJANGO_SECRET_KEY',
    'dev-insecure-key-change-in-production',
)

# DEBUG: ใช้ค่า Environment ถ้าไม่ตั้งจะเป็น False (เหมาะกับ Production)
DEBUG = os.environ.get('DJANGO_DEBUG', 'False').lower() == 'true'

# ✅ โฮสต์ที่อนุญาต: แยกด้วยจุลภาคใน ENV เช่น "myapp.onrender.com,localhost,127.0.0.1"
ALLOWED_HOSTS = [h.strip() for h in os.environ.get(
    'DJANGO_ALLOWED_HOSTS',
    '.onrender.com,localhost,127.0.0.1',
).split(',') if h.strip()]

# ✅ โดเมนที่ไว้ใจสำหรับ CSRF (Render + เพิ่มเองได้ใน ENV)
CSRF_TRUSTED_ORIGINS = [o.strip() for o in os.environ.get(
    'DJANGO_CSRF_TRUSTED_ORIGINS',
    'https://*.onrender.com',
).split(',') if o.strip()]

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
    'main',
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
                'django.template.context_processors.media',
                'main.context_processors.museum_context',
            ],
        },
    },
]

WSGI_APPLICATION = 'myproject.wsgi.application'

# =====================================================================
# DATABASE (ใช้ SQLite สำหรับ Render ฟรี)
# =====================================================================

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "db.sqlite3",
    }
}

# =====================================================================
# PASSWORD VALIDATION
# =====================================================================

AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

# =====================================================================
# INTERNATIONALIZATION
# =====================================================================

LANGUAGE_CODE = 'th'
TIME_ZONE = 'Asia/Bangkok'
USE_I18N = True
USE_TZ = True

# =====================================================================
# STATIC & MEDIA FILES
# =====================================================================

STATIC_URL = '/static/'
STATICFILES_DIRS = [
    BASE_DIR / "static",
]
STATIC_ROOT = BASE_DIR / "staticfiles"

MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'

DATA_UPLOAD_MAX_MEMORY_SIZE = 52428800
FILE_UPLOAD_MAX_MEMORY_SIZE = 52428800

# =====================================================================
# AUTHENTICATION
# =====================================================================

LOGIN_URL = '/login/'
LOGIN_REDIRECT_URL = 'home'
LOGOUT_REDIRECT_URL = 'login'

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# =====================================================================
# MIME FIX
# =====================================================================

mimetypes.add_type("text/javascript", ".js", True)
mimetypes.add_type("model/gltf-binary", ".glb", True)
mimetypes.add_type("application/octet-stream", ".mind", True)