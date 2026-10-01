"""What the administrator can see and ask for, in one place.

RULE_TYPES is keyed by the schema's own type names (agent/schemas.py
CONSTRAINTS); a test keeps the two identical. Step 2's tags, the confirmation
card's tag, the "You can ask for" menu and the "not available" line are all
built from here. Display only: nothing in this file is enforced.
"""

from __future__ import annotations

GROUPS = {
    "times": ("Times", "الأوقات"),
    "rooms": ("Rooms", "القاعات"),
    "students": ("Students", "الطلاب"),
    "ask": ("Ask", "أسئلة"),
}

KINDS = {
    "hard": ("Hard", "إلزامية"),
    "preference": ("Preference", "تفضيل"),
}

# type -> group, kind, settable before the build, name, ready example (ids that
# exist in the demo data)
RULE_TYPES: dict[str, dict] = {
    "campus_break": {
        "group": "times", "kind": "hard", "setup": True,
        "name_en": "Campus break", "name_ar": "استراحة عامة",
        "example_en": "No lectures from 12 to 1 for anyone",
        "example_ar": "لا محاضرات من ١٢ إلى ١",
    },
    "instructor_unavailable": {
        "group": "times", "kind": "hard", "setup": False,
        "name_en": "Instructor unavailable", "name_ar": "مدرّس غير متاح",
        "example_en": "Dr. Ahmed can't teach Tuesday after 2",
        "example_ar": "د. أحمد ما يقدر الثلاثاء بعد ٢",
    },
    "instructor_max_daily": {
        "group": "times", "kind": "hard", "setup": True,
        "name_en": "Instructor daily maximum", "name_ar": "حد يومي للمدرّس",
        "example_en": "Dr. Sarah Alqahtani teaches at most 3 classes a day",
        "example_ar": "د. سارة القحطاني ما تدرّس أكثر من ٣ محاضرات في اليوم",
    },
    "section_avoid_slots": {
        "group": "times", "kind": "hard", "setup": False,
        "name_en": "Section avoids hours", "name_ar": "شعبة تتجنّب أوقاتًا",
        "example_en": "Keep section S17 out of Thursday afternoon",
        "example_ar": "لا تحطون شعبة S16 يوم الأحد الصباح",
    },
    "room_closed": {
        "group": "rooms", "kind": "hard", "setup": False,
        "name_en": "Close a room", "name_ar": "إغلاق قاعة",
        "example_en": "Close room B12",
        "example_ar": "سكّروا القاعة B12",
    },
    "section_require_accessible": {
        "group": "rooms", "kind": "hard", "setup": False,
        "name_en": "Accessible room", "name_ar": "قاعة مهيأة",
        "example_en": "Section S20 must be in an accessible room",
        "example_ar": "شعبة S18 لازم تكون في قاعة مهيأة",
    },
    "course_needs_lab": {
        "group": "rooms", "kind": "hard", "setup": False,
        "name_en": "Course needs a lab", "name_ar": "مقرر يحتاج معمل",
        "example_en": "Networks needs a lab",
        "example_ar": "مادة الشبكات تحتاج معمل",
    },
    "avoid_single_class_days": {
        "group": "students", "kind": "preference", "setup": True,
        "name_en": "Fewer single-class days", "name_ar": "أيام بمحاضرة واحدة أقل",
        "example_en": "Avoid days where a student comes in for only one class",
        "example_ar": "لا تخلّون الطالب يجي ليوم فيه محاضرة وحدة",
    },
}

# questions, not rules: shown under "Ask" once there is a timetable
QUESTIONS = [
    {"name_en": "Why is there a gap?", "name_ar": "لماذا يوجد فراغ؟",
     "example_en": "Why does AR-L2 have a gap on Wednesday?",
     "example_ar": "ليش عند عمارة المستوى الثاني فراغ يوم الأربعاء؟"},
    {"name_en": "What if…", "name_ar": "ماذا لو…",
     "example_en": "What if we close room B12?",
     "example_ar": "وش يصير لو سكّرنا القاعة B12؟"},
]

# what the solver always enforces, whatever the administrator says
BUILTIN_RULES = [
    ("An instructor teaches one class at a time", "لا يدرّس المدرّس محاضرتين في الوقت نفسه"),
    ("A room holds one class at a time", "لا تُستخدم القاعة لمحاضرتين في الوقت نفسه"),
    ("A room seats at least the section's students", "سعة القاعة لا تقل عن عدد طلاب الشعبة"),
    ("A section's two meetings fall on different days", "محاضرتا الشعبة في يومين مختلفين"),
    ("Instructors' unavailable hours from the file", "أوقات عدم إتاحة المدرّسين كما في الملف"),
    ("Courses marked as needing a lab get a lab", "المقررات التي تحتاج معملًا تُدرَّس في معمل كما في الملف"),
    ("Students who need accessible rooms get them, with at most 6 minutes' walk "
     "between consecutive classes",
     "الطلاب الذين يحتاجون قاعات مهيأة يحصلون عليها، ولا يزيد المشي بين محاضرتين "
     "متتاليتين عن ٦ دقائق"),
]
GOALS = (
    "Always aimed for: fewer clashes, gaps, long walks, wasted seats and "
    "overloaded instructor days",
    "أهداف دائمة: تعارضات أقل، فراغات أقل، مشي أقل، مقاعد مهدرة أقل، وأيام أخف على المدرّسين",
)


def as_payload() -> dict:
    """Everything the page needs to draw step 2, the card tags and the menu."""
    return {
        "groups": {k: {"en": en, "ar": ar} for k, (en, ar) in GROUPS.items()},
        "kinds": {k: {"en": en, "ar": ar} for k, (en, ar) in KINDS.items()},
        "types": [{"type": t, **info} for t, info in RULE_TYPES.items()],
        "questions": QUESTIONS,
        "builtin": [{"en": en, "ar": ar} for en, ar in BUILTIN_RULES],
        "goals": {"en": GOALS[0], "ar": GOALS[1]},
    }


def unavailable_line() -> tuple[str, str]:
    """The line shown when a request matched no rule type: written here, never
    by the model."""
    en = ", ".join(info["name_en"] for info in RULE_TYPES.values())
    ar = "، ".join(info["name_ar"] for info in RULE_TYPES.values())
    return (
        f"This kind of rule is not available yet. Available rules: {en}.",
        f"هذا النوع غير متاح حاليًا. القواعد المتاحة: {ar}.",
    )
