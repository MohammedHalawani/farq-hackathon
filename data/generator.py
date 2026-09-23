from __future__ import annotations

import random

from core.models import (
    N_SLOTS,
    Building,
    Course,
    Instructor,
    Meeting,
    Room,
    Section,
    Student,
    University,
)

SEED = 20260923

BUILDINGS = [
    ("B1", "Main Hall", "المبنى الرئيسي"),
    ("B2", "Science Block", "مبنى العلوم"),
    ("B3", "Engineering Block", "مبنى الهندسة"),
    ("B4", "Business Block", "مبنى إدارة الأعمال"),
    ("B5", "Design Studio", "مبنى التصميم"),
]

WALK = {
    ("B1", "B2"): 4, ("B1", "B3"): 7, ("B1", "B4"): 10, ("B1", "B5"): 12,
    ("B2", "B3"): 5, ("B2", "B4"): 9, ("B2", "B5"): 11,
    ("B3", "B4"): 6, ("B3", "B5"): 8,
    ("B4", "B5"): 3,
}

# (id, building, capacity, accessible)
ROOMS = [
    ("B1-101", "B1", 40, True),
    ("B1-102", "B1", 60, True),
    ("B1-103", "B1", 35, True),
    ("B1-201", "B1", 90, False),
    ("B1-202", "B1", 45, False),
    ("B2-101", "B2", 50, True),
    ("B2-102", "B2", 30, True),
    ("B2-201", "B2", 120, False),
    ("B2-202", "B2", 25, False),
    ("B3-101", "B3", 55, True),
    ("B3-201", "B3", 70, False),
    ("B3-202", "B3", 40, False),
    ("B3-203", "B3", 30, False),
    ("B4-101", "B4", 45, True),
    ("B4-201", "B4", 80, False),
    ("B4-202", "B4", 35, False),
    ("B5-101", "B5", 60, False),
    ("B5-102", "B5", 28, False),
    ("B5-201", "B5", 100, False),
    ("B12", "B5", 25, False),
]

DEPARTMENTS = [
    ("CS", "Computer Science", "علوم الحاسب"),
    ("CE", "Civil Engineering", "الهندسة المدنية"),
    ("BA", "Business", "إدارة الأعمال"),
    ("AR", "Architecture", "العمارة"),
]
DEPT_NAME_AR = {d[0]: d[2] for d in DEPARTMENTS}
DEPT_NAME_EN = {d[0]: d[1] for d in DEPARTMENTS}

INSTRUCTOR_NAMES = [
    "د. أحمد العلي",
    "د. أحمد الغامدي",
    "د. سارة القحطاني",
    "د. خالد الشمري",
    "د. نورة الحربي",
    "د. فهد العتيبي",
    "د. منى الزهراني",
    "د. عبدالله الدوسري",
    "د. ريم المالكي",
    "د. ياسر السبيعي",
    "د. هند الرشيد",
    "د. ماجد البقمي",
    "د. لطيفة العنزي",
    "د. سلطان الجهني",
    "د. عائشة المطيري",
]

INSTRUCTOR_NAMES_EN = [
    "Dr. Ahmed Alali",
    "Dr. Ahmed Alghamdi",
    "Dr. Sarah Alqahtani",
    "Dr. Khalid Alshamri",
    "Dr. Noura Alharbi",
    "Dr. Fahd Alotaibi",
    "Dr. Mona Alzahrani",
    "Dr. Abdullah Aldosari",
    "Dr. Reem Almalki",
    "Dr. Yasser Alsubaie",
    "Dr. Hind Alrasheed",
    "Dr. Majed Albogami",
    "Dr. Latifa Alanazi",
    "Dr. Sultan Aljehani",
    "Dr. Aisha Almutairi",
]

