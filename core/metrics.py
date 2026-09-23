from __future__ import annotations

import statistics
from dataclasses import dataclass

from core.models import (
    FIRST_HOUR,
    N_DAYS,
    Assignment,
    University,
    slot_day,
    slot_period,
)

ACCESSIBLE_TRANSIT_LIMIT = 6
COMFORT_WALK_LIMIT = 8


def student_day_meetings(
    u: University, a: Assignment, student_id: str
) -> dict[int, list[tuple[int, str, str]]]:
    """day -> sorted list of (period, room_id, meeting_id)."""
    st = u.student_by_id[student_id]
    by_day: dict[int, list[tuple[int, str, str]]] = {d: [] for d in range(N_DAYS)}
    for sid in st.section_ids:
        for m in u.meetings_of_section[sid]:
            if m.id not in a.slot:
                continue
            s = a.slot[m.id]
            by_day[slot_day(s)].append((slot_period(s), a.room[m.id], m.id))
    for d in by_day:
        by_day[d].sort()
    return by_day


def student_conflicts(u: University, a: Assignment, student_id: str) -> int:
    seen: dict[int, int] = {}
    st = u.student_by_id[student_id]
    for sid in st.section_ids:
        for m in u.meetings_of_section[sid]:
            if m.id not in a.slot:
                continue
            seen[a.slot[m.id]] = seen.get(a.slot[m.id], 0) + 1
    return sum(c - 1 for c in seen.values() if c > 1)


def student_idle_slots(u: University, a: Assignment, student_id: str) -> int:
    total = 0
    for _, ms in student_day_meetings(u, a, student_id).items():
        if len(ms) < 2:
            continue
        periods = sorted({p for p, _, _ in ms})
        total += periods[-1] - periods[0] + 1 - len(periods)
    return total


def student_longest_gap(u: University, a: Assignment, student_id: str) -> int:
    """The longest single run of idle hours in the student's week."""
    worst = 0
    for _, ms in student_day_meetings(u, a, student_id).items():
        periods = sorted({p for p, _, _ in ms})
        if len(periods) < 2:
            continue
        run = 0
        for p in range(periods[0], periods[-1] + 1):
            run = 0 if p in periods else run + 1
            worst = max(worst, run)
    return worst


def student_transits(u: University, a: Assignment, student_id: str) -> list[int]:
    out: list[int] = []
    for _, ms in student_day_meetings(u, a, student_id).items():
        for (p1, r1, _), (p2, r2, _) in zip(ms, ms[1:]):
            if p2 - p1 == 1:
                out.append(u.walk_minutes(r1, r2))
    return out


def accessibility_violations(u: University, a: Assignment) -> list[dict]:
    """Inaccessible rooms and over-limit transits for students who need access."""
    out: list[dict] = []
    need_sections = u.sections_needing_accessible()
    for sid in sorted(need_sections):
        for m in u.meetings_of_section[sid]:
            if m.id not in a.room:
                continue
            r = u.room_by_id[a.room[m.id]]
            if not r.accessible:
                out.append(
                    {
                        "type": "inaccessible_room",
                        "meeting_id": m.id,
                        "section_id": sid,
                        "room_id": r.id,
                    }
                )
    for st in u.students:
        if not st.needs_accessibility:
            continue
        for day, ms in student_day_meetings(u, a, st.id).items():
            for (p1, r1, m1), (p2, r2, m2) in zip(ms, ms[1:]):
                if p2 - p1 != 1:
                    continue
                w = u.walk_minutes(r1, r2)
                if w > ACCESSIBLE_TRANSIT_LIMIT:
                    out.append(
                        {
                            "type": "transit_over_limit",
                            "student_id": st.id,
                            "day": day,
                            "meeting_ids": [m1, m2],
                            "minutes": w,
                        }
                    )
    return out


