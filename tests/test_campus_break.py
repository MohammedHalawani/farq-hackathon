"""A campus break is nobody's gap. Without one, nothing may move."""

from api.state import Session
from core.baseline import build_baseline
from core.explain import explain_gap
from core.metrics import (
    break_slots,
    compute,
    student_day_meetings,
    student_idle_slots,
    student_longest_gap,
)
from core.models import (
    N_DAYS,
    Assignment,
    Building,
    Course,
    Instructor,
    Meeting,
    Room,
    Section,
    Student,
    University,
    slot_id,
)
from core.solver import solve
from data.generator import generate

NOON = {"type": "campus_break", "days": [0, 1, 2, 3, 4], "slots": [4]}

# compute(generate(), build_baseline(...)) on main, before breaks existed
MAIN_BASELINE = {
    "access_avg_transit_minutes": 6.91, "access_max_transit_minutes": 12,
    "accessibility_violations": 40, "avg_idle_minutes_per_student_per_day": 31.2,
    "avg_room_fill_rate": 0.789, "avg_walk_minutes": 5.49,
    "idle_by_cohort": {
        "AR-L1": 24.0, "AR-L2": 34.6, "AR-L3": 36.5, "AR-L4": 56.0,
        "BA-L1": 0.0, "BA-L2": 32.2, "BA-L3": 48.6, "BA-L4": 48.0,
        "CE-L1": 24.0, "CE-L2": 13.1, "CE-L3": 71.4, "CE-L4": 2.8,
        "CS-L1": 24.0, "CS-L2": 14.5, "CS-L3": 57.3, "CS-L4": 13.4,
    },
    "instructor_load_std": 0.34, "instructor_max_daily": 4,
    "pct_repeaters_conflict_free": 54.1, "pct_students_conflict_free": 94.3,
    "pct_students_with_2h_gap": 44.0, "pct_students_with_any_gap": 88.7,
    "total_student_conflicts": 38, "worst_gap_hours": 3,
}


def _scalars(m: dict) -> dict:
    return {k: v for k, v in m.items() if k != "accessibility_violation_detail"}


# --- no break: byte-identical -------------------------------------------------


def test_no_break_metrics_match_main():
    u = generate()
    a = build_baseline(u)
    assert _scalars(compute(u, a)) == MAIN_BASELINE
    other_rules = [{"type": "room_closed", "room_id": "B12"},
                   {"type": "instructor_max_daily", "instructor_id": "I01", "max_classes": 3}]
    assert compute(u, a, []) == compute(u, a) == compute(u, a, other_rules)


def test_no_break_cache_entries_unchanged():
    # the names the demo campus was cached under before breaks stopped counting
    s = Session()
    assert {p: s._cache_path(p).name for p in ("balanced", "room_efficient",
                                               "student_friendly")} == {
        "balanced": "balanced-c9be9df9df5343bd.json",
        "room_efficient": "room_efficient-2fc4cc2bd1147f90.json",
        "student_friendly": "student_friendly-b8e4fd3f201f4ebd.json",
    }


# --- break at 12:00 -------------------------------------------------------------


def _one_student_campus() -> University:
    """One student, three sections, classes Sunday 11:00 and 13:00."""
    courses = [Course(f"C{i}", f"Course {i}", f"مقرر {i}", "CS", 1) for i in (1, 2)]
    sections = [Section(f"S{i}", f"C{i}", "I1", 10, "CS", 1) for i in (1, 2)]
    return University(
        buildings=[Building("B1", "B1", "B1")],
        rooms=[Room("R1", "B1", 40, True)],
        instructors=[Instructor("I1", "د. واحد")],
        courses=courses,
        sections=sections,
        meetings=[Meeting(f"S{i}-m{k + 1}", f"S{i}", k) for i in (1, 2) for k in (0, 1)],
        students=[Student("ST1", "طالب", "CS", 1, ["S1", "S2"])],
        walk={("B1", "B1"): 0},
    )


