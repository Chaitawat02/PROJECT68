from django.db.models import Q
from .models import MuseumProfile, Booking

def museum_context(request):
    museum = MuseumProfile.objects.first()
    return {'museum': museum}

def admin_sidebar_counts(request):
    pending_count = Booking.objects.filter(
        Q(Re_status='pending') | Q(Re_status__isnull=True) | Q(Re_status='')
    ).count()

    pending_assign_count = Booking.objects.filter(
        Re_status='approved'
    ).filter(
        Q(speaker_assignment__isnull=True) | Q(speaker_assignment__status='rejected')
    ).distinct().count()

    return {
        "pending_count": pending_count,
        "pending_assign_count": pending_assign_count,
    }