from __future__ import annotations

import random
from dataclasses import dataclass

from django.contrib.auth import get_user_model
from django.core.management.base import CommandError
from django.core.management.base import BaseCommand
from django.db import transaction

from main.models import Profile, Speaker


THAI_FIRST_NAMES = [
    "กิตติ", "ธนกฤต", "ณัฐ", "พีร", "ปริญญา", "ศุภชัย", "วรพล", "ชยพล", "ภัทร", "อธิชัย",
    "ชนัญชิดา", "พิมพ์", "กานดา", "ณิชา", "ศศิ", "ภัทรา", "อร", "กัญญา", "สุภัสสรา", "พัชรินทร์",
]


THAI_FIRST_NAMES_LATIN = {
    "กิตติ": "kitti",
    "ธนกฤต": "thanakrit",
    "ณัฐ": "nat",
    "พีร": "peera",
    "ปริญญา": "parinya",
    "ศุภชัย": "supachai",
    "วรพล": "woraphon",
    "ชยพล": "chayapol",
    "ภัทร": "phat",
    "อธิชัย": "athichai",
    "ชนัญชิดา": "chananchida",
    "พิมพ์": "phim",
    "กานดา": "kanda",
    "ณิชา": "nicha",
    "ศศิ": "sasi",
    "ภัทรา": "phatra",
    "อร": "on",
    "กัญญา": "kanya",
    "สุภัสสรา": "supatsara",
    "พัชรินทร์": "patcharin",
}


THAI_LAST_NAMES = [
    "ศรีสวัสดิ์", "สุขใจ", "พงศ์ไพศาล", "วัฒนกุล", "แสงทอง", "ชัยวัฒน์", "บุญมี", "นภากุล", "ศิริวงศ์", "ธีรพงศ์",
    "เจริญสุข", "ศรีสมบูรณ์", "พูนผล", "ธรรมชาติ", "สุวรรณ", "รุ่งเรือง", "กมล", "อนันต์", "วิไล", "วิเศษ",
]


THAI_LAST_NAMES_LATIN = {
    "ศรีสวัสดิ์": "srisawat",
    "สุขใจ": "sukjai",
    "พงศ์ไพศาล": "phongpaisan",
    "วัฒนกุล": "wattanakul",
    "แสงทอง": "saengthong",
    "ชัยวัฒน์": "chaiwat",
    "บุญมี": "bunmee",
    "นภากุล": "napakul",
    "ศิริวงศ์": "siriwong",
    "ธีรพงศ์": "teerapong",
    "เจริญสุข": "charoensuk",
    "ศรีสมบูรณ์": "srisomboon",
    "พูนผล": "poonphon",
    "ธรรมชาติ": "thammachat",
    "สุวรรณ": "suwan",
    "รุ่งเรือง": "rungrueang",
    "กมล": "kamon",
    "อนันต์": "anan",
    "วิไล": "wilai",
    "วิเศษ": "wiset",
}


SPEAKER_EXPERTISE = [
    "ผ้าไหมไทยและลวดลายพื้นถิ่น",
    "การทอผ้าและเทคนิคย้อมสีธรรมชาติ",
    "ประวัติศาสตร์สิ่งทอและวัฒนธรรม",
    "การออกแบบลายผ้าเชิงร่วมสมัย",
    "การอนุรักษ์ผ้าและการดูแลสิ่งทอ",
    "งานหัตถกรรมและภูมิปัญญาชุมชน",
]


SPEAKER_BIO_TEMPLATES = [
    "วิทยากรผู้เชี่ยวชาญด้าน{expertise} มีประสบการณ์ถ่ายทอดความรู้ในชุมชนและเวิร์กช็อปมากกว่า {years} ปี",
    "ทำงานวิจัยและลงพื้นที่เกี่ยวกับ{expertise} อย่างต่อเนื่อง สนใจการสืบสานภูมิปัญญาและการประยุกต์ใช้ในยุคปัจจุบัน",
    "มีผลงานจัดกิจกรรมการเรียนรู้เกี่ยวกับ{expertise} เน้นการเรียนรู้แบบลงมือปฏิบัติและเข้าใจบริบทของท้องถิ่น",
]


@dataclass(frozen=True)
class PersonData:
    first_name: str
    last_name: str
    phone: str


def _random_th_phone(rng: random.Random) -> str:
    prefix = rng.choice(["06", "08", "09"])
    return prefix + "".join(str(rng.randint(0, 9)) for _ in range(8))


def _pick_unique_person(rng: random.Random, used_full_names: set[str]) -> PersonData:
    for _ in range(5000):
        first = rng.choice(THAI_FIRST_NAMES)
        last = rng.choice(THAI_LAST_NAMES)
        full = f"{first} {last}".strip()
        if full in used_full_names:
            continue
        used_full_names.add(full)
        return PersonData(first_name=first, last_name=last, phone=_random_th_phone(rng))
    raise RuntimeError("Unable to generate unique sample names")


