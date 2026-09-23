"""Conventional greedy scheduler: the practice we are trying to beat.

It only avoids instructor clashes, room clashes and clashes inside a cohort,
and takes the first room that fits. Individual students (repeaters especially)
and accessibility are ignored.
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

    for sec in sections:
        used_days: set[int] = set()
        for m in u.meetings_of_section[sec.id]:
            placed = False
            for s in range(N_SLOTS):
                if slot_day(s) in used_days:
                    continue
                if busy_instructor.get((sec.instructor_id, s)):
                    continue
                if any(busy_cohort.get((c, s)) for c in u.serving_cohorts[sec.id]):
                    continue
                if s in u.instructor_by_id[sec.instructor_id].unavailable_slots:
                    continue
                for r in rooms:
                    if r.capacity < sec.enrollment:
                        continue
                    if busy_room.get((r.id, s)):
                        continue
                    slot[m.id] = s
                    room[m.id] = r.id
                    busy_instructor[(sec.instructor_id, s)] = True
                    busy_room[(r.id, s)] = True
                    for c in u.serving_cohorts[sec.id]:
                        busy_cohort[(c, s)] = True
                    used_days.add(slot_day(s))
                    placed = True
                    break
                if placed:
                    break
            if not placed:
                raise RuntimeError(f"baseline could not place {m.id}")
    return Assignment(slot, room)
