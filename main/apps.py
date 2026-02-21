from django.apps import AppConfig
from django.contrib.auth import get_user_model
from django.db import connection
from django.db.utils import OperationalError, ProgrammingError
import os


class MainConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'main'

    def ready(self):
        """
        Auto create superuser (Render)
        ทำงานเฉพาะเมื่อมี SETUP_ADMIN_KEY ใน Environment
        """

        # ทำงานเฉพาะบนโฮสต์ที่ตั้งค่าไว้
        if not os.environ.get("SETUP_ADMIN_KEY"):
            return

        try:
            # ✅ ถ้าตาราง auth_user ยังไม่มี ให้ข้าม (กันตอน migrate ยังไม่รัน)
            existing_tables = set(connection.introspection.table_names())
            if "auth_user" not in existing_tables:
                return

            User = get_user_model()

            # ✅ แนะนำให้ตั้งใน Render Environment
            username = os.environ.get("ADMIN_USERNAME", "admin")
            email = os.environ.get("ADMIN_EMAIL", "admin@example.com")
            password = os.environ.get("ADMIN_PASSWORD")  # ต้องตั้ง ไม่ควรฝังในโค้ด

            if not password:
                print("⚠️ ADMIN_PASSWORD not set. Skip auto superuser creation.")
                return

            if not User.objects.filter(username=username).exists():
                print("🔐 Creating superuser automatically...")
                User.objects.create_superuser(
                    username=username,
                    email=email,
                    password=password
                )

        except (OperationalError, ProgrammingError):
            # ป้องกัน error ตอน DB ยังไม่พร้อม/ยังไม่ได้ migrate
            return