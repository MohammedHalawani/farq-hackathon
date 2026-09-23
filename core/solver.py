from __future__ import annotations

from dataclasses import dataclass, field
from itertools import zip_longest

from ortools.sat.python import cp_model

from core.metrics import ACCESSIBLE_TRANSIT_LIMIT, COMFORT_WALK_LIMIT
from core.warmstart import build as greedy_start
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
import os

_TRACE = bool(os.environ.get("SOLVER_TRACE"))
ROUND_DET_TIME = 0.8
DEFAULT_ROUNDS = 13
# Re-solves after a confirmed change use fewer rounds so the admin is not kept
# waiting. what_if and apply MUST use the same value or the preview would lie.
CHANGE_ROUNDS = 4  # per-neighbourhood budget; single-worker, so reproducible


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


def _build_model(
    u: University,
    profile: str,
    constraints: list[dict],
    allowed_slots: dict[str, set[int]],
    allowed_rooms: dict[str, list[str]],
    base: Assignment | None,
    minimal_change: bool,
) -> "_Model":
    w = PROFILES[profile]
    max_daily = {
        c["instructor_id"]: c["max_classes"]
        for c in constraints
        if c["type"] == "instructor_max_daily"
    }
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

    adj_cache: dict[tuple[str, str], cp_model.IntVar] = {}

    def adjacency(m1: str, m2: str) -> cp_model.IntVar:
        """True when the two meetings sit in back-to-back periods of one day."""
        key = (m1, m2) if m1 < m2 else (m2, m1)
        if key in adj_cache:
            return adj_cache[key]
        a1, a2 = key
        sd = model.NewBoolVar(f"sd_{a1}_{a2}")
        model.Add(day_var[a1] != day_var[a2]).OnlyEnforceIf(sd.Not())
        gap_abs = model.NewIntVar(0, N_PERIODS - 1, f"pd_{a1}_{a2}")
        model.AddAbsEquality(gap_abs, per_var[a1] - per_var[a2])
        nb = model.NewBoolVar(f"nb_{a1}_{a2}")
        model.Add(gap_abs != 1).OnlyEnforceIf(nb.Not())
        a = model.NewBoolVar(f"adj_{a1}_{a2}")
        model.Add(a >= sd + nb - 1)
        adj_cache[key] = a
        return a

    # period of each meeting on a given day, or a sentinel when it is elsewhere
    pe_min: dict[tuple[str, int], cp_model.IntVar] = {}
    pe_max: dict[tuple[str, int], cp_model.IntVar] = {}
    for m in u.meetings:
        for d in range(N_DAYS):
            here = [v for s, v in y[m.id].items() if slot_day(s) == d]
            lo = model.NewIntVar(0, N_PERIODS - 1, f"lo_{m.id}_{d}")
            hi = model.NewIntVar(0, N_PERIODS - 1, f"hi_{m.id}_{d}")
            if not here:
                model.Add(lo == N_PERIODS - 1)
                model.Add(hi == 0)
            else:
                on = model.NewBoolVar(f"on_{m.id}_{d}")
                model.Add(sum(here) == 1).OnlyEnforceIf(on)
                model.Add(sum(here) == 0).OnlyEnforceIf(on.Not())
                model.Add(lo == per_var[m.id]).OnlyEnforceIf(on)
                model.Add(lo == N_PERIODS - 1).OnlyEnforceIf(on.Not())
                model.Add(hi == per_var[m.id]).OnlyEnforceIf(on)
                model.Add(hi == 0).OnlyEnforceIf(on.Not())
            pe_min[(m.id, d)] = lo
            pe_max[(m.id, d)] = hi
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
                if u.meeting_by_id[m1].section_id == u.meeting_by_id[m2].section_id:
                    continue  # the two meetings of a section are on different days
                adj = adjacency(m1, m2)
                far = model.NewBoolVar(f"far_{m1}_{m2}")
                hit = False
                for b1, v1 in in_building[m1].items():
                    for b2, v2 in in_building[m2].items():
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
        for d in range(N_DAYS):
            first = model.NewIntVar(0, N_PERIODS - 1, f"first_{id(g)}_{d}")
            last = model.NewIntVar(0, N_PERIODS - 1, f"last_{id(g)}_{d}")
            model.AddMinEquality(first, [pe_min[(mid, d)] for mid in mids])
            model.AddMaxEquality(last, [pe_max[(mid, d)] for mid in mids])
            count = sum(
                y[mid][s] for mid in mids for s in y[mid] if slot_day(s) == d
            )
            idle = model.NewIntVar(0, N_PERIODS, f"idle_{id(g)}_{d}")
            model.Add(idle >= last - first + 1 - count)
            penalties.append((w["idle"] * g.size, idle))

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

    obj: list = [weight * var for weight, var in penalties]
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

    total = model.NewIntVar(0, 2**40, "objective")
    model.Add(total == sum(obj))
    model.Minimize(total)

    return _Model(model, y, z, total, max_daily)


