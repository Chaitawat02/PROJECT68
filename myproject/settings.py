"""
Django settings for myproject project.
"""

from pathlib import Path
import os
import mimetypes
import dj_database_url
from urllib.parse import urlparse
from django.core.exceptions import ImproperlyConfigured


BASE_DIR = Path(__file__).resolve().parent.parent

# =====================================================================
# SECURITY SETTINGS
# =====================================================================

SECRET_KEY = os.environ.get(
    'DJANGO_SECRET_KEY',
    'dev-insecure-key-change-in-production',
)

DEBUG = os.environ.get('DJANGO_DEBUG', 'False').lower() == 'true'

ALLOWED_HOSTS = [h.strip() for h in os.environ.get(
    'DJANGO_ALLOWED_HOSTS',
    '.onrender.com,localhost,127.0.0.1',
).split(',') if h.strip()]

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
    'whitenoise.runserver_nostatic',
    'django.contrib.staticfiles',
    'cloudinary',
    'cloudinary_storage',
    'main',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
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
                'main.context_processors.admin_sidebar_counts',
            ],
        },
    },
]

WSGI_APPLICATION = 'myproject.wsgi.application'

# =====================================================================
# DATABASE
# - Production (Render): Postgres via DATABASE_URL
# - Localhost: MySQL
# =====================================================================

DATABASE_URL = os.environ.get("DATABASE_URL")

if DATABASE_URL:
    DATABASES = {
        "default": dj_database_url.parse(
            DATABASE_URL,
            conn_max_age=600,
            ssl_require=True,
        )
    }
else:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.mysql",
            "NAME": "museum_db",
            "USER": "root",
            "PASSWORD": "1234",
            "HOST": "127.0.0.1",
            "PORT": "3306",
            "OPTIONS": {
                "charset": "utf8mb4",
            },
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

# WhiteNoise
# - In production, prefer Manifest storage (hashed filenames) which requires collectstatic.
# - If collectstatic hasn't been run (no manifest yet), fall back so pages don't 500.
WHITENOISE_AUTOREFRESH = DEBUG
WHITENOISE_USE_FINDERS = DEBUG
WHITENOISE_MANIFEST_STRICT = os.environ.get(
    "WHITENOISE_MANIFEST_STRICT",
    "False",
).lower() == "true"

MEDIA_URL = "/media/"

USE_CLOUDINARY = os.environ.get("USE_CLOUDINARY", "False").lower() == "true"

def _cloudinary_storage_from_env() -> dict:
    """Build CLOUDINARY_STORAGE settings.

    Supports either:
    - CLOUDINARY_CLOUD_NAME / CLOUDINARY_API_KEY / CLOUDINARY_API_SECRET
    - CLOUDINARY_URL=cloudinary://<key>:<secret>@<cloud_name>
    """
    cloud_name = (os.environ.get("CLOUDINARY_CLOUD_NAME") or "").strip()
    api_key = (os.environ.get("CLOUDINARY_API_KEY") or "").strip()
    api_secret = (os.environ.get("CLOUDINARY_API_SECRET") or "").strip()

    if cloud_name and api_key and api_secret:
        return {
            "CLOUD_NAME": cloud_name,
            "API_KEY": api_key,
            "API_SECRET": api_secret,
        }

    cloudinary_url = (os.environ.get("CLOUDINARY_URL") or "").strip()
    if cloudinary_url:
        try:
            parsed = urlparse(cloudinary_url)
            # cloudinary://API_KEY:API_SECRET@CLOUD_NAME
            if parsed.scheme.startswith("cloudinary") and parsed.hostname and parsed.username and parsed.password:
                return {
                    "CLOUD_NAME": parsed.hostname,
                    "API_KEY": parsed.username,
                    "API_SECRET": parsed.password,
                }
        except Exception:
            pass

    return {}


CLOUDINARY_STORAGE = _cloudinary_storage_from_env()

if USE_CLOUDINARY and not all(
    CLOUDINARY_STORAGE.get(k) for k in ("CLOUD_NAME", "API_KEY", "API_SECRET")
):
    raise ImproperlyConfigured(
        "USE_CLOUDINARY=true but Cloudinary credentials are missing. "
        "Set CLOUDINARY_URL (cloudinary://<key>:<secret>@<cloud_name>) "
        "or set CLOUDINARY_CLOUD_NAME, CLOUDINARY_API_KEY, CLOUDINARY_API_SECRET."
    )

_static_manifest_path = (STATIC_ROOT / "staticfiles.json")

if DEBUG:
    _staticfiles_backend = "django.contrib.staticfiles.storage.StaticFilesStorage"
else:
    # If the manifest doesn't exist yet, using Manifest storage will crash template rendering
    # with: "Missing staticfiles manifest entry ...".
    if _static_manifest_path.exists():
        _staticfiles_backend = "whitenoise.storage.CompressedManifestStaticFilesStorage"
    else:
        _staticfiles_backend = "whitenoise.storage.CompressedStaticFilesStorage"
        # Allow serving from staticfiles finders as a safe fallback when STATIC_ROOT isn't built.
        WHITENOISE_USE_FINDERS = True

STORAGES = {
    "staticfiles": {
        "BACKEND": _staticfiles_backend,
    }
}

if USE_CLOUDINARY:
    STORAGES["default"] = {
        "BACKEND": "cloudinary_storage.storage.MediaCloudinaryStorage",
    }
else:
    MEDIA_ROOT = Path(os.environ.get("DJANGO_MEDIA_ROOT", str(BASE_DIR / "media")))
    STORAGES["default"] = {
        "BACKEND": "django.core.files.storage.FileSystemStorage",
    }

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