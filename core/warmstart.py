"""A hard-feasible greedy start for CP-SAT.

The naive baseline violates accessibility, so CP-SAT rejects it as a hint.
This builds a schedule that satisfies every hard constraint and is already
reasonable on the soft ones, which CP-SAT then polishes.
"""

from __future__ import annotations

from core.metrics import ACCESSIBLE_TRANSIT_LIMIT, COMFORT_WALK_LIMIT
from core.models import (
    Assignment,
    University,
    slot_day,
    slot_period,
)

def build(
    u: University,
    allowed_slots: dict[str, set[int]],
    allowed_rooms: dict[str, list[str]],
    max_daily: dict[str, int] | None = None,
    weights: dict[str, int] | None = None,
    keep: Assignment | None = None,
) -> Assignment | None:
    """With `keep`, every placement in it that is still legal is held fixed and
    only the broken ones are re-placed — a repair, not a rebuild."""
    max_daily = max_daily or {}
    w = weights or {"conflict": 1000, "repeater_conflict": 2500, "idle": 40, "walk": 15, "waste": 1}
    slot: dict[str, int] = {}
    room: dict[str, str] = {}

    busy_instructor: set[tuple[str, int]] = set()
    busy_room: set[tuple[str, int]] = set()
    inst_day_count: dict[tuple[str, int], int] = {}
    # student -> slot -> number of classes
    student_load: dict[tuple[str, int], int] = {}
    # student -> day -> {period: room}
    student_day: dict[tuple[str, int], dict[int, str]] = {}

    student_weight = {
        st.id: (w["repeater_conflict"] if st.is_repeater else w["conflict"])
        for st in u.students
    }
    access_students = {st.id for st in u.students if st.needs_accessibility}

    def idle_of(day_map: dict[int, str]) -> int:
        if len(day_map) < 2:
            return 0
        ps = sorted(day_map)
        return ps[-1] - ps[0] + 1 - len(ps)

    todo: set[str] = {m.id for m in u.meetings}
    if keep is not None:
        held = _still_legal(u, keep, allowed_slots, allowed_rooms, max_daily)
        todo -= set(held)
        for mid, (s, r) in held.items():
            sec = u.section_by_id[u.meeting_by_id[mid].section_id]
            slot[mid], room[mid] = s, r
            busy_instructor.add((sec.instructor_id, s))
            busy_room.add((r, s))
            d = slot_day(s)
            inst_day_count[(sec.instructor_id, d)] = (
                inst_day_count.get((sec.instructor_id, d), 0) + 1
            )
            for st in u.students_of_section[sec.id]:
                student_load[(st, s)] = student_load.get((st, s), 0) + 1
                student_day.setdefault((st, d), {})[slot_period(s)] = r

    order = sorted(
        u.sections,
        key=lambda s: (-len(allowed_rooms[u.meetings_of_section[s.id][0].id]), -s.enrollment, s.id),
    )

    for sec in order:
        inst = sec.instructor_id
        students = u.students_of_section[sec.id]
        used_days: set[int] = {
            slot_day(slot[m.id])
            for m in u.meetings_of_section[sec.id]
            if m.id in slot
        }
        for m in u.meetings_of_section[sec.id]:
            if m.id not in todo:
                continue
            best = None
            best_cost = None
            for s in sorted(allowed_slots[m.id]):
                d, p = slot_day(s), slot_period(s)
                if d in used_days or (inst, s) in busy_instructor:
                    continue
                if inst in max_daily and inst_day_count.get((inst, d), 0) >= max_daily[inst]:
                    continue
                conflict_cost = sum(
                    student_weight[st] * student_load.get((st, s), 0) for st in students
                )
                for r in allowed_rooms[m.id]:
                    if (r, s) in busy_room:
                        continue
                    cost = conflict_cost
                    cost += w["waste"] * (u.room_by_id[r].capacity - sec.enrollment)
                    ok = True
                    for st in students:
                        day_map = student_day.get((st, d))
                        if not day_map:
                            continue
                        for q in (p - 1, p + 1):
                            other = day_map.get(q)
                            if other is None:
                                continue
                            mins = u.walk_minutes(r, other)
                            if st in access_students and mins > ACCESSIBLE_TRANSIT_LIMIT:
                                ok = False
                                break
                            if mins > COMFORT_WALK_LIMIT:
                                cost += w["walk"]
                        if not ok:
                            break
                        cost += w["idle"] * (
                            idle_of({**day_map, p: r}) - idle_of(day_map)
                        )
                    if not ok:
                        continue
                    if best_cost is None or cost < best_cost:
                        best_cost, best = cost, (s, r)
                if best_cost == 0:
                    break
            if best is None:
                return None
            s, r = best
            slot[m.id], room[m.id] = s, r
            busy_instructor.add((inst, s))
            busy_room.add((r, s))
            d = slot_day(s)
            used_days.add(d)
            inst_day_count[(inst, d)] = inst_day_count.get((inst, d), 0) + 1
            for st in students:
                student_load[(st, s)] = student_load.get((st, s), 0) + 1
                student_day.setdefault((st, d), {})[slot_period(s)] = r

    # the model breaks symmetry with day(meeting 1) < day(meeting 2)
    for sec in u.sections:
        ms = u.meetings_of_section[sec.id]
        if len(ms) == 2 and slot_day(slot[ms[0].id]) > slot_day(slot[ms[1].id]):
            a, b = ms[0].id, ms[1].id
            slot[a], slot[b] = slot[b], slot[a]
            room[a], room[b] = room[b], room[a]

    return Assignment(slot, room)


