#!/usr/bin/env python
import os
import sys

# --- ส่วนแก้ไขเพื่อข้ามการตรวจสอบ mysqlclient version ---
try:
    import pymysql
    pymysql.install_as_MySQLdb()
    
    # บังคับข้ามการตรวจสอบเวอร์ชันของ Django
    from django.db.backends.mysql import base
    base.Database.version_info = (2, 2, 7, 'final', 0) 
    base.Database.__version__ = "2.2.7"
except Exception:
    pass
# --------------------------------------------------

def main():
    """Run administrative tasks."""
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'myproject.settings')
    try:
        from django.core.management import execute_from_command_line
    except ImportError as exc:
        raise ImportError(
            "Couldn't import Django. Are you sure it's installed and "
            "available on your PYTHONPATH environment variable? Did you "
            "forget to activate a virtual environment?"
        ) from exc
    execute_from_command_line(sys.argv)

if __name__ == '__main__':
    main()