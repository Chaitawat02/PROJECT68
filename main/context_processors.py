from .models import MuseumProfile

def museum_context(request):
    """
    ฟังก์ชันนี้จะส่งตัวแปร 'museum' ไปให้ทุก Template โดยอัตโนมัติ
    """
    # ดึงข้อมูลพิพิธภัณฑ์แถวแรกออกมา
    museum = MuseumProfile.objects.first()
    return {
        'museum': museum
    }