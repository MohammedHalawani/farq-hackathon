from __future__ import annotations

from typing import Literal, Union

from pydantic import BaseModel, Field, field_validator

from core.models import N_DAYS, N_PERIODS


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

    _d = field_validator("days")(_check_days)
    _s = field_validator("slots")(_check_slots_or_all)


class SectionAvoidSlots(BaseModel, extra="forbid"):
    type: Literal["section_avoid_slots"]
    section_id: str
    days: list[int] = Field(min_length=1)
    slots: list[int] = Field(min_length=1)

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


CONSTRAINTS = {
    "instructor_unavailable": InstructorUnavailable,
    "section_avoid_slots": SectionAvoidSlots,
    "room_closed": RoomClosed,
    "instructor_max_daily": InstructorMaxDaily,
    "section_require_accessible": SectionRequireAccessible,
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
        "days": {
            "type": "array",
            "items": {"type": "integer"},
            "description": "0=Sunday 1=Monday 2=Tuesday 3=Wednesday 4=Thursday",
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
