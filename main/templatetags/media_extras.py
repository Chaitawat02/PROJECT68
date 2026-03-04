from django import template
from django.core.files.storage import default_storage
import re

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


@register.filter
def strip_leading_number(text):
    """Strip a leading numeric prefix like '2.' / '2)' / '2 -' from a string."""
    if text is None:
        return ""
    s = str(text)
    return re.sub(r"^\s*\d+\s*[\.)\-:]\s*", "", s)
