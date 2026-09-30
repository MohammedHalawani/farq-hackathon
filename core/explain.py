"""Deterministic explanations. The LLM only phrases what these return."""

from __future__ import annotations

from core.metrics import (
    ACCESSIBLE_TRANSIT_LIMIT,
    student_day_meetings,
    student_idle_slots,
)
from core.models import (
    DAYS,
    FIRST_HOUR,
    N_DAYS,
    N_PERIODS,
    Assignment,
    University,
    slot_day,
    slot_id,
    slot_period,
)


def hour(period: int) -> str:
    return f"{FIRST_HOUR + period:02d}:00"


def _entity_students(u: University, entity_id: str) -> list[str]:
    if entity_id in u.student_by_id:
        return [entity_id]
    return [
        st.id
        for st in u.students
        if f"{st.department}-L{st.level}" == entity_id
    ]


def _entity_meetings(u: University, a: Assignment, entity_id: str, day: int) -> list[dict]:
    seen: dict[str, dict] = {}
    for sid in _entity_students(u, entity_id):
        for period, room, mid in student_day_meetings(u, a, sid)[day]:
            seen[mid] = {"meeting_id": mid, "period": period, "room": room}
    return sorted(seen.values(), key=lambda m: m["period"])


def _allowed(u: University, constraints: list[dict], mid: str, slot: int) -> list[str]:
    """User constraints and instructor availability that forbid this slot."""
    reasons = []
    sec = u.section_by_id[u.meeting_by_id[mid].section_id]
    inst = u.instructor_by_id[sec.instructor_id]
    if slot in inst.unavailable_slots:
        reasons.append(f"{inst.name} is not available at {hour(slot_period(slot))}")
    for c in constraints:
        if c["type"] == "instructor_unavailable" and c["instructor_id"] == sec.instructor_id:
            periods = range(N_PERIODS) if c["slots"] == "all" else c["slots"]
            if slot_day(slot) in c["days"] and slot_period(slot) in periods:
                reasons.append(f"a confirmed rule keeps {inst.name} free then")
        if c["type"] == "section_avoid_slots" and c["section_id"] == sec.id:
            if slot_day(slot) in c["days"] and slot_period(slot) in c["slots"]:
                reasons.append(f"a confirmed rule keeps {sec.id} out of that slot")
        if c["type"] == "campus_break":
            if slot_day(slot) in (c.get("days") or range(N_DAYS)) and slot_period(slot) in c["slots"]:
                reasons.append(
                    f"a confirmed rule (campus break) keeps every class out of "
                    f"{hour(slot_period(slot))}"
                )
    return reasons


def needs_lab(u: University, constraints: list[dict], course_id: str) -> bool:
    return u.course_by_id[course_id].needs_lab or any(
        c["type"] == "course_needs_lab" and c["course_id"] == course_id for c in constraints
    )


def _room_options(
    u: University, a: Assignment, constraints: list[dict], mid: str, slot: int
) -> tuple[list[str], list[str]]:
    """(rooms that would work, reasons none do)."""
    sec = u.section_by_id[u.meeting_by_id[mid].section_id]
    closed = {c["room_id"] for c in constraints if c["type"] == "room_closed"}
    needs_access = sec.id in u.sections_needing_accessible() or any(
        c["type"] == "section_require_accessible" and c["section_id"] == sec.id
        for c in constraints
    )
    busy = {
        a.room[other]
        for other in a.slot
        if a.slot[other] == slot and other != mid
    }
    lab = needs_lab(u, constraints, sec.course_id)
    fits = [r for r in u.rooms if r.capacity >= sec.enrollment and (r.kind == "lab" or not lab)]
    ok, too_small, occupied, not_accessible = [], [], [], []
    for r in u.rooms:
        if r.id in closed:
            continue
        if lab and r.kind != "lab":
            continue
        if r.capacity < sec.enrollment:
            too_small.append(r.id)
            continue
        if r.id in busy:
            occupied.append(r.id)
            continue
        if needs_access and not r.accessible:
            not_accessible.append(r.id)
            continue
        ok.append(r.id)
    reasons = []
    if not ok:
        if lab and not fits:
            reasons.append(f"{sec.id} needs a lab and no lab seats {sec.enrollment} students")
        elif lab and not (needs_access and not_accessible):
            reasons.append(
                f"{sec.id} needs a lab and every lab that seats {sec.enrollment} "
                "is already taken at that hour"
            )
        elif not fits:
            reasons.append(f"no room seats {sec.enrollment} students")
        elif needs_access and not_accessible:
            reasons.append(
                f"{sec.id} needs an accessible room and every accessible room that "
                f"seats {sec.enrollment} is already taken at that hour"
            )
        elif occupied:
            reasons.append(
                f"all {len(occupied)} rooms big enough are already in use at that hour"
            )
        else:
            reasons.append("no room is free at that hour")
    return ok, reasons