def test_class_at_11_and_13_with_a_break_at_12_is_no_gap():
    u = _one_student_campus()
    a = Assignment(
        slot={"S1-m1": slot_id(0, 3), "S2-m1": slot_id(0, 5),   # Sunday 11:00, 13:00
              "S1-m2": slot_id(1, 0), "S2-m2": slot_id(2, 0)},
        room={m: "R1" for m in ("S1-m1", "S1-m2", "S2-m1", "S2-m2")},
    )
    assert student_idle_slots(u, a, "ST1") == 1           # without a break: a gap
    breaks = break_slots([NOON])
    assert student_idle_slots(u, a, "ST1", breaks) == 0
    assert student_longest_gap(u, a, "ST1", breaks) == 0
    m = compute(u, a, [NOON])
    assert m["pct_students_with_any_gap"] == 0
    assert m["avg_idle_minutes_per_student_per_day"] == 0
    out = explain_gap(u, a, [NOON], "ST1", 0)
    assert out["gap_hours"] == [] and "campus break" in out["note"]


def _idle_by_hand(u, a, sid, breaks) -> int:
    """Empty hours between the first and last class, skipping break hours."""
    total = 0
    for day, ms in student_day_meetings(u, a, sid).items():
        periods = {p for p, _, _ in ms}
        if len(periods) < 2:
            continue
        total += sum(
            1 for p in range(min(periods), max(periods) + 1)
            if p not in periods and slot_id(day, p) not in breaks
        )
    return total


def test_break_hour_is_never_idle_for_any_student():
    u = generate()
    breaks = break_slots([NOON])
    assert breaks == {slot_id(d, 4) for d in range(N_DAYS)}
    # the baseline ignores the break, so some students have class at 12:00 and
    # some sit through an empty 12:00; the break-aware solve keeps it empty
    base = build_baseline(u)
    built = solve(u, "balanced", constraints=[NOON], rounds=0).assignment
    for a in (base, built):
        for st in u.students:
            assert student_idle_slots(u, a, st.id, breaks) == _idle_by_hand(u, a, st.id, breaks)
    assert all(s % 8 != 4 for s in built.slot.values())
    empties_at_noon = sum(
        _idle_by_hand(u, base, st.id, frozenset()) - _idle_by_hand(u, base, st.id, breaks)
        for st in u.students
    )
    assert empties_at_noon > 0, "the baseline must have students idle at 12:00 to test this"
    assert compute(u, base, [NOON])["avg_idle_minutes_per_student_per_day"] < \
        compute(u, base)["avg_idle_minutes_per_student_per_day"]


def test_break_only_on_named_days():
    thursday = {"type": "campus_break", "days": [4], "slots": [6, 7]}
    assert break_slots([thursday]) == {slot_id(4, 6), slot_id(4, 7)}
    assert break_slots([{"type": "room_closed", "room_id": "B12"}]) == frozenset()


# --- the baseline keeps the break free ----------------------------------------

# sha256 of the demo baseline's (slot, room) on main
MAIN_BASELINE_HASH = "48b4bc3af8fabca34e03ddcc6f9374d68298d4e6426220d048ec49e49aa801bb"


def _fingerprint(a: Assignment) -> str:
    import hashlib
    import json

    return hashlib.sha256(
        json.dumps([sorted(a.slot.items()), sorted(a.room.items())]).encode()
    ).hexdigest()


def test_baseline_without_a_break_is_byte_identical_to_main():
    u = generate()
    assert _fingerprint(build_baseline(u)) == MAIN_BASELINE_HASH
    assert _fingerprint(build_baseline(u, [])) == MAIN_BASELINE_HASH
    assert _fingerprint(build_baseline(u, [{"type": "room_closed", "room_id": "B12"}])) \
        == MAIN_BASELINE_HASH


def test_baseline_never_uses_a_break_slot():
    u = generate()
    thursday = {"type": "campus_break", "days": [4], "slots": [6, 7]}
    for rule in (NOON, thursday):
        a = build_baseline(u, [rule])
        assert not set(a.slot.values()) & break_slots([rule])
        assert len(a.slot) == len(u.meetings)