COURSE_WORDS = {
    "CS": [("Programming", "البرمجة"), ("Data Structures", "هياكل البيانات"),
           ("Databases", "قواعد البيانات"), ("Networks", "الشبكات"),
           ("Operating Systems", "نظم التشغيل"), ("Algorithms", "الخوارزميات"),
           ("Software Engineering", "هندسة البرمجيات"), ("Machine Learning", "تعلم الآلة"),
           ("Computer Graphics", "رسوميات الحاسب"), ("Security", "أمن المعلومات")],
    "CE": [("Statics", "الاستاتيكا"), ("Surveying", "المساحة"),
           ("Concrete Design", "تصميم الخرسانة"), ("Soil Mechanics", "ميكانيكا التربة"),
           ("Hydraulics", "الهيدروليكا"), ("Structural Analysis", "تحليل الإنشاءات"),
           ("Transportation", "هندسة النقل"), ("Construction Management", "إدارة التشييد"),
           ("Steel Design", "تصميم المنشآت المعدنية"), ("Environmental Eng", "الهندسة البيئية")],
    "BA": [("Accounting", "المحاسبة"), ("Microeconomics", "الاقتصاد الجزئي"),
           ("Marketing", "التسويق"), ("Finance", "التمويل"),
           ("Operations", "إدارة العمليات"), ("Organizational Behavior", "السلوك التنظيمي"),
           ("Business Law", "القانون التجاري"), ("Strategy", "الإدارة الاستراتيجية"),
           ("Statistics", "الإحصاء"), ("Entrepreneurship", "ريادة الأعمال")],
    "AR": [("Design Studio I", "استوديو التصميم ١"), ("Architectural History", "تاريخ العمارة"),
           ("Building Materials", "مواد البناء"), ("Urban Design", "التصميم العمراني"),
           ("Visual Communication", "التواصل البصري"), ("Landscape", "تنسيق المواقع"),
           ("Digital Fabrication", "التصنيع الرقمي"), ("Housing", "الإسكان"),
           ("Conservation", "الحفاظ المعماري"), ("Professional Practice", "الممارسة المهنية")],
}

FIRST_NAMES_AR = ["محمد", "عبدالرحمن", "فاطمة", "نوف", "سلمان", "دانة", "تركي", "جواهر",
                  "بندر", "شهد", "راكان", "لمى", "مشعل", "غادة", "أنس", "رهف"]
LAST_NAMES_AR = ["الحربي", "القحطاني", "الشهري", "العتيبي", "الدوسري", "الزهراني",
                 "المالكي", "السبيعي", "الغامدي", "البقمي", "العنزي", "المطيري"]


def build_walk_matrix() -> dict[tuple[str, str], int]:
    walk: dict[tuple[str, str], int] = {}
    ids = [b[0] for b in BUILDINGS]
    for a in ids:
        for b in ids:
            if a == b:
                walk[(a, b)] = 0
            else:
                walk[(a, b)] = WALK.get((a, b)) or WALK[(b, a)]
    return walk


def curriculum_indices(level: int) -> list[int]:
    start = min((level - 1) * 2, 5)
    return list(range(start, start + 5))


