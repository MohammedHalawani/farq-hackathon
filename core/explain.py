"""Deterministic explanations. The LLM only phrases what these return."""

from __future__ import annotations

import re

from core.metrics import (
    ACCESSIBLE_TRANSIT_LIMIT,
    break_slots,
    student_day_meetings,
    student_idle_slots,
)
from core.models import (
    DAYS,
    DAYS_AR,
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


def _r(en: str, ar: str) -> dict:
    """A reason in both languages, written here so neither depends on a model."""
    return {"en": en, "ar": ar}


def _allowed(u: University, constraints: list[dict], mid: str, slot: int) -> list[dict]:
    """User constraints and instructor availability that forbid this slot."""
    reasons = []
    sec = u.section_by_id[u.meeting_by_id[mid].section_id]
    inst = u.instructor_by_id[sec.instructor_id]
    h = hour(slot_period(slot))
    if slot in inst.unavailable_slots:
        reasons.append(_r(f"{inst.name} is not available at {h}",
                          f"الساعة {h} خارج أوقات {inst.name} المتاحة"))
    for c in constraints:
        if c["type"] == "instructor_unavailable" and c["instructor_id"] == sec.instructor_id:
            periods = range(N_PERIODS) if c["slots"] == "all" else c["slots"]
            if slot_day(slot) in c["days"] and slot_period(slot) in periods:
                reasons.append(_r(f"a confirmed rule keeps {inst.name} free then",
                                  f"قاعدة مؤكدة تمنع تدريس {inst.name} في هذا الوقت"))
        if c["type"] == "section_avoid_slots" and c["section_id"] == sec.id:
            if slot_day(slot) in c["days"] and slot_period(slot) in c["slots"]:
                reasons.append(_r(f"a confirmed rule keeps {sec.id} out of that slot",
                                  f"قاعدة مؤكدة تُبعد الشعبة {sec.id} عن هذا الوقت"))
        if c["type"] == "campus_break":
            if slot_day(slot) in (c.get("days") or range(N_DAYS)) and slot_period(slot) in c["slots"]:
                reasons.append(_r(
                    f"a confirmed rule (campus break) keeps every class out of {h}",
                    f"قاعدة مؤكدة (استراحة عامة) تمنع أي محاضرة الساعة {h}",
                ))
    return reasons


def needs_lab(u: University, constraints: list[dict], course_id: str) -> bool:
    return u.course_by_id[course_id].needs_lab or any(
        c["type"] == "course_needs_lab" and c["course_id"] == course_id for c in constraints
    )


def _room_options(
    u: University, a: Assignment, constraints: list[dict], mid: str, slot: int
) -> tuple[list[str], list[dict]]:
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
    n = sec.enrollment
    if not ok:
        if lab and not fits:
            reasons.append(_r(f"{sec.id} needs a lab and no lab seats {n} students",
                              f"الشعبة {sec.id} تحتاج معملًا ولا يتسع أي معمل لـ {n} طالبًا"))
        elif lab and not (needs_access and not_accessible):
            reasons.append(_r(
                f"{sec.id} needs a lab and every lab that seats {n} "
                "is already taken at that hour",
                f"الشعبة {sec.id} تحتاج معملًا وكل معمل يتسع لـ {n} مشغول في تلك الساعة",
            ))
        elif not fits:
            reasons.append(_r(f"no room seats {n} students",
                              f"لا توجد قاعة تتسع لـ {n} طالبًا"))
        elif needs_access and not_accessible:
            reasons.append(_r(
                f"{sec.id} needs an accessible room and every accessible room that "
                f"seats {n} is already taken at that hour",
                f"الشعبة {sec.id} تحتاج قاعة مهيأة وكل قاعة مهيأة تتسع لـ {n} "
                "مشغولة في تلك الساعة",
            ))
        elif occupied:
            reasons.append(_r(
                f"all {len(occupied)} rooms big enough are already in use at that hour",
                f"كل القاعات الكافية ({len(occupied)}) مشغولة في تلك الساعة",
            ))
        else:
            reasons.append(_r("no room is free at that hour",
                              "لا توجد قاعة متاحة في تلك الساعة"))
    return ok, reasons


def blockers(
    u: University, a: Assignment, constraints: list[dict], mid: str, slot: int
) -> list[str]:
    """Every hard constraint that forbids moving this meeting into this slot."""
    return [r["en"] for r in blocker_reasons(u, a, constraints, mid, slot)]


def blocker_reasons(
    u: University, a: Assignment, constraints: list[dict], mid: str, slot: int
) -> list[dict]:
    """blockers(), each as {en, ar}."""
    out = list(_allowed(u, constraints, mid, slot))
    m = u.meeting_by_id[mid]
    sec = u.section_by_id[m.section_id]

    for other in u.meetings:
        if other.id == mid or other.id not in a.slot:
            continue
        if a.slot[other.id] != slot:
            continue
        if u.section_by_id[other.section_id].instructor_id == sec.instructor_id:
            name = u.instructor_by_id[sec.instructor_id].name
            busy = u.course_by_id[u.section_by_id[other.section_id].course_id]
            out.append(_r(f"{name} already teaches {busy.name} then",
                          f"لدى {name} محاضرة {busy.name_ar} في هذا الوقت"))
            break

    for sibling in u.meetings_of_section[sec.id]:
        if sibling.id != mid and sibling.id in a.slot:
            if slot_day(a.slot[sibling.id]) == slot_day(slot):
                out.append(_r(
                    f"the section's other meeting is already on {DAYS[slot_day(slot)]}, "
                    "and the two must fall on different days",
                    f"المحاضرة الأخرى للشعبة يوم {DAYS_AR[slot_day(slot)]} أصلًا، "
                    "ويجب أن تكونا في يومين مختلفين",
                ))

    _, room_reasons = _room_options(u, a, constraints, mid, slot)
    out += room_reasons
    return out


def _cost_of_move(
    u: University, a: Assignment, mid: str, slot: int, room: str,
    breaks: frozenset[int] = frozenset(),
) -> dict:
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
    idle_before = sum(student_idle_slots(u, a, sid, breaks) for sid in affected)
    idle_after = sum(student_idle_slots(u, trial, sid, breaks) for sid in affected)
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
    if len({m["period"] for m in meetings}) == 1:
        return _explain_single_day(u, a, constraints, entity_id, day, meetings)
    if len(meetings) < 2:
        return {
            "entity_id": entity_id,
            "day": DAYS[day],
            "day_ar": DAYS_AR[day],
            "gap_hours": [],
            "note": "There is no gap: fewer than two classes that day.",
        }
    periods = sorted({m["period"] for m in meetings})
    # a campus-break hour is nobody's gap, though it can still be the reason
    # a class could not move
    breaks = break_slots(constraints)
    gaps = [
        p for p in range(periods[0], periods[-1] + 1)
        if p not in periods and slot_id(day, p) not in breaks
    ]
    inside_breaks = [
        p for p in range(periods[0], periods[-1] + 1)
        if p not in periods and slot_id(day, p) in breaks
    ]
    if not gaps:
        return {
            "entity_id": entity_id,
            "day": DAYS[day],
            "day_ar": DAYS_AR[day],
            "gap_hours": [],
            **({"campus_break_hours": [hour(p) for p in inside_breaks]} if inside_breaks else {}),
            "note": "There is no gap that day."
            + (
                f" The empty hour{'s' if len(inside_breaks) > 1 else ''} at "
                f"{', '.join(hour(p) for p in inside_breaks)} "
                "is the confirmed campus break, which is not a gap."
                if inside_breaks else ""
            ),
        }

    # the classes either side of the gap: the last before it, the first after
    # (next to it, unless a break sits in between)
    before = max(p for p in periods if p < min(gaps))
    after = min(p for p in periods if p > max(gaps))
    movable = [m for m in meetings if m["period"] in (before, after)]
    findings = []
    for m in movable:
        sec = u.section_by_id[u.meeting_by_id[m["meeting_id"]].section_id]
        course = u.course_by_id[sec.course_id]
        for g in gaps:
            slot = slot_id(day, g)
            why_r = blocker_reasons(u, a, constraints, m["meeting_id"], slot)
            why = [r["en"] for r in why_r]
            entry = {
                "meeting_id": m["meeting_id"],
                "section_id": sec.id,
                "course": course.name,
                "course_ar": course.name_ar,
                "from_hour": hour(m["period"]),
                "to_hour": hour(g),
                "blocked_by": why,
                "blocked_by_ar": [r["ar"] for r in why_r],
            }
            if not why:
                rooms, _ = _room_options(u, a, constraints, m["meeting_id"], slot)
                best = min(
                    (_cost_of_move(u, a, m["meeting_id"], slot, r, breaks) for r in rooms),
                    key=lambda c: (
                        c["new_accessibility_transit_breaches"],
                        c["new_student_clashes"],
                        -c["idle_hours_saved"],
                    ),
                )
                entry["would_cost"] = best
                if best["new_student_clashes"]:
                    n = best["new_student_clashes"]
                    entry["verdict"] = (
                        f"nothing forbids the move, but it would clash with "
                        f"{n} students' other classes"
                    )
                    entry["verdict_ar"] = f"لا شيء يمنع النقل، لكنه يسبب تعارضًا لـ {n} طالبًا"
                elif best["idle_hours_saved"] <= 0:
                    entry["verdict"] = (
                        "the move is allowed but pointless: it would not shorten "
                        "any student's day, because the students in this class are "
                        "not the ones sitting through the gap"
                    )
                    entry["verdict_ar"] = (
                        "النقل ممكن لكنه بلا فائدة: طلاب هذه المحاضرة ليسوا من ينتظرون "
                        "في الفراغ"
                    )
                else:
                    n = best["idle_hours_saved"]
                    entry["verdict"] = f"possible, and it would save {n} idle hours"
                    entry["verdict_ar"] = f"ممكن، ويوفّر {n} ساعة فراغ"
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
        "day_ar": DAYS_AR[day],
        "gap_hours": [hour(g) for g in gaps],
        "gap_length_hours": len(gaps),
        **(
            {"campus_break_hours": [hour(p) for p in inside_breaks],
             "campus_break_note": "a confirmed campus break: nobody has class then, "
             "so it is not counted as a gap and no class can move into it"}
            if inside_breaks else {}
        ),
        "classes_that_day": [
            {"hour": hour(m["period"]), "room": m["room"], "meeting_id": m["meeting_id"]}
            for m in meetings
        ],
        "moves_considered": findings,
    }


