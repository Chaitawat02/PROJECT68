from django.apps import AppConfig
from django.contrib.auth import get_user_model
from django.db.utils import OperationalError
import os


class MainConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'main'

    def ready(self):
        """
        Auto create superuser (for Render Free Plan)
        ทำงานเฉพาะเมื่อมี SETUP_ADMIN_KEY ใน Environment
        """

        if os.environ.get("SETUP_ADMIN_KEY"):

            try:
                User = get_user_model()

                username = "admin"
                email = "admin@example.com"
                password = "Admin12345!"

                if not User.objects.filter(username=username).exists():
                    print("🔐 Creating superuser automatically...")
                    User.objects.create_superuser(
                        username=username,
                        email=email,
                        password=password
                    )

            except OperationalError:
                # ป้องกัน error ตอน migrate ยังไม่เสร็จ
                pass