def problem_labels(
    u: University, a: Assignment, entity_type: str, entity_id: str
) -> dict[str, list[dict]]:
    """Why each meeting is a problem for this entity, in words an administrator
    can read. Built here so the wording never depends on the model."""
    out: dict[str, list[dict]] = {}

    def add(mid: str, kind: str, text_en: str, text_ar: str) -> None:
        out.setdefault(mid, []).append(
            {"kind": kind, "text_en": text_en, "text_ar": text_ar}
        )

    if entity_type == "student":
        student_ids = [entity_id]
    elif entity_type == "cohort":
        student_ids = [
            s.id for s in u.students if f"{s.department}-L{s.level}" == entity_id
        ]
    else:
        student_ids = []

    # --- clashes: two classes the same person must be at once
    for sid in student_ids:
        st = u.student_by_id[sid]
        at_slot: dict[int, list[str]] = {}
        for sec in st.section_ids:
            for m in u.meetings_of_section[sec]:
                if m.id in a.slot:
                    at_slot.setdefault(a.slot[m.id], []).append(m.id)
        for slot, mids in at_slot.items():
            if len(mids) < 2:
                continue
            names = [
                u.course_by_id[u.section_by_id[u.meeting_by_id[m].section_id].course_id]
                for m in mids
            ]
            when = f"{FIRST_HOUR + slot_period(slot):02d}:00"
            en = " and ".join(c.name for c in names) + f" both at {when}"
            ar = " و".join(c.name_ar for c in names) + f" في نفس الوقت {when}"
            for m in mids:
                add(m, "clash", en, ar)

    # --- accessibility: the room itself, then the walk between rooms
    need = {sid for sid in student_ids if u.student_by_id[sid].needs_accessibility}
    for sid in need:
        st = u.student_by_id[sid]
        for sec in st.section_ids:
            for m in u.meetings_of_section[sec]:
                if m.id not in a.room:
                    continue
                r = u.room_by_id[a.room[m.id]]
                if r.accessible:
                    continue
                where = f" · floor {r.floor}" if r.floor and r.floor > 1 else ""
                where_ar = f" · الدور {r.floor}" if r.floor and r.floor > 1 else ""
                add(
                    m.id,
                    "inaccessible",
                    f"Room {r.id}{where} · no step-free access",
                    f"قاعة {r.id}{where_ar} · غير مهيّأة للوصول",
                )
        for _, ms in student_day_meetings(u, a, sid).items():
            for (p1, r1, m1), (p2, r2, m2) in zip(ms, ms[1:]):
                if p2 - p1 != 1:
                    continue
                mins = u.walk_minutes(r1, r2)
                if mins <= ACCESSIBLE_TRANSIT_LIMIT:
                    continue
                for m in (m1, m2):
                    add(
                        m,
                        "transit",
                        f"{mins} min walk (limit {ACCESSIBLE_TRANSIT_LIMIT})",
                        f"{mins} دقيقة مشي (الحد {ACCESSIBLE_TRANSIT_LIMIT})",
                    )

    # de-duplicate: the same walk is reported from both ends
    for mid, items in out.items():
        seen, unique = set(), []
        for it in items:
            if it["text_en"] in seen:
                continue
            seen.add(it["text_en"])
            unique.append(it)
        out[mid] = unique
    return out


@dataclass
class Metrics:
    data: dict

    def __getitem__(self, k):
        return self.data[k]