def _explain_single_day(
    u: University, a: Assignment, constraints: list[dict], entity_id: str, day: int,
    meetings: list[dict],
) -> dict:
    """Why this day has only one class: try moving it next to the classes of
    every other day the entity comes in, and say what stops each move."""
    breaks = break_slots(constraints)
    lone = meetings[0]
    sec = u.section_by_id[u.meeting_by_id[lone["meeting_id"]].section_id]
    course = u.course_by_id[sec.course_id]
    findings = []
    for d2 in range(N_DAYS):
        if d2 == day:
            continue
        there = sorted({m["period"] for m in _entity_meetings(u, a, entity_id, d2)})
        if not there:
            continue        # moving it to an empty day just moves the problem
        # hours right next to that day's classes: no new gap
        options = sorted({
            p for q in there for p in (q - 1, q + 1)
            if 0 <= p < N_PERIODS and p not in there and slot_id(d2, p) not in breaks
        })
        best = None
        for p in options:
            slot = slot_id(d2, p)
            why = blocker_reasons(u, a, constraints, lone["meeting_id"], slot)
            entry = {
                "meeting_id": lone["meeting_id"], "section_id": sec.id,
                "course": course.name, "course_ar": course.name_ar,
                "from_hour": hour(lone["period"]), "to_hour": hour(p),
                "to_day": DAYS[d2], "to_day_ar": DAYS_AR[d2],
                "blocked_by": [r["en"] for r in why],
                "blocked_by_ar": [r["ar"] for r in why],
            }
            if not why:
                rooms, _ = _room_options(u, a, constraints, lone["meeting_id"], slot)
                cost = min((_cost_of_move(u, a, lone["meeting_id"], slot, r, breaks) for r in rooms),
                           key=lambda c: (c["new_accessibility_transit_breaches"],
                                          c["new_student_clashes"]))
                n = cost["new_student_clashes"]
                if n:
                    entry["verdict"] = f"nothing forbids it, but it would clash with {n} students' other classes"
                    entry["verdict_ar"] = f"لا شيء يمنعه، لكنه يسبب تعارضًا لـ {n} طالبًا"
                else:
                    entry["verdict"] = "possible: nothing forbids it and no student would clash"
                    entry["verdict_ar"] = "ممكن: لا شيء يمنعه ولا يتعارض أي طالب"
                best = entry
                if not n:
                    break
            elif best is None:
                best = entry
        if best is not None:
            findings.append(best)
    return {
        "entity_id": entity_id,
        "day": DAYS[day],
        "day_ar": DAYS_AR[day],
        "gap_hours": [],
        "note": "There is no gap: only one class that day.",
        "counts_as": (
            "one student's own timetable"
            if entity_id in u.student_by_id
            else "every class this cohort takes, pooled; an individual student "
            "may have a different day"
        ),
        "single_class": {
            "meeting_id": lone["meeting_id"], "section_id": sec.id,
            "course": course.name, "course_ar": course.name_ar,
            "hour": hour(lone["period"]),
        },
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
        why = blocker_reasons(u, a, constraints, meeting_id, s)
        if why:
            blocked_slots[s] = why
        else:
            free_slots.append(s)

    # the first reason per blocked slot, counted; hours are dropped from the
    # key so "not available at 09:00" and "at 10:00" count as one reason
    tally: dict[str, list] = {}
    for reasons in blocked_slots.values():
        first = reasons[0]
        key = _without_hour(first["en"])
        if key not in tally:
            tally[key] = [_without_hour(first["en"]), _without_hour(first["ar"]), 0]
        tally[key][2] += 1
    top = sorted(tally.values(), key=lambda t: -t[2])[:4]

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
            "reason_ar": (
                "في الشعبة طالب يحتاج قاعة مهيأة"
                if needs_access
                else "المقرر يُدرَّس في معمل"
                if lab
                else "أي قاعة تتسع للشعبة مسموحة"
            ),
        },
        "slot_choice": {
            "alternative_slots_blocked": len(blocked_slots),
            "alternative_slots_free": len(free_slots),
            "main_blockers": [(en, n) for en, _, n in top],
            "main_blockers_ar": [(ar, n) for _, ar, n in top],
        },
        "instructor_name": u.instructor_by_id[sec.instructor_id].name,
        "current_ar": {"day": DAYS_AR[slot_day(slot)]},
    }