def _still_legal(
    u: University,
    a: Assignment,
    allowed_slots: dict[str, set[int]],
    allowed_rooms: dict[str, list[str]],
    max_daily: dict[str, int],
) -> dict[str, tuple[int, str]]:
    """The placements in `a` that survive the new rules, everything else dropped."""
    held: dict[str, tuple[int, str]] = {}
    per_instructor_day: dict[tuple[str, int], int] = {}
    access_students = {st.id for st in u.students if st.needs_accessibility}

    for m in sorted(u.meetings, key=lambda m: m.id):
        s, r = a.slot.get(m.id), a.room.get(m.id)
        if s is None or s not in allowed_slots[m.id] or r not in allowed_rooms[m.id]:
            continue
        sec = u.section_by_id[m.section_id]
        if any(
            held[o][0] == s
            and (
                held[o][1] == r
                or u.section_by_id[u.meeting_by_id[o].section_id].instructor_id
                == sec.instructor_id
            )
            for o in held
        ):
            continue
        sibling = [o for o in u.meetings_of_section[sec.id] if o.id != m.id and o.id in held]
        if sibling and slot_day(held[sibling[0].id][0]) == slot_day(s):
            continue
        cap = max_daily.get(sec.instructor_id)
        day = slot_day(s)
        if cap is not None and per_instructor_day.get((sec.instructor_id, day), 0) >= cap:
            continue
        if not _transit_ok(u, held, access_students, m.id, s, r):
            continue
        held[m.id] = (s, r)
        per_instructor_day[(sec.instructor_id, day)] = (
            per_instructor_day.get((sec.instructor_id, day), 0) + 1
        )
    return held


def _transit_ok(u, held, access_students, mid, s, r) -> bool:
    sec = u.section_by_id[u.meeting_by_id[mid].section_id]
    mine = set(u.students_of_section[sec.id]) & access_students
    if not mine:
        return True
    for other, (os_, orm) in held.items():
        if slot_day(os_) != slot_day(s) or abs(slot_period(os_) - slot_period(s)) != 1:
            continue
        osec = u.section_by_id[u.meeting_by_id[other].section_id]
        if mine & set(u.students_of_section[osec.id]):
            if u.walk_minutes(orm, r) > ACCESSIBLE_TRANSIT_LIMIT:
                return False
    return True
