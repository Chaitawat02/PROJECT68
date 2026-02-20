import os, sys
from pathlib import Path
PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from shutil import copy2
import django
os.environ.setdefault('DJANGO_SETTINGS_MODULE','myproject.settings')
django.setup()
from django.conf import settings

src_dir = PROJECT_ROOT / 'profile_pics'
dst_dir = Path(settings.MEDIA_ROOT) / 'profile_pics'
print('SRC:', src_dir)
print('DST:', dst_dir)

if not src_dir.exists():
    print('No source profile_pics folder found at', src_dir)
    sys.exit(1)

os.makedirs(dst_dir, exist_ok=True)

files = list(src_dir.iterdir())
if not files:
    print('No files to copy')
else:
    for f in files:
        if f.is_file():
            dst = dst_dir / f.name
            copy2(f, dst)
            print('copied', f, '->', dst)
print('Done')