def _without_hour(text: str) -> str:
    return re.sub(r"\s*(at|الساعة)\s+\d{2}:\d{2}\s*", " ", text).strip()


# --- the summary the chat shows verbatim ----------------------------------------


def _spans(hours: list[str], sep: str = ", ") -> str:
    """["10:00", "11:00", "13:00"] -> "10:00–12:00, 13:00–14:00"."""
    ps = sorted(int(h[:2]) for h in hours)
    runs: list[list[int]] = []
    for p in ps:
        if runs and p == runs[-1][1]:
            runs[-1][1] = p + 1
        else:
            runs.append([p, p + 1])
    return sep.join(f"{a:02d}:00–{b:02d}:00" for a, b in runs)


def _hours_word(n: int, ar: bool) -> str:
    if not ar:
        return f"{n} hour{'s' if n != 1 else ''}"
    return {1: "ساعة واحدة", 2: "ساعتان"}.get(n, f"{n} ساعات")


def _summarize_single(out: dict, ar: bool) -> str:
    who, day, one = out["entity_id"], out["day_ar"] if ar else out["day"], out["single_class"]
    course = one["course_ar"] if ar else one["course"]
    lines = [
        f"يوم {day} لـ {who} فيه محاضرة واحدة فقط: {course} الساعة {one['hour']}."
        if ar else
        f"{who} has only one class on {day}: {course} at {one['hour']}."
    ]
    if "pooled" in out.get("counts_as", ""):
        lines.append("هذه محاضرات الدفعة كلها معًا؛ قد يختلف يوم الطالب الواحد."
                     if ar else
                     "This pools every class the cohort takes; one student's day may differ.")
    if not out["moves_considered"]:
        lines.append("لا يوجد يوم آخر فيه محاضرات يمكن نقلها إليه."
                     if ar else "There is no other day with classes to move it to.")
    for m in out["moves_considered"]:
        to_day = m["to_day_ar"] if ar else m["to_day"]
        why = ((m["blocked_by_ar"] if ar else m["blocked_by"]) or [None])[0] \
            or (m["verdict_ar"] if ar else m["verdict"])
        lines.append(
            f"• نقلها إلى {to_day} الساعة {m['to_hour']}: {why}."
            if ar else
            f"• Moving it to {to_day} {m['to_hour']}: {why}."
        )
    return "\n".join(lines)