def _make_realistic_username(
    *,
    rng: random.Random,
    user_model,
    first_name_th: str,
    last_name_th: str,
    category: str,
    used_usernames: set[str],
) -> str:
    first = THAI_FIRST_NAMES_LATIN.get(first_name_th, "member")
    last = THAI_LAST_NAMES_LATIN.get(last_name_th, "user")
    base = f"{first}.{last}".lower()

    if category == "speaker":
        base = f"{base}.sp"

    base = base.replace(" ", "")

    for _ in range(2000):
        suffix = rng.randint(10, 9999)
        candidate = f"{base}{suffix}"
        if candidate in used_usernames:
            continue
        if user_model.objects.filter(username=candidate).exists():
            continue
        used_usernames.add(candidate)
        return candidate

    raise RuntimeError("Unable to generate unique usernames")


class Command(BaseCommand):
    help = "Create sample normal users with filled profile data."

    def add_arguments(self, parser):
        parser.add_argument(
            "--count",
            type=int,
            default=50,
            help="Number of users to create (default: 50).",
        )
        parser.add_argument(
            "--password",
            type=str,
            default="Z12345678",
            help="Password for all created users (default: Z12345678).",
        )
        parser.add_argument(
            "--username-prefix",
            type=str,
            default="user",
            help="Username prefix (default: user).",
        )
        parser.add_argument(
            "--email-domain",
            type=str,
            default="example.com",
            help="Email domain to use (default: example.com).",
        )
        parser.add_argument(
            "--start-index",
            type=int,
            default=1,
            help="Start index for username numbering (default: 1).",
        )

        parser.add_argument(
            "--purge",
            action="store_true",
            help="Delete ALL users except the one specified by --keep-username (dangerous).",
        )
        parser.add_argument(
            "--keep-username",
            type=str,
            default="admin",
            help="Username to keep when using --purge (default: admin).",
        )

        parser.add_argument(
            "--use-prefix-usernames",
            action="store_true",
            help="Even with --realistic, keep old username pattern (prefix + number).",
        )

        parser.add_argument(
            "--realistic",
            action="store_true",
            help="Use more realistic (but synthetic) Thai-like names/phones.",
        )
        parser.add_argument(
            "--seed",
            type=int,
            default=68,
            help="Random seed for deterministic data generation (default: 68).",
        )
        parser.add_argument(
            "--update-existing",
            action="store_true",
            help=(
                "Update existing users that match the username prefix instead of creating new ones. "
                "(Useful to make existing sample users look more realistic.)"
            ),
        )
        parser.add_argument(
            "--speakers",
            type=int,
            default=0,
            help="Number of speakers to create (default: 0).",
        )
        parser.add_argument(
            "--speaker-username-prefix",
            type=str,
            default="speaker",
            help="Username prefix for speaker accounts (default: speaker).",
        )

    @transaction.atomic
    def handle(self, *args, **options):
        count: int = options["count"]
        password: str = options["password"]
        username_prefix: str = options["username_prefix"]
        email_domain: str = options["email_domain"]
        start_index: int = options["start_index"]
        realistic: bool = options["realistic"]
        seed: int = options["seed"]
        update_existing: bool = options["update_existing"]
        speakers: int = options["speakers"]
        speaker_username_prefix: str = options["speaker_username_prefix"]
        purge: bool = options["purge"]
        keep_username: str = options["keep_username"]
        use_prefix_usernames: bool = options["use_prefix_usernames"]

        if count <= 0:
            self.stdout.write(self.style.WARNING("Nothing to do (count <= 0)."))
            # Still allow speaker creation
            count = 0

        User = get_user_model()

        rng = random.Random(seed)
        used_full_names: set[str] = set()
        used_usernames: set[str] = set()

        if realistic:
            self.stdout.write(
                self.style.WARNING(
                    "Generating realistic-looking sample data (synthetic; not real personal data)."
                )
            )

        if purge:
            keep_user = User.objects.filter(username=keep_username).first()
            if not keep_user:
                raise CommandError(
                    f"Cannot purge because keep user '{keep_username}' was not found. "
                    "Create it first (e.g. createsuperuser) or change --keep-username."
                )

            users_to_delete = User.objects.exclude(pk=keep_user.pk)

            # Import here to avoid unused imports when command is used only for creation.
            from main.models import (
                Booking,
                BookingQuestionResponse,
                Reservation,
                SurveyRating,
                WorkshopBooking,
            )

            # Clear user-related records first so pre_delete protections won't block User deletion.
            BookingQuestionResponse.objects.filter(user__in=users_to_delete).delete()
            SurveyRating.objects.filter(user__in=users_to_delete).delete()
            Reservation.objects.filter(user__in=users_to_delete).delete()
            WorkshopBooking.objects.filter(user__in=users_to_delete).delete()
            Booking.objects.filter(Us_ID__in=users_to_delete).delete()

            # Remove speakers (and cascading assignments/uploads/images) except if tied to keep_user.
            Speaker.objects.exclude(user=keep_user).delete()

            deleted = users_to_delete.delete()

            # Ensure the kept user has a profile.
            Profile.objects.get_or_create(user=keep_user)

            self.stdout.write(
                self.style.SUCCESS(
                    f"Purged users except '{keep_username}'. Deleted summary: {deleted}"
                )
            )

        created = 0
        updated = 0

        if update_existing and count > 0:
            # Update up to `count` existing users with the prefix.
            users_to_update = list(
                User.objects.filter(username__startswith=username_prefix).order_by("username")[:count]
            )
            for user in users_to_update:
                if realistic:
                    person = _pick_unique_person(rng, used_full_names)
                    user.first_name = person.first_name
                    user.last_name = person.last_name
                    profile_phone = person.phone
                else:
                    # Keep deterministic placeholder updates.
                    user.first_name = (user.first_name or "").strip() or "User"
                    user.last_name = (user.last_name or "").strip() or "Sample"
                    profile_phone = (getattr(user, "profile", None) and user.profile.phone) or ""

                if not user.email:
                    user.email = f"{user.username}@{email_domain}"

                user.save()

                profile, _ = Profile.objects.get_or_create(user=user)
                profile.full_name = f"{user.first_name} {user.last_name}".strip()
                if realistic and profile_phone:
                    profile.phone = profile_phone
                if hasattr(profile, "role"):
                    profile.role = "member"
                profile.save()
                updated += 1
        else:
            attempted_index = start_index
            # Create exactly `count` new users, skipping existing usernames.
            while created < count:
                if realistic and not use_prefix_usernames:
                    person = _pick_unique_person(rng, used_full_names)
                    first_name = person.first_name
                    last_name = person.last_name
                    phone = person.phone
                    username = _make_realistic_username(
                        rng=rng,
                        user_model=User,
                        first_name_th=first_name,
                        last_name_th=last_name,
                        category="member",
                        used_usernames=used_usernames,
                    )
                else:
                    username = f"{username_prefix}{attempted_index:03d}"
                    attempted_index += 1

                    if User.objects.filter(username=username).exists():
                        continue

                    if realistic:
                        person = _pick_unique_person(rng, used_full_names)
                        first_name = person.first_name
                        last_name = person.last_name
                        phone = person.phone
                    else:
                        first_name = f"User{attempted_index - 1:03d}"
                        last_name = "Sample"
                        phone = f"080000{attempted_index - 1:04d}"  # e.g. 0800000001

                email = f"{username}@{email_domain}"

                user = User.objects.create_user(
                    username=username,
                    email=email,
                    password=password,
                    first_name=first_name,
                    last_name=last_name,
                )

                profile, _ = Profile.objects.get_or_create(user=user)
                profile.full_name = f"{first_name} {last_name}".strip()
                profile.phone = phone
                if hasattr(profile, "role"):
                    profile.role = "member"
                profile.save()

                created += 1

        speaker_created = 0
        if speakers and speakers > 0:
            attempted_index = 1
            while speaker_created < speakers:
                if realistic and not use_prefix_usernames:
                    person = _pick_unique_person(rng, used_full_names)
                    username = _make_realistic_username(
                        rng=rng,
                        user_model=User,
                        first_name_th=person.first_name,
                        last_name_th=person.last_name,
                        category="speaker",
                        used_usernames=used_usernames,
                    )
                else:
                    username = f"{speaker_username_prefix}{attempted_index:03d}"
                    attempted_index += 1

                    if User.objects.filter(username=username).exists():
                        continue

                    person = _pick_unique_person(rng, used_full_names) if realistic else PersonData(
                        first_name=f"Speaker{attempted_index - 1:03d}",
                        last_name="Sample",
                        phone=f"090000{attempted_index - 1:04d}",
                    )

                if User.objects.filter(username=username).exists():
                    continue

                user = User.objects.create_user(
                    username=username,
                    email=f"{username}@{email_domain}",
                    password=password,
                    first_name=person.first_name,
                    last_name=person.last_name,
                )

                profile, _ = Profile.objects.get_or_create(user=user)
                profile.full_name = f"{person.first_name} {person.last_name}".strip()
                profile.phone = person.phone
                if hasattr(profile, "role"):
                    profile.role = "speaker"
                profile.save()

                expertise = rng.choice(SPEAKER_EXPERTISE)
                years = rng.randint(3, 20)
                bio = " ".join(
                    template.format(expertise=expertise, years=years)
                    for template in rng.sample(SPEAKER_BIO_TEMPLATES, k=2)
                )

                Speaker.objects.create(
                    user=user,
                    name=profile.full_name or f"{person.first_name} {person.last_name}".strip(),
                    biography=bio,
                    expertise=expertise,
                )

                speaker_created += 1

        self.stdout.write(
            self.style.SUCCESS(
                "Done: "
                f"created_users={created}, updated_users={updated}, speakers_created={speaker_created}. "
                f"Password for created accounts: {password}"
            )
        )