def compute(u: University, a: Assignment) -> dict:
    idle_per_student = {}
    conflicts_per_student = {}
    longest_gap = {}
    transits: list[int] = []
    for st in u.students:
        idle_per_student[st.id] = student_idle_slots(u, a, st.id)
        conflicts_per_student[st.id] = student_conflicts(u, a, st.id)
        longest_gap[st.id] = student_longest_gap(u, a, st.id)
        transits.extend(student_transits(u, a, st.id))

    n = len(u.students)
    repeaters = [s for s in u.students if s.is_repeater]

    idle_by_cohort: dict[str, list[float]] = {}
    for st in u.students:
        idle_by_cohort.setdefault(f"{st.department}-L{st.level}", []).append(
            idle_per_student[st.id] / N_DAYS
        )

    fills = []
    for sec in u.sections:
        for m in u.meetings_of_section[sec.id]:
            if m.id in a.room:
                fills.append(sec.enrollment / u.room_by_id[a.room[m.id]].capacity)

    load: dict[str, list[int]] = {i.id: [0] * N_DAYS for i in u.instructors}
    for m in u.meetings:
        if m.id not in a.slot:
            continue
        sec = u.section_by_id[m.section_id]
        load[sec.instructor_id][slot_day(a.slot[m.id])] += 1
    max_daily = [max(v) for v in load.values()]

    viol = accessibility_violations(u, a)
    acc_transits: list[int] = []
    for st in u.students:
        if st.needs_accessibility:
            acc_transits.extend(student_transits(u, a, st.id))

    return {
        "avg_idle_minutes_per_student_per_day": round(
            60 * sum(idle_per_student.values()) / n / N_DAYS, 1
        ),
        "idle_by_cohort": {
            k: round(60 * sum(v) / len(v), 1) for k, v in sorted(idle_by_cohort.items())
        },
        "pct_students_conflict_free": round(
            100 * sum(1 for v in conflicts_per_student.values() if v == 0) / n, 1
        ),
        "pct_repeaters_conflict_free": round(
            100
            * sum(1 for s in repeaters if conflicts_per_student[s.id] == 0)
            / max(len(repeaters), 1),
            1,
        ),
        "total_student_conflicts": sum(conflicts_per_student.values()),
        "pct_students_with_2h_gap": round(
            100 * sum(1 for v in longest_gap.values() if v >= 2) / n, 1
        ),
        "pct_students_with_any_gap": round(
            100 * sum(1 for v in longest_gap.values() if v >= 1) / n, 1
        ),
        "worst_gap_hours": max(longest_gap.values()) if longest_gap else 0,
        "avg_room_fill_rate": round(sum(fills) / max(len(fills), 1), 3),
        "avg_walk_minutes": round(sum(transits) / max(len(transits), 1), 2),
        "accessibility_violations": len(viol),
        "accessibility_violation_detail": viol,
        "access_avg_transit_minutes": round(
            sum(acc_transits) / max(len(acc_transits), 1), 2
        ),
        "access_max_transit_minutes": max(acc_transits) if acc_transits else 0,
        "instructor_load_std": round(
            statistics.pstdev(max_daily) if len(max_daily) > 1 else 0.0, 3
        ),
        "instructor_max_daily": max(max_daily) if max_daily else 0,
    }


SUMMARY_KEYS = [
    ("avg_idle_minutes_per_student_per_day", "Avg idle minutes / student / day", "lower"),
    ("pct_students_with_2h_gap", "% students with a 2h+ gap", "lower"),
    ("pct_students_with_any_gap", "% students with any gap", "lower"),
    ("worst_gap_hours", "Worst single gap (hours)", "lower"),
    ("pct_students_conflict_free", "% students conflict-free", "higher"),
    ("pct_repeaters_conflict_free", "% repeaters conflict-free", "higher"),
    ("total_student_conflicts", "Total student conflicts", "lower"),
    ("avg_room_fill_rate", "Avg room fill rate", "higher"),
    ("avg_walk_minutes", "Avg walking minutes", "lower"),
    ("accessibility_violations", "Accessibility violations", "lower"),
    ("access_avg_transit_minutes", "Accessibility avg transit (min)", "lower"),
    ("access_max_transit_minutes", "Accessibility max transit (min)", "lower"),
    ("instructor_load_std", "Instructor load std. dev.", "lower"),
]


def delta(before: dict, after: dict) -> dict:
    out = {}
    for key, label, direction in SUMMARY_KEYS:
        b, a_ = before[key], after[key]
        out[key] = {
            "label": label,
            "before": b,
            "after": a_,
            "delta": round(a_ - b, 3),
            "better": direction,
        }
    return out


def moved_meetings(before: Assignment, after: Assignment) -> list[str]:
    return sorted(
        m
        for m in after.slot
        if before.slot.get(m) != after.slot.get(m)
        or before.room.get(m) != after.room.get(m)
    )