def summarize_gap(out: dict, lang: str = "en") -> str | None:
    """explain_gap's result as the lines the chat shows word for word."""
    if "error" in out:
        return None
    ar = lang == "ar"
    if out.get("single_class"):
        return _summarize_single(out, ar)
    who, day = out["entity_id"], out["day_ar"] if ar else out["day"]
    breaks = out.get("campus_break_hours", [])
    break_line = (
        (f"الساعة {'، '.join(breaks)} استراحة عامة: لا تُحسب فراغًا ولا يمكن نقل محاضرة إليها."
         if ar else
         f"{', '.join(breaks)} is the campus break: it is not a gap, and no class can move into it.")
        if breaks else None
    )
    if not out["gap_hours"]:
        head = (f"لا يوجد فراغ لـ {who} يوم {day}." if ar
                else f"{who} has no gap on {day}.")
        return "\n".join(x for x in (head, break_line) if x)

    n = out["gap_length_hours"]
    lines = [
        f"فراغ {who} يوم {day}: {_spans(out['gap_hours'], '، ')} ({_hours_word(n, True)})."
        if ar else
        f"{who} has a gap on {day}: {_spans(out['gap_hours'])} ({_hours_word(n, False)})."
    ]
    if break_line:
        lines.append(break_line)
    if who not in out.get("counts_as", "") and "pooled" in out.get("counts_as", ""):
        lines.append("هذه محاضرات الدفعة كلها معًا؛ قد ينتظر الطالب الواحد أقل من ذلك."
                     if ar else
                     "This pools every class the cohort takes; one student may wait less.")
    for m in out["moves_considered"]:
        course = m["course_ar"] if ar else m["course"]
        if m["blocked_by"]:
            why = (m["blocked_by_ar"] if ar else m["blocked_by"])[0]
        else:
            why = m["verdict_ar"] if ar else m["verdict"]
        lines.append(
            f"• نقل {course} من {m['from_hour']} إلى {m['to_hour']}: {why}."
            if ar else
            f"• Moving {course} from {m['from_hour']} to {m['to_hour']}: {why}."
        )
    return "\n".join(lines)


