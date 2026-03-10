from django import template
from django.core.files.storage import FileSystemStorage
import re

register = template.Library()


@register.filter
def file_exists(file_field):
    """Best-effort check whether an uploaded file can be used.

    Notes:
    - For local FileSystemStorage we can reliably check storage.exists(name).
    - For remote/cloud storages (e.g., Cloudinary), exists() may be unsupported or
      return False even when the file is available. In that case, treat a resolvable
      .url as sufficient.
    """
    try:
        if not file_field:
            return False
        name = getattr(file_field, 'name', None)
        if not name:
            return False

        storage = getattr(file_field, "storage", None)
        if isinstance(storage, FileSystemStorage):
            return storage.exists(name)

        # Remote storage: if it can produce a URL, assume it's usable.
        _ = file_field.url
        return True
    except Exception:
        return False


@register.filter
def strip_leading_number(text):
    """Strip a leading numeric prefix like '2.' / '2)' / '2 -' from a string."""
    if text is None:
        return ""
    s = str(text)
    return re.sub(r"^\s*\d+\s*[\.)\-:]\s*", "", s)