def generate(seed: int = SEED) -> University:
    rng = random.Random(seed)

    buildings = [Building(i, n, na) for i, n, na in BUILDINGS]
    rooms = [Room(i, b, c, a) for i, b, c, a in ROOMS]

    # 10 courses per department; consecutive levels share part of the curriculum.
    courses: list[Course] = []
    dept_courses: dict[str, list[Course]] = {}
    for dept, _, _ in DEPARTMENTS:
        dept_courses[dept] = []
        for idx, (en, ar) in enumerate(COURSE_WORDS[dept]):
            level = min(idx // 2 + 1, 4)
            c = Course(f"C{len(courses) + 1:02d}", en, ar, dept, level)
            courses.append(c)
            dept_courses[dept].append(c)

    def curriculum(dept: str, level: int) -> list[Course]:
        return [dept_courses[dept][i] for i in curriculum_indices(level)]

    shared_count: dict[str, int] = {c.id: 0 for c in courses}
    for dept, _, _ in DEPARTMENTS:
        for level in (1, 2, 3, 4):
            for c in curriculum(dept, level):
                shared_count[c.id] += 1

    # 60 sections: the 5 most-shared courses per department get a second section.
    doubled: set[str] = set()
    for dept, _, _ in DEPARTMENTS:
        ranked = sorted(dept_courses[dept], key=lambda c: (-shared_count[c.id], c.id))
        doubled.update(c.id for c in ranked[:5])

    instructors = [
        Instructor(f"I{i + 1:02d}", n, INSTRUCTOR_NAMES_EN[i])
        for i, n in enumerate(INSTRUCTOR_NAMES)
    ]

    sections: list[Section] = []
    sections_of_course: dict[str, list[Section]] = {}
    for c in courses:
        sections_of_course[c.id] = []
        for _ in range(2 if c.id in doubled else 1):
            sec = Section(f"S{len(sections) + 1:02d}", c.id, "", 0, c.department, c.level)
            sections.append(sec)
            sections_of_course[c.id].append(sec)

    order = list(range(len(sections)))
    rng.shuffle(order)
    for pos, idx in enumerate(order):
        sections[idx].instructor_id = instructors[pos % len(instructors)].id

    for inst in instructors:
        inst.unavailable_slots = set(rng.sample(range(N_SLOTS), rng.randint(3, 6)))

    meetings = [Meeting(f"{s.id}-m{k + 1}", s.id, k) for s in sections for k in range(2)]

    cohort_list = [(d[0], lv) for d in DEPARTMENTS for lv in (1, 2, 3, 4)]

    def section_for(dept: str, level: int, course: Course) -> Section:
        """A cohort always uses the same section of a course."""
        opts = sections_of_course[course.id]
        return opts[cohort_list.index((dept, level)) % len(opts)]

    # ~3% accessibility needs, concentrated in CE-L2 and AR-L3 for a legible demo.
    students: list[Student] = []
    n_students = 300
    access_ids = set(rng.sample(range(n_students), 9))
    repeater_ids = set(rng.sample(range(n_students), int(n_students * 0.15)))

    for i in range(n_students):
        dept = DEPARTMENTS[i % 4][0]
        level = (i // 4) % 4 + 1
        if i in access_ids:
            dept, level = ("CE", 2) if i % 2 == 0 else ("AR", 3)
        own = curriculum(dept, level)
        is_repeater = i in repeater_ids and level > 1
        picked: list[str] = []
        if is_repeater:
            for c in rng.sample(own, 4):
                picked.append(section_for(dept, level, c).id)
            lower = [c for c in curriculum(dept, level - 1) if c not in own]
            for c in rng.sample(lower, min(rng.randint(1, 2), len(lower))):
                picked.append(section_for(dept, level - 1, c).id)
        else:
            for c in own:
                picked.append(section_for(dept, level, c).id)
        name = f"{rng.choice(FIRST_NAMES_AR)} {rng.choice(LAST_NAMES_AR)}"
        students.append(
            Student(
                id=f"ST{i + 1:03d}",
                name=name,
                department=dept,
                level=level,
                section_ids=picked,
                needs_accessibility=i in access_ids,
                is_repeater=is_repeater,
            )
        )

    counts_by_section: dict[str, int] = {}
    for st in students:
        for sid in st.section_ids:
            counts_by_section[sid] = counts_by_section.get(sid, 0) + 1
    for s in sections:
        s.enrollment = max(counts_by_section.get(s.id, 0), 8)

    u = University(
        buildings=buildings,
        rooms=rooms,
        instructors=instructors,
        courses=courses,
        sections=sections,
        meetings=meetings,
        students=students,
        walk=build_walk_matrix(),
    )
    # A section's serving cohorts: what a department timetable would block out.
    serving: dict[str, set[str]] = {s.id: set() for s in sections}
    for st in students:
        cohort = f"{st.department}-L{st.level}"
        for sid in st.section_ids:
            if not st.is_repeater or sid in [
                section_for(st.department, st.level, c).id
                for c in curriculum(st.department, st.level)
            ]:
                serving[sid].add(cohort)
    u.serving_cohorts = serving
    return u
