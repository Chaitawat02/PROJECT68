from django.urls import path
from django.shortcuts import redirect
from django.conf import settings
from django.conf.urls.static import static

from . import views

urlpatterns = [
    # ======================================================
    # 0) Redirect / Utility
    # ======================================================
    path("user/booking_history/", lambda request: redirect("booking_history", permanent=True)),
    path("booking/<int:booking_id>/cancel/", views.booking_cancel_view, name="booking_cancel"),

    # ======================================================
    # 1) PUBLIC PAGES & AUTHENTICATION
    # ======================================================
    path("", views.home_view, name="home"),

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
    path("silk/<int:pk>/", views.silk_detail_view, name="silk_detail"),
    # path("silk/<int:pk>/ar/", views.silk_ar_view, name="silk_ar_detail"),
    path("silk/<int:pk>/qr/", views.silk_qr_view, name="silk_qr"),
    path("silk/detail/<str:pattern_id>/", views.silk_detail, name="silk_detail_str"),


    # path("ar/scan/", views.silk_ar_scan_view, name="silk_ar_scan"),
    path("ar-test-tracking/", views.ar_test_view, name="ar_test_tracking"),
    path("ar-mirror/", views.ar_test_view, name="ar_mirror"),

    # ======================================================
    # 3) WORKSHOPS & USER BOOKING
    # ======================================================
    path("workshops/", views.workshops_view, name="workshops"),
    path("workshops/list/", views.workshops_list_view, name="workshops_list"),

    path("booking/", views.booking_view, name="booking"),
    path("user/history/", views.user_booking_history_view, name="booking_history"),
    path("booking/<int:booking_id>/edit/", views.booking_edit_view, name="booking_edit"),
    path("booking/<int:booking_id>/detail/", views.booking_detail_view, name="booking_detail"),
    path("booking/<int:booking_id>/questionnaire/", views.booking_questionnaire_view, name="booking_questionnaire"),
    path("booking/<int:pk>/rate/", views.booking_rate_view, name="booking_rate"),

    # ======================================================
    # 4) SPEAKER PORTAL (สำหรับวิทยากร)
    # ======================================================
    path("speaker/dashboard/", views.speaker_dashboard, name="speaker_dashboard"),
    path("speaker/assignments/<str:assignment_id>/", views.speaker_assignment_detail, name="speaker_assignment_detail"),
    path("speaker/assignments/<str:assignment_id>/accept/", views.accept_assignment, name="accept_assignment"),
    path("speaker/assignments/<str:assignment_id>/complete/", views.complete_assignment, name="complete_assignment"),
    path("speaker/assignments/<str:assignment_id>/reject/", views.reject_assignment, name="reject_assignment"),

    path("speakers/", views.speaker_list_view, name="speaker_list"),
    path("speakers/<int:speaker_id>/", views.speaker_detail_view, name="speaker_detail"),

    path("speaker/edit/<int:speaker_id>/", views.speaker_edit_view, name="speaker_edit_view"),
    path("speaker/pending/", views.speaker_pending_view, name="speaker_pending"),
    path("speaker/in-progress/", views.speaker_in_progress_view, name="speaker_in_progress"),
    path("speaker/completed/", views.speaker_completed_view, name="speaker_completed"),

    path("speaker/report/", views.speaker_report_view, name="speaker_report"),
    path("speaker/report/booking/<int:booking_id>/", views.speaker_report_booking_detail, name="speaker_report_booking_detail"),

    path("speaker/upload-work/", views.speaker_upload_work_view, name="speaker_upload_work"),

    # ======================================================
    # 5) USER DASHBOARD
    # ======================================================
    path("user/dashboard/", views.user_dashboard_view, name="user_dashboard"),
    path("user/profile/edit/", views.user_profile_edit_view, name="user_profile_edit"),
    path("user/profile/image/delete/", views.user_profile_delete_image_view, name="user_profile_delete_image"),

    # ======================================================
    # 6) ADMIN PANEL (ระบบจัดการหลังบ้าน)
    # ======================================================
    path("admin-panel/dashboard/", views.admin_dashboard_view, name="admin_dashboard"),

    # Reports
    path("admin-panel/report/", views.admin_report_view, name="admin_report"),
    path("admin-panel/report/pdf/", views.admin_report_pdf_view, name="admin_report_pdf"),
    path("admin-panel/report/visit/", views.admin_booking_visit_report_view, name="admin_booking_visit_report"),
    path("admin-panel/report/users/", views.admin_users_report_view, name="admin_users_report"),
    path("admin-panel/report/silk/", views.admin_silk_report_view, name="admin_silk_report"),
    path("admin-panel/report/events/", views.admin_events_report_view, name="admin_events_report"),

    # Work gallery
    path("admin-panel/work-gallery/", views.work_gallery_view, name="work_gallery"),

    # Museum info
    path("admin-panel/museum-info/", views.admin_edit_museum_view, name="admin_editmuseum"),

    # Admin: Speaker Management (โฟลเดอร์: speakers)
    path("admin-panel/manage-speakers/", views.manage_speakers_view, name="manage_speakers"),
    path("admin-panel/speaker-assignments/history/", views.speaker_assignment_history_view, name="speaker_assignment_history"),

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
    path("admin-panel/silk/image-delete/<int:image_id>/", views.silk_gallery_image_delete, name="silk_gallery_image_delete"),

    # Admin: Evaluation/Question Management (โฟลเดอร์: Question)
    path("admin-panel/manage-questions/", views.manage_questions_view, name="manage_questions"),
    path("admin-panel/manage-questions/add/", views.manage_questions_add_view, name="manage_questions_add"),
    path("admin-panel/manage-questions/edit/<int:question_id>/", views.manage_questions_edit_view, name="manage_questions_edit"),
    path("admin-panel/manage-questions/delete/<int:question_id>/", views.manage_questions_delete_view, name="manage_questions_delete"),

    # Admin: Booking & Approval (โฟลเดอร์: booking)
    path("admin-panel/approve-bookings/", views.approve_bookings_view, name="approve_bookings"),
    path("admin-panel/approve-bookings/delete/<int:booking_id>/", views.admin_delete_booking_view, name="admin_delete_booking"),
    path("admin-panel/booking/update-status/<int:booking_id>/<str:status>/", views.update_booking_status, name="update_booking_status"),
    path("admin-panel/booking/<int:booking_id>/select-speaker/", views.speaker_assign_from_booking_view, name="speaker_assign_from_booking"),

    # Admin: Booking Responses / Evaluation
    path("admin-panel/booking-responses/", views.booking_responses_admin_view, name="booking_responses_admin"),
    path("admin-panel/booking-responses/summary/", views.booking_responses_summary_view, name="booking_responses_summary"),

    # ======================================================
    # 7) PUBLIC QUESTION (single question rating)
    # ======================================================
    path("question/<int:question_id>/rate/", views.question_rate_view, name="question_rate"),

    # ======================================================
    # 8) API & AJAX
    # ======================================================
    path("api/bookings/", views.booking_list_api, name="booking_list_api"),
    path("api/silk/<int:target_index>/", views.silkpattern_detail_api, name="silkpattern_detail_api"),
    path("api/workshops/by-date/", views.ajax_workshops_by_date_view, name="ajax_workshops_by_date"),
]

# ======================================================
# Static / Media (DEV only)
# ======================================================
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)