from __future__ import annotations

from dataclasses import dataclass, field

from ortools.sat.python import cp_model

from core.metrics import ACCESSIBLE_TRANSIT_LIMIT, COMFORT_WALK_LIMIT
from core.models import (
    N_DAYS,
    N_PERIODS,
    N_SLOTS,
    Assignment,
    University,
    slot_day,
    slot_id,
    slot_period,
)

PROFILES = {
    "student_friendly": {
        "conflict": 1000,
        "repeater_conflict": 2500,
        "idle": 40,
        "walk": 15,
        "waste": 1,
        "peak": 5,
    },
    "room_efficient": {
        "conflict": 1000,
        "repeater_conflict": 2500,
        "idle": 5,
        "walk": 3,
        "waste": 10,
        "peak": 5,
    },
    "balanced": {
        "conflict": 1000,
        "repeater_conflict": 2500,
        "idle": 20,
        "walk": 8,
        "waste": 4,
        "peak": 8,
    },
}

MOVE_PENALTY = 60


@dataclass
class SolveResult:
    status: str
    assignment: Assignment | None
    objective: int | None
    wall_time: float
    profile: str
    blocking_constraints: list[dict] = field(default_factory=list)
    message: str = ""


@dataclass
class _Group:
    section_ids: frozenset[str]
    size: int
    repeater: bool
    needs_accessibility: bool


def student_groups(u: University) -> list[_Group]:
    """Students with identical enrolments are modelled once and weighted."""
    buckets: dict[frozenset[str], _Group] = {}
    for st in u.students:
        key = frozenset(st.section_ids)
        g = buckets.get(key)
        if g is None:
            g = _Group(key, 0, False, False)
            buckets[key] = g
        g.size += 1
        g.repeater = g.repeater or st.is_repeater
        g.needs_accessibility = g.needs_accessibility or st.needs_accessibility
    return [buckets[k] for k in sorted(buckets, key=lambda s: sorted(s))]


def _allowed_slots(u: University, constraints: list[dict]) -> dict[str, set[int]]:
    allowed = {m.id: set(range(N_SLOTS)) for m in u.meetings}
    for m in u.meetings:
        sec = u.section_by_id[m.section_id]
        allowed[m.id] -= u.instructor_by_id[sec.instructor_id].unavailable_slots
    for c in constraints:
        if c["type"] == "instructor_unavailable":
            banned = _slot_set(c)
            for m in u.meetings:
                if u.section_by_id[m.section_id].instructor_id == c["instructor_id"]:
                    allowed[m.id] -= banned
        elif c["type"] == "section_avoid_slots":
            banned = _slot_set(c)
            for m in u.meetings_of_section.get(c["section_id"], []):
                allowed[m.id] -= banned
    return allowed


def _slot_set(c: dict) -> set[int]:
    days = c.get("days") or list(range(N_DAYS))
    periods = c.get("slots")
    if periods in (None, "all"):
        periods = list(range(N_PERIODS))
    return {slot_id(d, p) for d in days for p in periods}


def _allowed_rooms(u: University, constraints: list[dict]) -> dict[str, list[str]]:
    closed = {c["room_id"] for c in constraints if c["type"] == "room_closed"}
    need_access = u.sections_needing_accessible() | {
        c["section_id"] for c in constraints if c["type"] == "section_require_accessible"
    }
    allowed: dict[str, list[str]] = {}
    for m in u.meetings:
        sec = u.section_by_id[m.section_id]
        rooms = [
            r.id
            for r in u.rooms
            if r.id not in closed
            and r.capacity >= sec.enrollment
            and (r.accessible or sec.id not in need_access)
        ]
        allowed[m.id] = rooms
    return allowed