def summarize_meeting(out: dict, lang: str = "en") -> str | None:
    """explain_meeting's result as the lines the chat shows word for word."""
    if "error" in out:
        return None
    ar = lang == "ar"
    cur, sc, rc = out["current"], out["slot_choice"], out["room_choice"]
    total = sc["alternative_slots_blocked"] + sc["alternative_slots_free"]
    if ar:
        lines = [
            f"{out['course_ar']} ({out['meeting_id']}) يوم {out['current_ar']['day']} "
            f"الساعة {cur['hour']} في القاعة {cur['room']}، مع {out['instructor_name']}.",
            f"القاعة: {rc['reason_ar']}.",
            f"من {total} وقتًا بديلًا: {sc['alternative_slots_blocked']} محجوب "
            f"و{sc['alternative_slots_free']} متاح.",
        ]
        lines += [f"• {why} ({n})." for why, n in sc["main_blockers_ar"]]
    else:
        lines = [
            f"{out['course']} ({out['meeting_id']}) is on {cur['day']} at {cur['hour']} "
            f"in {cur['room']}, with {out['instructor_name']}.",
            f"Room: {rc['reason']}.",
            f"Of {total} other times: {sc['alternative_slots_blocked']} blocked, "
            f"{sc['alternative_slots_free']} free.",
        ]
        lines += [f"• {why} ({n})." for why, n in sc["main_blockers"]]
    return "\n".join(lines)
