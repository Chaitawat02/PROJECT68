from __future__ import annotations

import os
from uuid import uuid4

from django.utils import timezone
from django.utils.text import slugify


def _safe_ext(filename: str) -> str:
    _, ext = os.path.splitext(filename or "")
    ext = (ext or "").lower()
    # keep short, sane extensions only
    if len(ext) > 10:
        return ""
    return ext


def _ascii_slug(filename: str) -> str:
    base = os.path.splitext(os.path.basename(filename or ""))[0]
    s = slugify(base)
    return s or "upload"


def _uploader_segment(instance) -> str:
    """Best-effort: derive an uploader/owner identifier from the instance graph.

    We intentionally avoid importing Django models here.
    """
    # Common patterns
    for attr in ("user", "Us_ID", "created_by", "uploaded_by", "owner"):
        u = getattr(instance, attr, None)
        if u is not None:
            uid = getattr(u, "pk", None) or getattr(u, "id", None)
            if uid is not None:
                return f"u{uid}"

    # Nested: Profile.user
    profile = getattr(instance, "profile", None)
    if profile is not None:
        u = getattr(profile, "user", None)
        uid = getattr(u, "pk", None) or getattr(u, "id", None)
        if uid is not None:
            return f"u{uid}"

    # Nested: Speaker.user
    speaker = getattr(instance, "speaker", None)
    if speaker is not None:
        u = getattr(speaker, "user", None)
        uid = getattr(u, "pk", None) or getattr(u, "id", None)
        if uid is not None:
            return f"u{uid}"

    # Nested: SpeakerWorkImage -> upload -> speaker -> user
    upload = getattr(instance, "upload", None)
    if upload is not None:
        speaker = getattr(upload, "speaker", None)
        u = getattr(speaker, "user", None) if speaker is not None else None
        uid = getattr(u, "pk", None) or getattr(u, "id", None)
        if uid is not None:
            return f"u{uid}"

    # MuseumProfile has user
    museum_user = getattr(instance, "user", None)
    uid = getattr(museum_user, "pk", None) or getattr(museum_user, "id", None)
    if uid is not None:
        return f"u{uid}"

    return "system"


def _build_path(category: str, instance, filename: str) -> str:
    today = timezone.now()
    uploader = _uploader_segment(instance)
    slug = _ascii_slug(filename)
    ext = _safe_ext(filename)
    token = uuid4().hex[:12]
    # uploads/<category>/<uploader>/<yyyy>/<mm>/<slug>-<token><ext>
    return "/".join(
        [
            "uploads",
            category,
            uploader,
            f"{today:%Y}",
            f"{today:%m}",
            f"{slug}-{token}{ext}",
        ]
    )


# ---- Public upload_to callables ----

def upload_profile_pic(instance, filename: str) -> str:
    return _build_path("profile-pics", instance, filename)


def upload_speaker_profile(instance, filename: str) -> str:
    return _build_path("speaker-profiles", instance, filename)


def upload_museum_image(instance, filename: str) -> str:
    return _build_path("museum", instance, filename)


def upload_workshop_image(instance, filename: str) -> str:
    return _build_path("workshops", instance, filename)


def upload_workshop_gallery(instance, filename: str) -> str:
    return _build_path("workshops-gallery", instance, filename)


def upload_qr_code(instance, filename: str) -> str:
    return _build_path("qr-codes", instance, filename)


def upload_ar_file(instance, filename: str) -> str:
    return _build_path("ar", instance, filename)


def upload_ar_poster(instance, filename: str) -> str:
    return _build_path("ar-posters", instance, filename)


def upload_silk_model(instance, filename: str) -> str:
    return _build_path("silk-models", instance, filename)


def upload_silk_target(instance, filename: str) -> str:
    return _build_path("silk-targets", instance, filename)


def upload_silk_image(instance, filename: str) -> str:
    return _build_path("silk-images", instance, filename)


def upload_silk_gallery_image(instance, filename: str) -> str:
    return _build_path("silk-gallery", instance, filename)


def upload_speaker_work_image(instance, filename: str) -> str:
    return _build_path("speaker-work", instance, filename)
