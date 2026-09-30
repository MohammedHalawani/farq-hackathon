from __future__ import annotations

from typing import Literal, Union

import re

from pydantic import BaseModel, Field, field_validator, model_validator

from core.models import DAYS, DAYS_AR, FIRST_HOUR, N_DAYS, N_PERIODS


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


DAY_START, DAY_END = FIRST_HOUR, FIRST_HOUR + N_PERIODS   # 08:00, 16:00

_CLOCK = re.compile(
    r"^(\d{1,2})(?:[:.٫](\d{2}))?\s*"
    r"(am|pm|a\.m\.|p\.m\.|ص|صباحا|صباحًا|م|مساء|مساءً|ظهرا|ظهرًا|عصرا|عصرًا)?$"
)
_PM = {"pm", "p.m.", "م", "مساء", "مساءً", "ظهرا", "ظهرًا", "عصرا", "عصرًا"}


def to_hour(v, what: str = "time") -> int:
    """A clock time as the model or a person writes it -> the hour, 8..16.
    "14:00", "14", "2pm", "٢ م" and "٢" are all 14: with no am/pm, 1..7 means
    the afternoon, since teaching starts at 08:00."""
    if isinstance(v, bool):
        raise ValueError(f"{what} '{v}' is not a time")
    if isinstance(v, (int, float)) and float(v).is_integer():
        text = str(int(v))
    elif isinstance(v, str):
        text = v.strip().lower().translate(str.maketrans("٠١٢٣٤٥٦٧٨٩", "0123456789"))
    else:
        raise ValueError(f"{what} '{v}' is not a time")
    m = _CLOCK.match(text)
    if not m:
        raise ValueError(f"{what} '{v}' is not a clock time; write it like \"14:00\"")
    h, minutes, mark = int(m.group(1)), m.group(2), m.group(3)
    if minutes not in (None, "00"):
        raise ValueError(f"{what} '{v}' is not on the hour; classes start on the hour")
    if mark in _PM and h < 12:
        h += 12
    elif mark is None and 1 <= h < DAY_START:
        h += 12
    if not DAY_START <= h <= DAY_END:
        raise ValueError(
            f"{what} '{v}' is outside the teaching day, "
            f"{DAY_START:02d}:00–{DAY_END:02d}:00"
        )
    return h


def _given(raw: dict, key: str) -> bool:
    return raw.get(key) not in (None, "", False)


def _hours_to_slots(raw: dict, whole_day) -> dict:
    """Clock times -> `slots`, by code. Exactly one of these shapes:
      at                       one hour: at 08:00 is 08:00-09:00
      from + to                that range
      to                       from the start of the day
      from + until_end_of_day  "after X": to the end of the day, said explicitly
    A `from` with nothing to end it is rejected rather than read as the end of
    the day. With no times and no `slots`, `whole_day` is used (None: the rule
    must name its hours)."""
    if not isinstance(raw, dict):
        return raw
    raw = dict(raw)
    has = {k: _given(raw, k) for k in ("at", "from", "to", "until_end_of_day")}
    for k in ("at", "from", "to", "until_end_of_day"):
        value = raw.pop(k, None)
        if has[k]:
            has[k] = value
    if has["at"]:
        if has["from"] or has["to"] or has["until_end_of_day"]:
            raise ValueError("use `at` alone for one hour, or `from` with `to` / "
                             "`until_end_of_day` for a range, not both")
        h = to_hour(has["at"], "at")
        if h >= DAY_END:
            raise ValueError(f"at {h:02d}:00 is when the teaching day ends; "
                             f"the last hour starts at {DAY_END - 1:02d}:00")
        raw["slots"] = [h - DAY_START]
        return raw
    if has["from"] or has["to"] or has["until_end_of_day"]:
        if has["until_end_of_day"] and has["to"]:
            raise ValueError("give `to` or `until_end_of_day`, not both")
        if has["until_end_of_day"] and not has["from"]:
            raise ValueError("`until_end_of_day` needs `from`, the hour it starts at")
        # a bad clock time is the more useful message, so check it first
        start = to_hour(has["from"], "from") if has["from"] else DAY_START
        end = to_hour(has["to"], "to") if has["to"] else DAY_END
        if has["from"] and not (has["to"] or has["until_end_of_day"]):
            raise ValueError(
                "`from` alone does not say how long: use `at` for that one hour "
                "(\"at 8\"), `to` for a range, or `until_end_of_day: true` for "
                "\"after\" (\"after 2\")"
            )
        if start >= DAY_END:
            raise ValueError(f"from {start:02d}:00 leaves no teaching hour before "
                             f"{DAY_END:02d}:00")
        if end <= start:
            raise ValueError(f"to {end:02d}:00 is not after from {start:02d}:00")
        raw["slots"] = list(range(start - DAY_START, end - DAY_START))
    elif "slots" not in raw:
        if whole_day is None:
            raise ValueError("say which hours: `at` for one hour, or `from` with `to` "
                             "or `until_end_of_day`")
        raw["slots"] = whole_day
    return raw


def _prepare(whole_day):
    def prepare(raw):
        return _hours_to_slots(_day_alias(raw), whole_day)
    return prepare


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

    _prep = model_validator(mode="before")(_prepare("all"))
    _names = field_validator("days", mode="before")(_to_days)
    _d = field_validator("days")(_check_days)
    _s = field_validator("slots")(_check_slots_or_all)


class SectionAvoidSlots(BaseModel, extra="forbid"):
    type: Literal["section_avoid_slots"]
    section_id: str
    days: list[int] = Field(min_length=1)
    slots: list[int] = Field(min_length=1)

    _prep = model_validator(mode="before")(_prepare(list(range(N_PERIODS))))
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

    _prep = model_validator(mode="before")(_prepare(None))
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
        "at": {
            "type": "string",
            "description": (
                'One single hour, 24-hour "HH:MM": "at 8" / «الساعة ٨» is "08:00" '
                "and means 08:00-09:00. Use it alone, without from/to."
            ),
        },
        "from": {
            "type": "string",
            "description": (
                'Start of a range, 24-hour "HH:MM", e.g. "14:00". Always pair it '
                "with `to`, or with until_end_of_day for \"after\"."
            ),
        },
        "to": {
            "type": "string",
            "description": (
                'End of a range, 24-hour "HH:MM", e.g. "13:00". Without `from` the '
                'range starts at 08:00 ("before 10" is to "10:00").'
            ),
        },
        "until_end_of_day": {
            "type": "boolean",
            "description": (
                'true for "after X" / «بعد X»: from `from` to the end of the '
                "teaching day (16:00)."
            ),
        },
        "max_classes": {"type": "integer"},
    },
}
