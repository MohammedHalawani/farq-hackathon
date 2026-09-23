"""Conventional greedy scheduler: the practice we are trying to beat.

It avoids instructor clashes, room clashes and clashes inside a cohort, and
tries — but does not insist — to stagger each level against the one below, the
way a registrar does so a student repeating a course has some chance of fitting
it in. It takes the first room that fits.

What it never does is look at an individual student. The stagger works for about
half the repeaters and silently fails for the rest, and accessibility is ignored
entirely.
"""

from __future__ import annotations

from core.models import N_SLOTS, Assignment, University, slot_day


def build_baseline(u: University) -> Assignment:
    slot: dict[str, int] = {}
    room: dict[str, str] = {}

    busy_instructor: dict[tuple[str, int], bool] = {}
    busy_room: dict[tuple[str, int], bool] = {}
    busy_cohort: dict[tuple[str, int], bool] = {}

    rooms = sorted(u.rooms, key=lambda r: (r.capacity, r.id))
    sections = sorted(u.sections, key=lambda s: (-s.enrollment, s.id))

    def level_below(section_id: str) -> set[str]:
        """The level under each cohort this section serves. A registrar staggers
        against it so a repeater can fit the course they are retaking."""
        out: set[str] = set()
        for cohort in u.serving_cohorts[section_id]:
            dept, level = cohort.split("-L")
            if int(level) > 1:
                out.add(f"{dept}-L{int(level) - 1}")
        return out

    for sec in sections:
        used_days: set[int] = set()
        near = level_below(sec.id)
        for m in u.meetings_of_section[sec.id]:
            # first pass keeps the level below clear; the second gives that up
            spot = _first_fit(u, sec, rooms, used_days, busy_instructor,
                              busy_room, busy_cohort, near)
            if spot is None:
                spot = _first_fit(u, sec, rooms, used_days, busy_instructor,
                                  busy_room, busy_cohort, set())
            if spot is None:
                raise RuntimeError(f"baseline could not place {m.id}")
            s, r = spot
            slot[m.id], room[m.id] = s, r
            busy_instructor[(sec.instructor_id, s)] = True
            busy_room[(r, s)] = True
            for c in u.serving_cohorts[sec.id]:
                busy_cohort[(c, s)] = True
            used_days.add(slot_day(s))

    return Assignment(slot, room)


def _first_fit(u, sec, rooms, used_days, busy_instructor, busy_room, busy_cohort, near):
    for s in range(N_SLOTS):
        if slot_day(s) in used_days:
            continue
        if busy_instructor.get((sec.instructor_id, s)):
            continue
        if s in u.instructor_by_id[sec.instructor_id].unavailable_slots:
            continue
        if any(busy_cohort.get((c, s)) for c in u.serving_cohorts[sec.id]):
            continue
        if any(busy_cohort.get((c, s)) for c in near):
            continue
        for r in rooms:
            if r.capacity >= sec.enrollment and not busy_room.get((r.id, s)):
                return s, r.id
    return None