def solve(
    u: University,
    profile: str = "balanced",
    constraints: list[dict] | None = None,
    base: Assignment | None = None,
    time_limit: float = 30.0,
    minimal_change: bool = False,
) -> SolveResult:
    constraints = constraints or []
    w = PROFILES[profile]

    allowed_slots = _allowed_slots(u, constraints)
    allowed_rooms = _allowed_rooms(u, constraints)

    for m in u.meetings:
        if not allowed_slots[m.id] or not allowed_rooms[m.id]:
            return SolveResult(
                "INFEASIBLE",
                None,
                None,
                0.0,
                profile,
                message=f"No slot or room left for meeting {m.id}",
            )

    model = cp_model.CpModel()
    building_ids = [b.id for b in u.buildings]

    y: dict[str, dict[int, cp_model.IntVar]] = {}
    z: dict[str, dict[str, cp_model.IntVar]] = {}
    slot_var: dict[str, cp_model.IntVar] = {}
    day_var: dict[str, cp_model.IntVar] = {}
    per_var: dict[str, cp_model.IntVar] = {}
    in_building: dict[str, dict[str, cp_model.IntVar]] = {}

    for m in u.meetings:
        ys = {s: model.NewBoolVar(f"y_{m.id}_{s}") for s in sorted(allowed_slots[m.id])}
        y[m.id] = ys
        model.AddExactlyOne(ys.values())
        zs = {r: model.NewBoolVar(f"z_{m.id}_{r}") for r in allowed_rooms[m.id]}
        z[m.id] = zs
        model.AddExactlyOne(zs.values())

        sv = model.NewIntVarFromDomain(
            cp_model.Domain.FromValues(sorted(ys)), f"slot_{m.id}"
        )
        model.Add(sv == sum(s * v for s, v in ys.items()))
        slot_var[m.id] = sv
        dv = model.NewIntVar(0, N_DAYS - 1, f"day_{m.id}")
        model.Add(dv == sum(slot_day(s) * v for s, v in ys.items()))
        day_var[m.id] = dv
        pv = model.NewIntVar(0, N_PERIODS - 1, f"per_{m.id}")
        model.Add(pv == sum(slot_period(s) * v for s, v in ys.items()))
        per_var[m.id] = pv

        bs = {}
        for b in building_ids:
            members = [zs[r] for r in zs if u.room_by_id[r].building_id == b]
            if not members:
                continue
            bv = model.NewBoolVar(f"b_{m.id}_{b}")
            model.AddMaxEquality(bv, members)
            bs[b] = bv
        in_building[m.id] = bs

    # --- hard: no instructor overlap
    by_instructor: dict[str, list[str]] = {}
    for m in u.meetings:
        by_instructor.setdefault(
            u.section_by_id[m.section_id].instructor_id, []
        ).append(m.id)
    for inst, mids in by_instructor.items():
        model.AddAllDifferent([slot_var[i] for i in mids])

    # --- hard: no room overlap (one optional interval per meeting/room)
    per_room: dict[str, list] = {r.id: [] for r in u.rooms}
    for m in u.meetings:
        for r, presence in z[m.id].items():
            iv = model.NewOptionalFixedSizeIntervalVar(
                slot_var[m.id], 1, presence, f"iv_{m.id}_{r}"
            )
            per_room[r].append(iv)
    for r, ivs in per_room.items():
        if len(ivs) > 1:
            model.AddNoOverlap(ivs)

    # --- hard: a section's two meetings fall on different days
    for sec in u.sections:
        ms = u.meetings_of_section[sec.id]
        if len(ms) == 2:
            model.Add(day_var[ms[0].id] < day_var[ms[1].id])

    groups = student_groups(u)

    def adjacency(m1: str, m2: str) -> cp_model.IntVar:
        """True when m2 sits in the period right after m1 on the same day."""
        key = (m1, m2)
        if key in adj_cache:
            return adj_cache[key]
        sd = model.NewBoolVar(f"sd_{m1}_{m2}")
        model.Add(day_var[m1] != day_var[m2]).OnlyEnforceIf(sd.Not())
        nx = model.NewBoolVar(f"nx_{m1}_{m2}")
        model.Add(per_var[m2] - per_var[m1] != 1).OnlyEnforceIf(nx.Not())
        a = model.NewBoolVar(f"adj_{m1}_{m2}")
        model.Add(a >= sd + nx - 1)
        adj_cache[key] = a
        return a

    adj_cache: dict[tuple[str, str], cp_model.IntVar] = {}
    penalties: list[tuple[int, cp_model.IntVar]] = []

    def group_meetings(g: _Group) -> list[str]:
        return [
            m.id for sid in sorted(g.section_ids) for m in u.meetings_of_section[sid]
        ]

    for g in groups:
        mids = group_meetings(g)
        weight_conflict = w["repeater_conflict"] if g.repeater else w["conflict"]

        # --- soft: student clashes
        for i in range(len(mids)):
            for j in range(i + 1, len(mids)):
                if u.meeting_by_id[mids[i]].section_id == u.meeting_by_id[mids[j]].section_id:
                    continue
                same = model.NewBoolVar(f"cl_{mids[i]}_{mids[j]}_{g.size}")
                model.Add(slot_var[mids[i]] != slot_var[mids[j]]).OnlyEnforceIf(
                    same.Not()
                )
                penalties.append((weight_conflict * g.size, same))

        # --- walking between consecutive classes
        for m1 in mids:
            for m2 in mids:
                if m1 >= m2:
                    continue
                for a, b in ((m1, m2), (m2, m1)):
                    adj = adjacency(a, b)
                    far = model.NewBoolVar(f"far_{a}_{b}")
                    hit = False
                    for b1, v1 in in_building[a].items():
                        for b2, v2 in in_building[b].items():
                            mins = u.walk[(b1, b2)]
                            if mins > COMFORT_WALK_LIMIT:
                                model.AddBoolOr([far, adj.Not(), v1.Not(), v2.Not()])
                                hit = True
                            # --- hard: accessibility transit limit
                            if g.needs_accessibility and mins > ACCESSIBLE_TRANSIT_LIMIT:
                                model.AddBoolOr([adj.Not(), v1.Not(), v2.Not()])
                    if hit:
                        penalties.append((w["walk"] * g.size, far))

        # --- soft: idle slots between the first and last class of a day
        occ: dict[int, cp_model.IntVar] = {}
        for s in range(N_SLOTS):
            here = [y[m][s] for m in mids if s in y[m]]
            if not here:
                continue
            o = model.NewBoolVar(f"occ_{id(g)}_{s}")
            model.AddMaxEquality(o, here)
            occ[s] = o
        for d in range(N_DAYS):
            day_occ = [occ.get(slot_id(d, p)) for p in range(N_PERIODS)]
            pre: list[cp_model.IntVar | None] = [None] * N_PERIODS
            post: list[cp_model.IntVar | None] = [None] * N_PERIODS
            run = None
            for p in range(N_PERIODS):
                run = _or_var(model, run, day_occ[p], f"pre_{id(g)}_{d}_{p}")
                pre[p] = run
            run = None
            for p in reversed(range(N_PERIODS)):
                run = _or_var(model, run, day_occ[p], f"post_{id(g)}_{d}_{p}")
                post[p] = run
            for p in range(1, N_PERIODS - 1):
                if pre[p - 1] is None or post[p + 1] is None:
                    continue
                gap = model.NewBoolVar(f"gap_{id(g)}_{d}_{p}")
                lits = [gap, pre[p - 1].Not(), post[p + 1].Not()]
                if day_occ[p] is not None:
                    lits.append(day_occ[p])
                model.AddBoolOr(lits)
                penalties.append((w["idle"] * g.size, gap))

    # --- soft: room waste
    waste_terms = []
    for m in u.meetings:
        enroll = u.section_by_id[m.section_id].enrollment
        waste_terms += [
            (u.room_by_id[r].capacity - enroll) * v for r, v in z[m.id].items()
        ]
    waste = model.NewIntVar(0, 100000, "waste")
    model.Add(waste == sum(waste_terms))

    # --- soft: instructor peak load, hard: instructor_max_daily
    max_daily = {
        c["instructor_id"]: c["max_classes"]
        for c in constraints
        if c["type"] == "instructor_max_daily"
    }
    peak_terms = []
    for inst, mids in by_instructor.items():
        peak = model.NewIntVar(0, len(mids), f"peak_{inst}")
        for d in range(N_DAYS):
            count = sum(
                y[mid][s] for mid in mids for s in y[mid] if slot_day(s) == d
            )
            model.Add(peak >= count)
            if inst in max_daily:
                model.Add(count <= max_daily[inst])
        peak_terms.append(peak)

    obj = [weight * var for weight, var in penalties]
    obj.append(w["waste"] * waste)
    obj += [w["peak"] * p for p in peak_terms]

    if minimal_change and base is not None:
        for m in u.meetings:
            bs, br = base.slot.get(m.id), base.room.get(m.id)
            if bs is None or bs not in y[m.id] or br not in z[m.id]:
                continue
            moved = model.NewBoolVar(f"mv_{m.id}")
            model.Add(y[m.id][bs] + z[m.id][br] >= 2).OnlyEnforceIf(moved.Not())
            obj.append(MOVE_PENALTY * moved)

    model.Minimize(sum(obj))

    if base is not None:
        for m in u.meetings:
            bs, br = base.slot.get(m.id), base.room.get(m.id)
            if bs in y[m.id]:
                model.AddHint(y[m.id][bs], 1)
            if br in z[m.id]:
                model.AddHint(z[m.id][br], 1)

    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = time_limit
    solver.parameters.num_workers = 8
    solver.parameters.random_seed = 7
    status = solver.Solve(model)
    name = solver.StatusName(status)

    if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        return SolveResult(name, None, None, solver.WallTime(), profile)

    assignment = Assignment(
        slot={
            m.id: next(s for s, v in y[m.id].items() if solver.Value(v)) for m in u.meetings
        },
        room={
            m.id: next(r for r, v in z[m.id].items() if solver.Value(v)) for m in u.meetings
        },
    )
    return SolveResult(
        name, assignment, int(solver.ObjectiveValue()), solver.WallTime(), profile
    )


def _or_var(model, run, nxt, name):
    if nxt is None:
        return run
    if run is None:
        return nxt
    v = model.NewBoolVar(name)
    model.AddMaxEquality(v, [run, nxt])
    return v
