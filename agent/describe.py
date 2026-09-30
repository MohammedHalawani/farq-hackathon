"""Plain-language rendering of a constraint, built in code so the card never
depends on the model's wording."""

from __future__ import annotations

from core.models import DAYS, DAYS_AR, FIRST_HOUR, N_DAYS, University


def _hours(slots) -> tuple[str, str]:
    if slots == "all":
        return "all day", "طوال اليوم"
    ps = sorted(slots)
    if ps == list(range(ps[0], ps[0] + len(ps))):
        start, end = FIRST_HOUR + ps[0], FIRST_HOUR + ps[-1] + 1
        return f"{start:02d}:00–{end:02d}:00", f"{start:02d}:00–{end:02d}:00"
    label = ", ".join(f"{FIRST_HOUR + p:02d}:00" for p in ps)
    return label, label


def _days(days) -> tuple[str, str]:
    return (
        ", ".join(DAYS[d] for d in sorted(days)),
        "، ".join(DAYS_AR[d] for d in sorted(days)),
    )


def describe(u: University, c: dict) -> dict:
    """-> {title_en, title_ar, rows:[{label_en,label_ar,value}]}"""
    t = c["type"]
    if t == "instructor_unavailable":
        name = u.instructor_by_id[c["instructor_id"]].name
        d_en, d_ar = _days(c["days"])
        h_en, h_ar = _hours(c["slots"])
        return {
            "title_en": "Instructor unavailable",
            "title_ar": "المدرّس غير متاح",
            "rows": [
                {"label_en": "Instructor", "label_ar": "المدرّس", "value": name},
                {"label_en": "Days", "label_ar": "الأيام", "value": d_en, "value_ar": d_ar},
                {"label_en": "Hours", "label_ar": "الساعات", "value": h_en, "value_ar": h_ar},
            ],
        }
    if t == "section_avoid_slots":
        sec = u.section_by_id[c["section_id"]]
        course = u.course_by_id[sec.course_id]
        d_en, d_ar = _days(c["days"])
        h_en, h_ar = _hours(c["slots"])
        return {
            "title_en": "Section avoids these hours",
            "title_ar": "الشعبة تتجنّب هذه الساعات",
            "rows": [
                {"label_en": "Section", "label_ar": "الشعبة",
                 "value": f"{sec.id} — {course.name}", "value_ar": f"{sec.id} — {course.name_ar}"},
                {"label_en": "Days", "label_ar": "الأيام", "value": d_en, "value_ar": d_ar},
                {"label_en": "Hours", "label_ar": "الساعات", "value": h_en, "value_ar": h_ar},
            ],
        }
    if t == "room_closed":
        r = u.room_by_id[c["room_id"]]
        return {
            "title_en": "Room closed",
            "title_ar": "إغلاق قاعة",
            "rows": [
                {"label_en": "Room", "label_ar": "القاعة", "value": r.id},
                {"label_en": "Capacity", "label_ar": "السعة", "value": str(r.capacity)},
                {"label_en": "Accessible", "label_ar": "مهيّأة للوصول",
                 "value": "yes" if r.accessible else "no",
                 "value_ar": "نعم" if r.accessible else "لا"},
            ],
        }
    if t == "instructor_max_daily":
        name = u.instructor_by_id[c["instructor_id"]].name
        return {
            "title_en": "Daily teaching cap",
            "title_ar": "حد أقصى يومي",
            "rows": [
                {"label_en": "Instructor", "label_ar": "المدرّس", "value": name},
                {"label_en": "Max classes per day", "label_ar": "أقصى عدد حصص يوميًا",
                 "value": str(c["max_classes"])},
            ],
        }
    if t == "campus_break":
        d_en, d_ar = _days(c.get("days") or range(N_DAYS))
        if len(c.get("days") or range(N_DAYS)) == N_DAYS:
            d_en, d_ar = "every day", "كل الأيام"
        h_en, h_ar = _hours(c["slots"])
        return {
            "title_en": "Campus break — no classes for anyone",
            "title_ar": "استراحة عامة — لا محاضرات لأي أحد",
            "rows": [
                {"label_en": "Days", "label_ar": "الأيام", "value": d_en, "value_ar": d_ar},
                {"label_en": "Hours", "label_ar": "الساعات", "value": h_en, "value_ar": h_ar},
            ],
        }
    if t == "course_needs_lab":
        course = u.course_by_id[c["course_id"]]
        n_sec = sum(1 for s in u.sections if s.course_id == course.id)
        labs = sum(1 for r in u.rooms if r.kind == "lab")
        return {
            "title_en": "Course is taught in a lab",
            "title_ar": "المقرر يُدرَّس في معمل",
            "rows": [
                {"label_en": "Course", "label_ar": "المقرر",
                 "value": f"{course.id} — {course.name}",
                 "value_ar": f"{course.id} — {course.name_ar}"},
                {"label_en": "Sections", "label_ar": "الشعب", "value": str(n_sec)},
                {"label_en": "Labs on campus", "label_ar": "المعامل المتاحة",
                 "value": str(labs)},
            ],
        }
    sec = u.section_by_id[c["section_id"]]
    course = u.course_by_id[sec.course_id]
    return {
        "title_en": "Section needs an accessible room",
        "title_ar": "الشعبة تحتاج قاعة مهيّأة",
        "rows": [
            {"label_en": "Section", "label_ar": "الشعبة",
             "value": f"{sec.id} — {course.name}", "value_ar": f"{sec.id} — {course.name_ar}"},
        ],
    }


def short_label(u: University, c: dict) -> str:
    d = describe(u, c)
    return d["title_en"] + " — " + " · ".join(r["value"] for r in d["rows"])