def blockers(
    u: University, a: Assignment, constraints: list[dict], mid: str, slot: int
) -> list[str]:
    """Every hard constraint that forbids moving this meeting into this slot."""
    out = list(_allowed(u, constraints, mid, slot))
    m = u.meeting_by_id[mid]
    sec = u.section_by_id[m.section_id]

    for other in u.meetings:
        if other.id == mid or other.id not in a.slot:
            continue
        if a.slot[other.id] != slot:
            continue
        if u.section_by_id[other.section_id].instructor_id == sec.instructor_id:
            out.append(
                f"{u.instructor_by_id[sec.instructor_id].name} already teaches "
                f"{u.course_by_id[u.section_by_id[other.section_id].course_id].name} then"
            )
            break

    for sibling in u.meetings_of_section[sec.id]:
        if sibling.id != mid and sibling.id in a.slot:
            if slot_day(a.slot[sibling.id]) == slot_day(slot):
                out.append(
                    f"the section's other meeting is already on {DAYS[slot_day(slot)]}, "
                    "and the two must fall on different days"
                )

    _, room_reasons = _room_options(u, a, constraints, mid, slot)
    out += room_reasons
    return out


def _cost_of_move(u: University, a: Assignment, mid: str, slot: int, room: str) -> dict:
    """What the move would cost, counted rather than guessed."""
    trial = a.copy()
    trial.slot[mid], trial.room[mid] = slot, room
    sec = u.section_by_id[u.meeting_by_id[mid].section_id]
    new_clashes = 0
    new_transit = 0
    for sid in u.students_of_section[sec.id]:
        st = u.student_by_id[sid]
        busy = [
            other
            for other in (m.id for s in st.section_ids for m in u.meetings_of_section[s])
            if other != mid and trial.slot.get(other) == slot
        ]
        new_clashes += len(busy)
        if st.needs_accessibility:
            for p, r, _ in student_day_meetings(u, trial, sid)[slot_day(slot)]:
                if abs(p - slot_period(slot)) == 1 and u.walk_minutes(r, room) > ACCESSIBLE_TRANSIT_LIMIT:
                    new_transit += 1
    affected = sorted(set(u.students_of_section[sec.id]))
    idle_before = sum(student_idle_slots(u, a, sid) for sid in affected)
    idle_after = sum(student_idle_slots(u, trial, sid) for sid in affected)
    return {
        "room": room,
        "new_student_clashes": new_clashes,
        "new_accessibility_transit_breaches": new_transit,
        "idle_hours_saved": idle_before - idle_after,
        "students_affected": len(affected),
    }


