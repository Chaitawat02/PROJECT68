from django import template
from django.core.files.storage import default_storage

register = template.Library()


@register.filter
def file_exists(file_field):
    """Return True if the given FileField/ImageField has a file present on storage."""
    try:
        if not file_field:
            return False
        name = getattr(file_field, 'name', None)
        if not name:
            return False
        return default_storage.exists(name)
    except Exception:
        return False
