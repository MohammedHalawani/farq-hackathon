from __future__ import annotations

from typing import Literal, Union

import re

from pydantic import BaseModel, Field, field_validator, model_validator

from core.models import DAYS, DAYS_AR, N_DAYS, N_PERIODS


def _fold(word: str) -> str:
    """Case, the article and hamza variants out of the way: "الإثنين",
    "الاثنين" and "اثنين" all fold to the same key."""
    w = word.strip().lower().translate(str.maketrans("٠١٢٣٤٥٦٧٨٩", "0123456789"))
    w = re.sub("[إأآا]", "ا", w)
    return w[2:] if w.startswith("ال") and len(w) > 3 else w


DAY_NAMES: dict[str, int] = {}
for _i, (_en, _ar) in enumerate(zip(DAYS, DAYS_AR)):
    for _name in (_en, _en[:3], _ar):
        DAY_NAMES[_fold(_name)] = _i


def to_day(v) -> int:
    """A day as the model or a person writes it -> 0..4. Integers pass through
    (range-checked later); names are looked up by code, never by the model."""
    if isinstance(v, bool):
        raise ValueError(f"'{v}' is not a day")
    if isinstance(v, int):
        return v
    if isinstance(v, float) and v.is_integer():
        return int(v)
    if isinstance(v, str):
        key = _fold(v)
        if key.lstrip("-").isdigit():
            return int(key)
        if key in DAY_NAMES:
            return DAY_NAMES[key]
    raise ValueError(
        f"'{v}' is not a teaching day. Use a day name: {', '.join(DAYS)}."
    )


def _to_days(v):
    """A single day or a list of them, as names or numbers."""
    if v is None:
        return v
    if not isinstance(v, (list, tuple)):
        v = [v]
    return [to_day(d) for d in v]


def _day_alias(raw):
    """`day` (one value or a list) is accepted as `days`."""
    if isinstance(raw, dict) and "day" in raw:
        raw = dict(raw)
        day = raw.pop("day")
        if "days" not in raw:
            raw["days"] = day
    return raw


def _check_days(v: list[int]) -> list[int]:
    for d in v:
        if not 0 <= d < N_DAYS:
            raise ValueError(f"day {d} is outside Sunday..Thursday (0..{N_DAYS - 1})")
    return sorted(set(v))


def _check_slots(v: "list[int] | Literal['all']") -> "list[int] | str":
    if v == "all":
        return v
    for s in v:
        if not 0 <= s < N_PERIODS:
            raise ValueError(f"slot {s} is outside 0..{N_PERIODS - 1} (08:00..15:00)")
    return sorted(set(v))


def _check_slots_or_all(v):
    """Instructor availability also accepts the whole day as "all"."""
    out = _check_slots(v)
    return "all" if out == list(range(N_PERIODS)) else out


class InstructorUnavailable(BaseModel, extra="forbid"):
    type: Literal["instructor_unavailable"]
    instructor_id: str
    days: list[int] = Field(min_length=1)
    slots: Union[Literal["all"], list[int]]

    _alias = model_validator(mode="before")(_day_alias)
    _names = field_validator("days", mode="before")(_to_days)
    _d = field_validator("days")(_check_days)
    _s = field_validator("slots")(_check_slots_or_all)


class SectionAvoidSlots(BaseModel, extra="forbid"):
    type: Literal["section_avoid_slots"]
    section_id: str
    days: list[int] = Field(min_length=1)
    slots: list[int] = Field(min_length=1)

    _alias = model_validator(mode="before")(_day_alias)
    _names = field_validator("days", mode="before")(_to_days)
    _d = field_validator("days")(_check_days)
    _s = field_validator("slots")(_check_slots)


class RoomClosed(BaseModel, extra="forbid"):
    type: Literal["room_closed"]
    room_id: str


class InstructorMaxDaily(BaseModel, extra="forbid"):
    type: Literal["instructor_max_daily"]
    instructor_id: str
    max_classes: int = Field(ge=1, le=8)


class SectionRequireAccessible(BaseModel, extra="forbid"):
    type: Literal["section_require_accessible"]
    section_id: str


def _check_days_or_all(v: list[int]) -> list[int]:
    """A campus break with no days named applies to every day."""
    return _check_days(v) if v else list(range(N_DAYS))


class CampusBreak(BaseModel, extra="forbid"):
    type: Literal["campus_break"]
    days: list[int] = Field(default_factory=lambda: list(range(N_DAYS)))
    slots: list[int] = Field(min_length=1)

    _alias = model_validator(mode="before")(_day_alias)
    _names = field_validator("days", mode="before")(_to_days)
    _d = field_validator("days")(_check_days_or_all)
    _s = field_validator("slots")(_check_slots)


class CourseNeedsLab(BaseModel, extra="forbid"):
    type: Literal["course_needs_lab"]
    course_id: str


CONSTRAINTS = {
    "instructor_unavailable": InstructorUnavailable,
    "section_avoid_slots": SectionAvoidSlots,
    "room_closed": RoomClosed,
    "instructor_max_daily": InstructorMaxDaily,
    "section_require_accessible": SectionRequireAccessible,
    "campus_break": CampusBreak,
    "course_needs_lab": CourseNeedsLab,
}


def parse_constraint(raw: dict) -> dict:
    """Validate against exactly one schema; anything else is rejected."""
    if not isinstance(raw, dict) or "type" not in raw:
        raise ValueError("A constraint needs a 'type' field.")
    model = CONSTRAINTS.get(raw["type"])
    if model is None:
        raise ValueError(
            f"Unknown constraint type '{raw['type']}'. "
            f"Allowed: {', '.join(sorted(CONSTRAINTS))}."
        )
    return model.model_validate(raw).model_dump()


CONSTRAINT_TOOL_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["type"],
    "properties": {
        "type": {"type": "string", "enum": sorted(CONSTRAINTS)},
        "instructor_id": {"type": "string", "description": "e.g. I01 (from get_entity)"},
        "section_id": {"type": "string", "description": "e.g. S12 (from get_entity)"},
        "room_id": {"type": "string", "description": "e.g. B12 (from get_entity)"},
        "course_id": {"type": "string", "description": "e.g. C04 (from get_entity)"},
        "days": {
            "type": "array",
            "items": {"type": "string"},
            "description": (
                "Day names: Sunday, Monday, Tuesday, Wednesday, Thursday "
                "(Arabic names are fine too). For campus_break, omit it to mean "
                "every day."
            ),
        },
        "slots": {
            "type": "array",
            "items": {"type": "integer"},
            "description": (
                "Hour indexes: 0=08:00, 1=09:00 ... 7=15:00. "
                "For a whole day use [0,1,2,3,4,5,6,7]."
            ),
        },
        "max_classes": {"type": "integer"},
    },
}
