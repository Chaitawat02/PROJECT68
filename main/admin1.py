# main/admin.py
from django.contrib import admin
from .models import SilkPattern

@admin.register(SilkPattern)
class SilkPatternAdmin(admin.ModelAdmin):
    # แสดงหัวข้อในหน้าลิสต์รายการ
    list_display = ('Si_ID', 'Si_name', 'Si_type', 'target_index', 'has_model')
    
    # เพิ่มตัวกรองข้อมูลด้านขวามือ
    list_filter = ('Si_type', 'Si_color')
    
    # เพิ่มช่องค้นหา
    search_fields = ('Si_ID', 'Si_name', 'Si_history')
    
    # จัดกลุ่มฟิลด์ในหน้าแก้ไขให้ดูง่าย (Fieldsets)
    fieldsets = (
        ('ข้อมูลพื้นฐาน', {
            'fields': ('Si_ID', 'Si_name', 'Si_type', 'Si_color', 'Si_address')
        }),
        ('เนื้อหาและประวัติ', {
            'fields': ('Si_history', 'image')
        }),
        ('ตั้งค่า AR (Augmented Reality)', {
            'fields': ('target_index', 'target_file', 'reference', 'model_3d'),
            'description': 'จัดการไฟล์ .glb และลำดับ Index เพื่อใช้ในการแสดงผล AR'
        }),
    )

    # ฟังก์ชันช่วยเช็คในหน้า List ว่ามีไฟล์โมเดลหรือยัง
    def has_model(self, obj):
        return bool(obj.model_3d)
    has_model.boolean = True
    has_model.short_description = "มีโมเดล 3D"