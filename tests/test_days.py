"""Days are converted by code: the model writes a name, never a number."""

import pytest

from agent.schemas import parse_constraint, to_day

SPELLINGS = {
    0: ["Sunday", "sunday", "SUNDAY", "Sun", "sun", "الأحد", "الاحد", "أحد", "احد"],
    1: ["Monday", "monday", "MONDAY", "Mon", "mon", "الاثنين", "الإثنين", "اثنين", "إثنين"],
    2: ["Tuesday", "tuesday", "TUESDAY", "Tue", "tue", "الثلاثاء", "ثلاثاء"],
    3: ["Wednesday", "wednesday", "WEDNESDAY", "Wed", "wed", "الأربعاء", "الاربعاء",
        "أربعاء", "اربعاء"],
    4: ["Thursday", "thursday", "THURSDAY", "Thu", "thu", "الخميس", "خميس"],
}


@pytest.mark.parametrize("day,name", [(d, n) for d, ns in SPELLINGS.items() for n in ns])
def test_every_spelling(day, name):
    assert to_day(name) == day
    assert to_day(f"  {name} ") == day


@pytest.mark.parametrize("value,day", [(0, 0), (4, 4), ("3", 3), ("٣", 3), (2.0, 2)])
def test_numbers_still_pass(value, day):
    assert to_day(value) == day


@pytest.mark.parametrize("bad", ["Friday", "الجمعة", "Saturday", "السبت", "tomorrow", "", True])
def test_not_a_teaching_day(bad):
    with pytest.raises(ValueError):
        to_day(bad)


def _unavailable(**days):
    return {"type": "instructor_unavailable", "instructor_id": "I05", "slots": [0, 1], **days}


@pytest.mark.parametrize("given", [
    {"days": ["Wednesday"]}, {"days": ["الأربعاء"]}, {"days": [3]}, {"days": "Wednesday"},
    {"day": "Wednesday"}, {"day": 3}, {"day": ["الاربعاء"]}, {"day": "wed"},
])
def test_constraint_days_are_normalised(given):
    assert parse_constraint(_unavailable(**given))["days"] == [3]


def test_names_and_numbers_mix_and_deduplicate():
    c = parse_constraint(_unavailable(days=["Thursday", "الأحد", 0, "thu"]))
    assert c["days"] == [0, 4]


def test_day_alias_on_every_constraint_with_days():
    avoid = {"type": "section_avoid_slots", "section_id": "S16", "day": "الأحد",
             "slots": [0, 1, 2, 3]}
    brk = {"type": "campus_break", "day": ["Thursday"], "slots": [6, 7]}
    assert parse_constraint(avoid)["days"] == [0]
    assert parse_constraint(brk)["days"] == [4]
    # `days` wins when both are given
    assert parse_constraint(_unavailable(days=["Monday"], day="Friday"))["days"] == [1]


def test_campus_break_without_days_is_every_day():
    assert parse_constraint({"type": "campus_break", "slots": [4]})["days"] == [0, 1, 2, 3, 4]


def test_a_weekend_day_is_rejected():
    with pytest.raises(ValueError):
        parse_constraint(_unavailable(days=["Friday"]))


def test_explain_gap_takes_a_day_name():
    from types import SimpleNamespace

    from agent.agent import Tools
    from core.baseline import build_baseline
    from data.generator import generate

    u = generate()
    t = Tools(SimpleNamespace(u=u, current=build_baseline(u), constraints=[]))
    out = t.run("explain_gap", {"entity_id": "CS-L3", "day": "الأربعاء"})
    assert t.calls[-1][1]["day"] == 3 and out["day"] == "Wednesday"
    assert "error" in t.run("explain_gap", {"entity_id": "CS-L3", "day": "Friday"})
