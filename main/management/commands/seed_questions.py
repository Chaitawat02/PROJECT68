from __future__ import annotations

import random

from django.core.management.base import BaseCommand
from django.db import transaction

from main.models import Question


DEFAULT_CHOICES = [
    "น้อยมาก",
    "น้อย",
    "ปานกลาง",
    "มาก",
    "มากที่สุด",
]


def _make_question(text: str) -> dict:
    return {
        "question": text,
        "option_a": DEFAULT_CHOICES[0],
        "option_b": DEFAULT_CHOICES[1],
        "option_c": DEFAULT_CHOICES[2],
        "option_d": DEFAULT_CHOICES[3],
        "option_e": DEFAULT_CHOICES[4],
    }


MUSEUM_QUESTIONS = [
    _make_question("ความสะดวกในการเดินทางและการเข้าถึงพิพิธภัณฑ์"),
    _make_question("ความชัดเจนของป้ายบอกทาง/ป้ายข้อมูลภายในพิพิธภัณฑ์"),
    _make_question("ความสะอาดและความพร้อมของพื้นที่จัดแสดง"),
    _make_question("ความน่าสนใจของนิทรรศการและการจัดแสดงโดยรวม"),
    _make_question("ความเหมาะสมของเวลาเปิด-ปิดและการให้บริการ"),
]

SILK_QUESTIONS = [
    _make_question("ความน่าสนใจของเนื้อหาเกี่ยวกับผ้าไหมและลายผ้า"),
    _make_question("ความเข้าใจง่ายของข้อมูล/คำอธิบายเกี่ยวกับผ้าไหม"),
    _make_question("ความสวยงามและความหลากหลายของลายผ้าไหมที่จัดแสดง"),
    _make_question("ประสบการณ์การเรียนรู้เกี่ยวกับกระบวนการทอผ้าไหม"),
    _make_question("ความคุ้มค่าของการเข้าชมในส่วนเนื้อหาผ้าไหม"),
]

SPEAKER_QUESTIONS = [
    _make_question("ความชัดเจนในการอธิบายของวิทยากร"),
    _make_question("ความรู้ความเชี่ยวชาญของวิทยากรในหัวข้อที่บรรยาย"),
    _make_question("ความเหมาะสมของเวลาและจังหวะการนำเสนอ"),
    _make_question("การเปิดโอกาสให้ซักถามและการตอบคำถามของวิทยากร"),
    _make_question("ความเป็นกันเองและการสื่อสารที่เข้าใจง่าย"),
]

OTHER_QUESTIONS = [
    _make_question("ความพึงพอใจต่อการจอง/การลงทะเบียนเข้าชม"),
    _make_question("ความรวดเร็วและความช่วยเหลือของเจ้าหน้าที่"),
    _make_question("ความเหมาะสมของสิ่งอำนวยความสะดวก (ที่นั่ง/ห้องน้ำ/จุดพัก)"),
    _make_question("ความน่าสนใจของกิจกรรมเสริม/เวิร์กช็อป (ถ้ามี)"),
    _make_question("ความตั้งใจที่จะแนะนำพิพิธภัณฑ์ให้ผู้อื่น"),
]


class Command(BaseCommand):
    help = "Seed 20 survey questions (museum/silk/speaker/other) and activate 15 randomly."

    def add_arguments(self, parser):
        parser.add_argument(
            "--seed",
            type=int,
            default=68,
            help="Random seed for choosing active questions (default: 68).",
        )
        parser.add_argument(
            "--active",
            type=int,
            default=15,
            help="How many questions should be active (default: 15).",
        )
        parser.add_argument(
            "--purge",
            action="store_true",
            help="Delete existing questions before seeding.",
        )

    @transaction.atomic
    def handle(self, *args, **options):
        seed: int = options["seed"]
        active_count: int = options["active"]
        purge: bool = options["purge"]

        if active_count < 0 or active_count > 20:
            raise ValueError("--active must be between 0 and 20")

        if purge:
            Question.objects.all().delete()

        questions = MUSEUM_QUESTIONS + SILK_QUESTIONS + SPEAKER_QUESTIONS + OTHER_QUESTIONS
        if len(questions) != 20:
            raise RuntimeError("Expected exactly 20 questions")

        rng = random.Random(seed)
        active_indices = set(rng.sample(range(20), k=active_count))

        created = 0
        for idx, payload in enumerate(questions):
            q_number = idx + 1
            is_active = idx in active_indices
            question_text = f"{q_number}. {payload['question']}"

            Question.objects.create(
                question=question_text,
                option_a=payload["option_a"],
                option_b=payload["option_b"],
                option_c=payload["option_c"],
                option_d=payload["option_d"],
                option_e=payload["option_e"],
                is_active=is_active,
            )
            created += 1

        active_now = Question.objects.filter(is_active=True).count()
        self.stdout.write(
            self.style.SUCCESS(
                f"Seeded {created} questions. Active={active_now} (seed={seed})."
            )
        )
