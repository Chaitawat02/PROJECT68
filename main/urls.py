from django.urls import path
from django.conf import settings
from django.conf.urls.static import static
from . import views

urlpatterns = [
    # ======================================================
    # 1) PUBLIC PAGES & AUTHENTICATION
    # ======================================================
    path("", views.home_view, name="home"),
    path("about/", views.about_view, name="about"),
    path("contact/", views.contact_view, name="contact"),
    path("exhibitions/", views.exhibitions_view, name="exhibitions"),
    
    path("login/", views.login_view, name="login"),
    path("signup/", views.signup_view, name="signup"),
    path("logout/", views.logout_view, name="logout"),
    path("forgot-password/", views.forgot_password_view, name="forgot_password"),
    path("reset-password/", views.reset_password_view, name="reset_password_simple"),
    path("reset-password/<str:token>/", views.reset_password_view, name="reset_password"),

    # ======================================================
    # 2) SILK & COLLECTIONS (สำหรับ User)
    # ======================================================
    path("collections/", views.collections_view, name="collections"),
    path("silk/register/", views.silk_register_view, name="silk_register"),
    path("silk/<int:pk>/", views.silk_detail_view, name="silk_detail"),
    path("silk/<int:pk>/ar/", views.silk_ar_view, name="silk_ar_detail"),
    path("silk/<int:pk>/qr/", views.silk_qr_view, name="silk_qr"),
    path("silk/detail/<str:pattern_id>/", views.silk_detail, name="silk_detail_str"),
    path("silk/<int:pk>/rate/", views.silk_pattern_rating_view, name="silk_pattern_rate"),
    path("ar/scan/", views.silk_ar_scan_view, name="silk_ar_scan"),
    path("ar-test-tracking/", views.ar_test_view, name="ar_test_tracking"),
    path("ar-mirror/", views.ar_test_view, name="ar_mirror"),

    # ======================================================
    # 3) WORKSHOPS & USER BOOKING
    # ======================================================
    path("workshops/", views.workshops_view, name="workshops"),
    path("workshops/list/", views.workshops_list_view, name="workshops_list"),
    path("booking/", views.booking_view, name="booking"),
    path("booking/history/", views.booking_history_view, name="booking_history"),
    path("booking/<int:booking_id>/detail/", views.booking_detail_view, name="booking_detail"),
    path("booking/<int:booking_id>/questionnaire/", views.booking_questionnaire_view, name="booking_questionnaire"),
    path("booking/<int:pk>/rate/", views.booking_rate_view, name="booking_rate"),

    # ======================================================
    # 4) SPEAKER PORTAL (สำหรับวิทยากร)
    # ======================================================
    path("speaker/", views.speaker_home, name="speaker_home"),
    path("speaker/dashboard/", views.speaker_dashboard, name="speaker_dashboard"),
    path("speaker/assignments/", views.speaker_assignment_list, name="speaker_assignments"),
    path("speaker/assignments/<str:assignment_id>/", views.speaker_assignment_detail, name="speaker_assignment_detail"),
    path("speaker/assignments/<str:assignment_id>/accept/", views.accept_assignment, name="accept_assignment"),
    path("speaker/assignments/<str:assignment_id>/complete/", views.complete_assignment, name="complete_assignment"),
    path("speakers/", views.speaker_list_view, name="speaker_list"),
    path("speakers/<int:speaker_id>/", views.speaker_detail_view, name="speaker_detail"),
    path("speaker/edit/<int:speaker_id>/", views.speaker_edit_view, name="speaker_edit_view"),

    # ======================================================
    # 5) ADMIN PANEL (ระบบจัดการหลังบ้าน)
    # ======================================================
    path("admin-panel/dashboard/", views.admin_dashboard_view, name="admin_dashboard"),
    
    # Museum Info Management
    path("admin-panel/museum-info/", views.admin_edit_museum_view, name="admin_editmuseum"),

    # Admin: Speaker Management (อัปเดตโฟลเดอร์: speskers)
    path("admin-panel/manage-speakers/", views.manage_speakers_view, name="manage_speakers"),
    path("admin-panel/manage-speakers/add/", views.manage_speakers_add_view, name="manage_speakers_add"),
    path("admin-panel/manage-speakers/edit/<int:speaker_id>/", views.manage_speakers_edit_view, name="manage_speakers_edit"),
    path("admin-panel/manage-speakers/delete/<int:speaker_id>/", views.manage_speakers_delete_view, name="manage_speakers_delete"),
    path("admin-panel/manage-assignments/", views.manage_assignments_view, name="manage_assignments"),
    path("admin-panel/speakers/<int:speaker_id>/assign/", views.speaker_assign_form_view, name="speaker_assign_form"),
    path("admin-panel/speakers/assign/<int:assignment_id>/confirm/", views.speaker_assign_confirm_view, name="speaker_assign_confirm"),

    # Admin: User Management (โฟลเดอร์: Users)
    path("admin-panel/manage-users/", views.manage_users_view, name="manage_users"),
    path("admin-panel/manage-users/edit/<int:user_id>/", views.manage_users_edit_view, name="manage_users_edit"),
    path("admin-panel/manage-users/delete/<int:user_id>/", views.manage_users_delete_view, name="manage_users_delete"),

    # Admin: Workshop Management (โฟลเดอร์: events)
    path("admin-panel/events/", views.admin_events_list_view, name="admin_events_list"),
    path("admin-panel/events/add/", views.admin_events_add_view, name="admin_events_add"),
    path("admin-panel/events/edit/<int:workshop_id>/", views.admin_events_edit_view, name="admin_events_edit"),
    path("admin-panel/events/delete/<int:workshop_id>/", views.admin_events_delete_view, name="admin_events_delete"),

    # Admin: Silk Management (โฟลเดอร์: Silk)
    path("admin-panel/silk/", views.manage_silk_patterns_view, name="manage_silk_patterns"),
    path("admin-panel/silk/add/", views.manage_silk_patterns_add_view, name="manage_silk_add"),
    path("admin-panel/silk/edit/<int:pattern_id>/", views.manage_silk_edit_view, name="manage_silk_edit"),
    path("admin-panel/silk/delete/<int:pattern_id>/", views.manage_silk_delete_view, name="manage_silk_delete"),

    # Admin: Evaluation/Question Management (โฟลเดอร์: Question)
    path("admin-panel/manage-questions/", views.manage_questions_view, name="manage_questions"),
    path("admin-panel/manage-questions/add/", views.manage_questions_add_view, name="manage_questions_add"),
    path("admin-panel/manage-questions/edit/<int:question_id>/", views.manage_questions_edit_view, name="manage_questions_edit"),
    path("admin-panel/manage-questions/delete/<int:question_id>/", views.manage_questions_delete_view, name="manage_questions_delete"),

    # Public: single question rating (1-5 scale)
    path("question/<int:question_id>/rate/", views.question_rate_view, name="question_rate"),

    # Admin: Booking & Approval (โฟลเดอร์: booking)
    path("admin-panel/approve-bookings/", views.approve_bookings_view, name="approve_bookings"),
    path("admin-panel/booking/update-status/<int:booking_id>/<str:status>/", views.update_booking_status, name="update_booking_status"),
    path("admin-panel/approve-bookings/delete/<int:booking_id>/", views.admin_delete_booking_view, name="admin_delete_booking"),
    path("admin-panel/booking/<int:booking_id>/select-speaker/", views.speaker_assign_from_booking_view, name="speaker_assign_from_booking"),
    path("admin-panel/booking-responses/", views.booking_responses_admin_view, name="booking_responses_admin"),
    path("admin-panel/booking-responses/summary/", views.booking_responses_summary_view, name="booking_responses_summary"),

    # ======================================================
    # 6) API & AJAX
    # ======================================================
    path("api/bookings/", views.booking_list_api, name="booking_list_api"),
    path("api/silk/<int:target_index>/", views.silkpattern_detail_api, name="silkpattern_detail_api"),
    path("api/workshops/by-date/", views.ajax_workshops_by_date_view, name="ajax_workshops_by_date"),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT) # เพิ่มบรรทัดนี้เผื่อไว้สำหรับไฟล์ static