"""The personas are only useful if the baseline really does fail them."""

from core.baseline import build_baseline
from core.metrics import student_conflicts, student_transits
from data.generator import PERSONAS, generate


def test_personas_exist_and_are_named():
    u = generate()
    for eid, (name, name_en, kind) in PERSONAS.items():
        who = u.student_by_id.get(eid) or u.instructor_by_id.get(eid)
        assert who is not None, f"{eid} is not in the university"
        assert who.name == name and who.name_en == name_en


def test_noura_has_accessibility_problems_in_the_baseline():
    u = generate()
    a = build_baseline(u)
    noura = u.student_by_id["ST049"]
    assert noura.needs_accessibility
    inaccessible = [
        m.id
        for sid in noura.section_ids
        for m in u.meetings_of_section[sid]
        if not u.room_by_id[a.room[m.id]].accessible
    ]
    assert inaccessible, "Noura must start with inaccessible rooms"
    assert max(student_transits(u, a, noura.id)) > 6, "and an over-limit transit"


def test_faisal_is_a_repeater_who_clashes_in_the_baseline():
    u = generate()
    a = build_baseline(u)
    faisal = u.student_by_id["ST054"]
    assert faisal.is_repeater
    assert student_conflicts(u, a, faisal.id) > 0, "Faisal must start with a clash"
    lower = [s for s in faisal.section_ids if u.section_by_id[s].level < faisal.level]
    assert len(lower) == 1, "his tag names one repeated course"