@dataclass
class _Model:
    model: cp_model.CpModel
    y: dict[str, dict[int, cp_model.IntVar]]
    z: dict[str, dict[str, cp_model.IntVar]]
    total: cp_model.IntVar
    max_daily: dict[str, int]

    def pin(self, target: cp_model.CpModel, mid: str, slot: int, room: str) -> None:
        """Force a meeting to a slot and room by index, straight on the proto."""
        for var in (self.y[mid][slot], self.z[mid][room]):
            ct = target.Proto().constraints.add()
            ct.linear.vars.append(var.Index())
            ct.linear.coeffs.append(1)
            ct.linear.domain.extend([1, 1])

    def read(self, solver: cp_model.CpSolver, u: University) -> Assignment:
        return Assignment(
            slot={
                m.id: next(s for s, v in self.y[m.id].items() if solver.Value(v))
                for m in u.meetings
            },
            room={
                m.id: next(r for r, v in self.z[m.id].items() if solver.Value(v))
                for m in u.meetings
            },
        )

    def score(self, a: Assignment, u: University) -> int | None:
        """Objective value of a complete assignment, priced by CP-SAT itself."""
        self.model.ClearHints()
        for m in u.meetings:
            if a.slot.get(m.id) not in self.y[m.id] or a.room.get(m.id) not in self.z[m.id]:
                return None
            self.model.AddHint(self.y[m.id][a.slot[m.id]], 1)
            self.model.AddHint(self.z[m.id][a.room[m.id]], 1)
        probe = cp_model.CpSolver()
        probe.parameters.fix_variables_to_their_hinted_value = True
        probe.parameters.num_workers = 1
        probe.parameters.max_time_in_seconds = 10.0
        st = probe.Solve(self.model)
        self.model.ClearHints()
        if st not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
            return None
        return int(probe.ObjectiveValue())


def _neighborhoods(u: University, cur: Assignment) -> list[set[str]]:
    """The meeting sets CP-SAT re-optimises, interleaved so a short run still
    sees every kind of neighbourhood."""
    days: list[set[str]] = []
    for d in range(N_DAYS):
        days.append({m for m, s in cur.slot.items() if slot_day(s) == d})
    per_instructor: list[set[str]] = []
    per_cohort: list[set[str]] = []
    by_instructor: dict[str, set[str]] = {}
    for m in u.meetings:
        by_instructor.setdefault(
            u.section_by_id[m.section_id].instructor_id, set()
        ).add(m.id)
    insts = sorted(by_instructor)
    for i in range(0, len(insts), 2):
        free: set[str] = set()
        for inst in insts[i : i + 2]:
            free |= by_instructor[inst]
        per_instructor.append(free)
    for cohort in u.cohorts:
        free = {
            m.id
            for sec in u.sections
            if cohort in u.serving_cohorts[sec.id]
            for m in u.meetings_of_section[sec.id]
        }
        if free:
            per_cohort.append(free)

    out: list[set[str]] = []
    for group in zip_longest(days, per_instructor, per_cohort):
        out += [f for f in group if f]
    return out


