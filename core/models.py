from __future__ import annotations

from dataclasses import dataclass, field

DAYS = ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday"]
DAYS_AR = ["الأحد", "الاثنين", "الثلاثاء", "الأربعاء", "الخميس"]
N_DAYS = 5
N_PERIODS = 8
FIRST_HOUR = 8
N_SLOTS = N_DAYS * N_PERIODS


def slot_id(day: int, period: int) -> int:
    return day * N_PERIODS + period


def slot_day(s: int) -> int:
    return s // N_PERIODS


def slot_period(s: int) -> int:
    return s % N_PERIODS


def slot_label(s: int) -> str:
    return f"{DAYS[slot_day(s)]} {FIRST_HOUR + slot_period(s):02d}:00"


@dataclass
class Building:
    id: str
    name: str
    name_ar: str


@dataclass
class Room:
    id: str
    building_id: str
    capacity: int
    accessible: bool

    @property
    def floor(self) -> int | None:
        """Read off the room number: B1-201 is on floor 2. None when the id
        does not carry one."""
        _, _, number = self.id.partition("-")
        return int(number[0]) if number[:1].isdigit() else None


@dataclass
class Instructor:
    id: str
    name: str
    name_en: str = ""
    unavailable_slots: set[int] = field(default_factory=set)


@dataclass
class Course:
    id: str
    name: str
    name_ar: str
    department: str
    level: int


@dataclass
class Section:
    id: str
    course_id: str
    instructor_id: str
    enrollment: int
    department: str
    level: int

    @property
    def cohort(self) -> str:
        return f"{self.department}-L{self.level}"


@dataclass
class Meeting:
    id: str
    section_id: str
    index: int


@dataclass
class Student:
    id: str
    name: str
    department: str
    level: int
    section_ids: list[str]
    needs_accessibility: bool = False
    is_repeater: bool = False
    name_en: str = ""
    persona: str = ""


@dataclass
class University:
    buildings: list[Building]
    rooms: list[Room]
    instructors: list[Instructor]
    courses: list[Course]
    sections: list[Section]
    meetings: list[Meeting]
    students: list[Student]
    walk: dict[tuple[str, str], int]
    serving_cohorts: dict[str, set[str]] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.room_by_id = {r.id: r for r in self.rooms}
        self.instructor_by_id = {i.id: i for i in self.instructors}
        self.course_by_id = {c.id: c for c in self.courses}
        self.section_by_id = {s.id: s for s in self.sections}
        self.meeting_by_id = {m.id: m for m in self.meetings}
        self.student_by_id = {s.id: s for s in self.students}
        self.meetings_of_section = {s.id: [] for s in self.sections}
        for m in self.meetings:
            self.meetings_of_section[m.section_id].append(m)
        self.students_of_section: dict[str, list[str]] = {s.id: [] for s in self.sections}
        for st in self.students:
            for sid in st.section_ids:
                self.students_of_section[sid].append(st.id)
        if not self.serving_cohorts:
            self.serving_cohorts = {s.id: {s.cohort} for s in self.sections}

    def walk_minutes(self, room_a: str, room_b: str) -> int:
        ba = self.room_by_id[room_a].building_id
        bb = self.room_by_id[room_b].building_id
        return self.walk[(ba, bb)]

    def sections_needing_accessible(self) -> set[str]:
        out = set()
        for st in self.students:
            if st.needs_accessibility:
                out.update(st.section_ids)
        return out

    @property
    def cohorts(self) -> list[str]:
        return sorted({s.cohort for s in self.sections})


@dataclass
class Assignment:
    """slot and room per meeting id."""

    slot: dict[str, int]
    room: dict[str, str]

    def copy(self) -> "Assignment":
        return Assignment(dict(self.slot), dict(self.room))