def explain_gap(
    u: University,
    a: Assignment,
    constraints: list[dict],
    entity_id: str,
    day: int,
) -> dict:
    """Why the gap in this day is there: what blocks filling it."""
    students = _entity_students(u, entity_id)
    if not students:
        return {"error": f"'{entity_id}' is not a student or a cohort."}
    meetings = _entity_meetings(u, a, entity_id, day)
    if len(meetings) < 2:
        return {
            "entity_id": entity_id,
            "day": DAYS[day],
            "gap_hours": [],
            "note": "There is no gap: fewer than two classes that day.",
        }
    periods = sorted({m["period"] for m in meetings})
    gaps = [p for p in range(periods[0], periods[-1] + 1) if p not in periods]
    if not gaps:
        return {
            "entity_id": entity_id,
            "day": DAYS[day],
            "gap_hours": [],
            "note": "There is no gap that day.",
        }

    movable = [m for m in meetings if m["period"] in (min(gaps) - 1, max(gaps) + 1)]
    findings = []
    for m in movable:
        sec = u.section_by_id[u.meeting_by_id[m["meeting_id"]].section_id]
        course = u.course_by_id[sec.course_id]
        for g in gaps:
            slot = slot_id(day, g)
            why = blockers(u, a, constraints, m["meeting_id"], slot)
            entry = {
                "meeting_id": m["meeting_id"],
                "section_id": sec.id,
                "course": course.name,
                "course_ar": course.name_ar,
                "from_hour": hour(m["period"]),
                "to_hour": hour(g),
                "blocked_by": why,
            }
            if not why:
                rooms, _ = _room_options(u, a, constraints, m["meeting_id"], slot)
                best = min(
                    (_cost_of_move(u, a, m["meeting_id"], slot, r) for r in rooms),
                    key=lambda c: (
                        c["new_accessibility_transit_breaches"],
                        c["new_student_clashes"],
                        -c["idle_hours_saved"],
                    ),
                )
                entry["would_cost"] = best
                if best["new_student_clashes"]:
                    entry["verdict"] = (
                        f"nothing forbids the move, but it would clash with "
                        f"{best['new_student_clashes']} students' other classes"
                    )
                elif best["idle_hours_saved"] <= 0:
                    entry["verdict"] = (
                        "the move is allowed but pointless: it would not shorten "
                        "any student's day, because the students in this class are "
                        "not the ones sitting through the gap"
                    )
                else:
                    entry["verdict"] = (
                        f"possible, and it would save "
                        f"{best['idle_hours_saved']} idle hours"
                    )
            findings.append(entry)

    return {
        "entity_id": entity_id,
        "day": DAYS[day],
        "counts_as": (
            "one student's own timetable"
            if entity_id in u.student_by_id
            else "every class this cohort takes, pooled; an individual student "
            "may sit through less of it"
        ),
        "gap_hours": [hour(g) for g in gaps],
        "gap_length_hours": len(gaps),
        "classes_that_day": [
            {"hour": hour(m["period"]), "room": m["room"], "meeting_id": m["meeting_id"]}
            for m in meetings
        ],
        "moves_considered": findings,
    }


def explain_meeting(
    u: University, a: Assignment, constraints: list[dict], meeting_id: str
) -> dict:
    """Why this meeting sits where it does."""
    if meeting_id not in a.slot:
        return {"error": f"'{meeting_id}' is not in the current schedule."}
    m = u.meeting_by_id[meeting_id]
    sec = u.section_by_id[m.section_id]
    course = u.course_by_id[sec.course_id]
    slot, room = a.slot[meeting_id], a.room[meeting_id]

    blocked_slots, free_slots = {}, []
    for s in range(len(DAYS) * N_PERIODS):
        if s == slot:
            continue
        why = blockers(u, a, constraints, meeting_id, s)
        if why:
            blocked_slots[s] = why
        else:
            free_slots.append(s)

    tally: dict[str, int] = {}
    for reasons in blocked_slots.values():
        tally[reasons[0]] = tally.get(reasons[0], 0) + 1

    lab = needs_lab(u, constraints, sec.course_id)
    fitting = [r for r in u.rooms
               if r.capacity >= sec.enrollment and (r.kind == "lab" or not lab)]
    needs_access = sec.id in u.sections_needing_accessible()
    return {
        "meeting_id": meeting_id,
        "section_id": sec.id,
        "course": course.name,
        "course_ar": course.name_ar,
        "instructor": u.instructor_by_id[sec.instructor_id].name,
        "enrollment": sec.enrollment,
        "current": {
            "day": DAYS[slot_day(slot)],
            "hour": hour(slot_period(slot)),
            "room": room,
            "room_capacity": u.room_by_id[room].capacity,
            "room_accessible": u.room_by_id[room].accessible,
        },
        "room_choice": {
            "rooms_big_enough": len(fitting),
            "of_which_accessible": sum(1 for r in fitting if r.accessible),
            "must_be_accessible": needs_access,
            "must_be_lab": lab,
            "reason": (
                "a student in this section needs an accessible room"
                if needs_access
                else "the course is taught in a lab"
                if lab
                else "any room that seats the section is allowed"
            ),
        },
        "slot_choice": {
            "alternative_slots_blocked": len(blocked_slots),
            "alternative_slots_free": len(free_slots),
            "main_blockers": sorted(tally.items(), key=lambda kv: -kv[1])[:4],
        },
    }