def solve(
    u: University,
    profile: str = "balanced",
    constraints: list[dict] | None = None,
    base: Assignment | None = None,
    time_limit: float = 30.0,
    minimal_change: bool = False,
    hint_from: Assignment | None = None,
    rounds: int | None = None,
    on_round=None,
) -> SolveResult:
    """Constructive warm start, then CP-SAT re-optimises one neighbourhood at a
    time. Every round is solved to optimality by a single worker, so the whole
    search is reproducible run to run.
    """
    import time as _time

    started = _time.time()
    constraints = constraints or []
    w = PROFILES[profile]

    allowed_slots = _allowed_slots(u, constraints)
    allowed_rooms = _allowed_rooms(u, constraints)
    for m in u.meetings:
        if not allowed_slots[m.id] or not allowed_rooms[m.id]:
            sec = u.section_by_id[m.section_id]
            course = u.course_by_id[sec.course_id]
            lack = "slot" if not allowed_slots[m.id] else "room"
            return SolveResult(
                "INFEASIBLE", None, None, 0.0, profile,
                message=(
                    f"{course.name} ({sec.id}, {u.instructor_by_id[sec.instructor_id].name}) "
                    f"has no {lack} left under these rules."
                ),
            )

    built = _build_model(
        u, profile, constraints, allowed_slots, allowed_rooms, base, minimal_change
    )

    starts = [c for c in (base, hint_from) if c is not None]
    if base is not None:
        # repair the schedule we have before considering a rebuild
        starts.append(
            greedy_start(u, allowed_slots, allowed_rooms, built.max_daily, w, keep=base)
        )
    starts.append(greedy_start(u, allowed_slots, allowed_rooms, built.max_daily, w))
    cur: Assignment | None = None
    cur_obj: int | None = None
    for cand in starts:
        if cand is None:
            continue
        value = built.score(cand, u)
        if value is not None and (cur_obj is None or value < cur_obj):
            cur, cur_obj = cand, value

    if cur is None:
        # No usable starting point: let CP-SAT look for one from scratch.
        solver = cp_model.CpSolver()
        solver.parameters.max_time_in_seconds = time_limit
        solver.parameters.num_workers = 8
        status = solver.Solve(built.model)
        if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
            return SolveResult(
                "INFEASIBLE", None, None, _time.time() - started, profile,
                message="No schedule satisfies these constraints.",
            )
        return SolveResult(
            solver.StatusName(status), built.read(solver, u),
            int(solver.ObjectiveValue()), _time.time() - started, profile,
        )

    hoods = _neighborhoods(u, cur)[: DEFAULT_ROUNDS if rounds is None else rounds]
    improved = 0
    for free in hoods:
        # No wall-clock cutoff here on purpose: the number of rounds is what
        # makes a solve reproducible. A busy machine takes longer, not a
        # different answer.
        round_model = cp_model.CpModel()
        round_model.Proto().copy_from(built.model.Proto())
        hint = round_model.Proto().solution_hint
        for m in u.meetings:
            if m.id in free:
                hint.vars.append(built.y[m.id][cur.slot[m.id]].Index())
                hint.values.append(1)
                hint.vars.append(built.z[m.id][cur.room[m.id]].Index())
                hint.values.append(1)
            else:
                built.pin(round_model, m.id, cur.slot[m.id], cur.room[m.id])
        # never accept a round that is worse than what we already hold
        ct = round_model.Proto().constraints.add()
        ct.linear.vars.append(built.total.Index())
        ct.linear.coeffs.append(1)
        ct.linear.domain.extend([0, cur_obj])
        solver = cp_model.CpSolver()
        solver.parameters.num_workers = 1
        solver.parameters.max_deterministic_time = ROUND_DET_TIME
        solver.parameters.max_time_in_seconds = ROUND_DET_TIME * 10
        status = solver.Solve(round_model)
        if _TRACE:
            print(f"   round free={len(free):3d} {solver.StatusName(status):9}"
                  f" {solver.WallTime():5.1f}s det={solver.deterministic_time:4.1f}"
                  f" obj={solver.ObjectiveValue() if status in (cp_model.OPTIMAL, cp_model.FEASIBLE) else None}"
                  f" cur={cur_obj}", flush=True)
        if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
            continue
        value = int(solver.ObjectiveValue())
        if value < cur_obj:
            cur, cur_obj = built.read(solver, u), value
            improved += 1
        if on_round is not None:
            on_round()

    # Not a proven optimum: neighbourhood search returns the best schedule it
    # reached, and every round is guaranteed not to make it worse.
    return SolveResult(
        "IMPROVED" if improved else "FEASIBLE", cur, cur_obj,
        _time.time() - started, profile,
        message=f"{improved} of {len(hoods)} neighbourhoods improved",
    )
