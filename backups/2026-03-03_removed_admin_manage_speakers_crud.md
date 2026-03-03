Backup created before removing unused admin speaker CRUD routes/views.
Date: 2026-03-03

---

## main/urls.py (original snippet)

```python
    # Admin: Speaker Management (โฟลเดอร์: speakers)
    path("admin-panel/manage-speakers/", views.manage_speakers_view, name="manage_speakers"),
    path("admin-panel/manage-speakers/add/", views.manage_speakers_add_view, name="manage_speakers_add"),
    path("admin-panel/manage-speakers/edit/<int:speaker_id>/", views.manage_speakers_edit_view, name="manage_speakers_edit"),
    path("admin-panel/manage-speakers/delete/<int:speaker_id>/", views.manage_speakers_delete_view, name="manage_speakers_delete"),
```

## main/views.py (original views)

```python
@login_required
@user_passes_test(is_staff_or_admin)
def manage_speakers_add_view(request):
    """ผู้ดูแลระบบเพิ่มวิทยากรคนใหม่"""
    if request.method == 'POST':
        # สมมติว่ามีการเลือก User มาผูกกับ Speaker
        user_id = request.POST.get('user_id')
        name = request.POST.get('name')
        bio = request.POST.get('bio')

        user = get_object_or_404(User, id=user_id)
        Speaker.objects.create(user=user, name=name, bio=bio)

        messages.success(request, 'เพิ่มวิทยากรเรียบร้อยแล้ว')
        return redirect('manage_speakers')

    # ดึง User ที่ยังไม่เป็น Speaker มาให้เลือก
    available_users = User.objects.exclude(speaker__isnull=False)
    return render(request, 'admin_panel/speakers/admin_speaker_form.html', {
        'available_users': available_users,
        'title': 'เพิ่มวิทยากร'
    })

@login_required
@user_passes_test(is_staff_or_admin)
def manage_speakers_edit_view(request, speaker_id):
    """ผู้ดูแลระบบแก้ไขข้อมูลวิทยากร"""
    speaker = get_object_or_404(Speaker, id=speaker_id)
    if request.method == 'POST':
        speaker.name = request.POST.get('name')
        speaker.bio = request.POST.get('bio')
        if 'profile_picture' in request.FILES:
            speaker.profile_picture = request.FILES['profile_picture']
        speaker.save()
        messages.success(request, 'แก้ไขข้อมูลวิทยากรเรียบร้อยแล้ว')
        # redirect กลับมาที่หน้า edit เพื่อให้รูปใหม่แสดงทันที
        return redirect('manage_speakers_edit', speaker_id=speaker.id)

    return render(request, 'admin_panel/speakers/admin_speaker_form.html', {
        'speaker': speaker,
        'title': f'แก้ไขวิทยากร: {speaker.name}'
    })

@login_required
@user_passes_test(is_staff_or_admin)
def manage_speakers_delete_view(request, speaker_id):
    """ผู้ดูแลระบบลบวิทยากร"""
    speaker = get_object_or_404(Speaker, id=speaker_id)
    # เช็คว่าวิทยากรคนนี้ยังมีงานที่ถูกมอบหมายอยู่หรือไม่
    active_statuses = ['pending', 'assigned', 'accepted', 'confirmed']
    has_active_assignments = speaker.assignments.filter(status__in=active_statuses).exists()

    if has_active_assignments:
        messages.error(request, 'ไม่สามารถลบวิทยากรคนนี้ได้ เนื่องจากยังมีงานที่ได้รับมอบหมายอยู่')
    else:
        try:
            speaker.delete()
            messages.success(request, 'ลบวิทยากรเรียบร้อยแล้ว')
        except ProtectedError:
            messages.error(request, 'ไม่สามารถลบวิทยากรได้ เนื่องจากมีประวัติผลงานหรือมีงานที่ปิดงานแล้ว')
    return redirect('manage_speakers')
```
