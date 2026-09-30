from __future__ import annotations

import hashlib
import json
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from core.baseline import build_baseline
from core.metrics import compute, delta, moved_meetings
from core.models import DAYS, DAYS_AR, FIRST_HOUR, Assignment, University, slot_day, slot_period
from core.solver import CHANGE_ROUNDS, DEFAULT_ROUNDS, PROFILES, solve
from data.generator import generate

CACHE = Path(".cache")


def _where(slot: int | None, room: str | None) -> dict | None:
    if slot is None or room is None:
        return None
    return {
        "day": DAYS[slot_day(slot)],
        "day_ar": DAYS_AR[slot_day(slot)],
        "day_index": slot_day(slot),
        "period": slot_period(slot),
        "hour": f"{FIRST_HOUR + slot_period(slot):02d}:00",
        "room": room,
    }


@dataclass
class Version:
    index: int
    label: str
    constraint: dict | None
    assignment: Assignment
    metrics: dict
    at: str
    moved: list[str] = field(default_factory=list)
    deltas: dict = field(default_factory=dict)
    moves: list[dict] = field(default_factory=list)


class Session:
    """Everything the demo holds in memory: one university, one live schedule."""

    def __init__(self) -> None:
        self.lock = threading.Lock()
        self._plock = threading.Lock()
        self.load(generate(), is_demo=True)

    def load(self, u: University, is_demo: bool, report: dict | None = None,
             source: str = "demo") -> None:
        """Start over on a campus: the built-in demo or an uploaded workbook.
        The baseline is built first, so a campus it cannot place leaves the
        session untouched."""
        baseline = build_baseline(u)
        self.u = u
        self.is_demo = is_demo
        self.report = report
        self.source = source
        self.baseline: Assignment = baseline
        self.baseline_metrics = compute(self.u, self.baseline)
        self._campus_key = campus_key(u)
        self.profiles: dict[str, dict] = {}
        self.active_profile = "balanced"
        self.versions: list[Version] = []
        self.constraints: list[dict] = []
        self.pending: dict | None = None
        self.chat: list[dict] = []
        self.history: list = []
        self.build_seconds: float | None = None
        self.progress: dict = {
            "stage": "idle", "done": 0, "total": 0, "solved": [],
            "rounds_done": 0, "rounds_total": 0,
        }

    # --- schedules -----------------------------------------------------
    @property
    def current(self) -> Assignment | None:
        return self.versions[-1].assignment if self.versions else None

    @property
    def current_metrics(self) -> dict:
        return self.versions[-1].metrics

    def generate_all(self) -> dict:
        if not self.profiles:
            started = time.time()
            self.progress = {
                "stage": "solving",
                "done": 0,
                "total": len(PROFILES),
                "solved": [],
                "rounds_done": 0,
                "rounds_total": len(PROFILES) * DEFAULT_ROUNDS,
            }
            try:
                with ThreadPoolExecutor(max_workers=3) as pool:
                    results = dict(
                        zip(PROFILES, pool.map(self._solve_profile, PROFILES))
                    )
            except BuildError:
                self.progress = {**self.progress, "stage": "failed"}
                raise
            self.profiles = results
            self.build_seconds = round(time.time() - started, 1)
            self.progress = {
                "stage": "done",
                "done": len(PROFILES),
                "total": len(PROFILES),
                "solved": list(PROFILES),
                "rounds_done": self.progress["rounds_total"],
                "rounds_total": self.progress["rounds_total"],
            }
        if not self.versions:
            self._push("Initial schedule", None, self.profiles[self.active_profile]["assignment"])
        return self.comparison()

    def _solve_profile(self, profile: str) -> dict:
        cached = self._read_cache(profile)
        if cached is not None:
            out = cached
        else:
            r = solve(self.u, profile, constraints=list(self.constraints),
                      time_limit=30, on_round=self._tick)
            if r.assignment is None:
                raise BuildError(r.message or "No schedule satisfies these rules.")
            out = {
                "assignment": r.assignment,
                "metrics": compute(self.u, r.assignment),
                "objective": r.objective,
                "seconds": round(r.wall_time, 1),
            }
            self._write_cache(profile, out)
        with self._plock:
            self.progress["done"] += 1
            self.progress["solved"] = self.progress["solved"] + [profile]
        return out

    def _tick(self) -> None:
        with self._plock:
            self.progress["rounds_done"] = self.progress.get("rounds_done", 0) + 1

    def _cache_path(self, profile: str) -> Path:
        # the whole campus and the setup rules, not just the section ids: an
        # uploaded file can reuse S01..S60 and must not load the demo's schedule
        key = hashlib.sha256(
            json.dumps(
                [profile, self._campus_key, self.constraints], sort_keys=True, default=str
            ).encode()
        ).hexdigest()[:16]
        return CACHE / f"{profile}-{key}.json"

    def _read_cache(self, profile: str) -> dict | None:
        p = self._cache_path(profile)
        if not p.exists():
            return None
        raw = json.loads(p.read_text())
        a = Assignment(raw["slot"], raw["room"])
        return {
            "assignment": a,
            "metrics": compute(self.u, a),
            "objective": raw["objective"],
            "seconds": raw["seconds"],
        }

    def _write_cache(self, profile: str, out: dict) -> None:
        CACHE.mkdir(exist_ok=True)
        self._cache_path(profile).write_text(
            json.dumps(
                {
                    "slot": out["assignment"].slot,
                    "room": out["assignment"].room,
                    "objective": out["objective"],
                    "seconds": out["seconds"],
                }
            )
        )

    def comparison(self) -> dict:
        return {
            "baseline": self.baseline_metrics,
            "profiles": {
                name: {
                    "metrics": v["metrics"],
                    "objective": v["objective"],
                    "seconds": v["seconds"],
                }
                for name, v in self.profiles.items()
            },
            "active_profile": self.active_profile,
            "version": len(self.versions) - 1 if self.versions else None,
            "build_seconds": self.build_seconds,
        }

    # --- versions ------------------------------------------------------
    def _push(
        self, label: str, constraint: dict | None, assignment: Assignment
    ) -> Version:
        before = self.current
        metrics = compute(self.u, assignment)
        v = Version(
            index=len(self.versions),
            label=label,
            constraint=constraint,
            assignment=assignment,
            metrics=metrics,
            at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
            moved=moved_meetings(before, assignment) if before else [],
            deltas=delta(self.versions[-1].metrics, metrics) if self.versions else {},
        )
        v.moves = self.move_list(before, assignment)
        self.versions.append(v)
        return v

    def apply_constraint(self, constraint: dict, label: str) -> dict:
        """Minimal-change re-solve. Reports the blocking constraints on failure.
        Before the first build there is nothing to re-solve: the rule is kept as
        a setup rule and every profile is built with it."""
        proposed = self.constraints + [constraint]
        if self.current is None:
            r = solve(self.u, self.active_profile, constraints=proposed, rounds=0)
            if r.assignment is None:
                return {
                    "ok": False,
                    "stage": "setup",
                    "message": r.message or "No schedule satisfies these rules.",
                    "blocking": self._blocking(constraint),
                }
            self.constraints = proposed
            self.profiles = {}
            return {"ok": True, "stage": "setup", "rules": self.setup_rules()}
        r = solve(
            self.u,
            self.active_profile,
            constraints=proposed,
            base=self.current,
            minimal_change=True,
            rounds=CHANGE_ROUNDS,
        )
        if r.assignment is None:
            return {
                "ok": False,
                "message": r.message or "No schedule satisfies these constraints.",
                "blocking": self._blocking(constraint),
            }
        self.constraints = proposed
        v = self._push(label, constraint, r.assignment)
        return {"ok": True, "version": self.version_payload(v)}

    def _blocking(self, new_constraint: dict) -> list[dict]:
        """Drop the user's constraints one at a time to find who conflicts."""
        out = []
        for i, c in enumerate(self.constraints):
            trial = [x for j, x in enumerate(self.constraints) if j != i]
            trial.append(new_constraint)
            r = solve(self.u, self.active_profile, constraints=trial, rounds=0)
            if r.assignment is not None:
                out.append(c)
        return out or [new_constraint]

    def remove_setup_rule(self, index: int) -> dict:
        if self.current is not None:
            return {"ok": False, "message": "The timetable is built; use undo instead."}
        if not 0 <= index < len(self.constraints):
            return {"ok": False, "message": "No such rule."}
        self.constraints.pop(index)
        return {"ok": True, "rules": self.setup_rules()}

    def setup_rules(self) -> list[dict]:
        from agent.describe import describe, short_label

        return [
            {"index": i, "constraint": c, "label": short_label(self.u, c),
             "describe": describe(self.u, c)}
            for i, c in enumerate(self.constraints)
        ]

    def undo(self) -> dict:
        if len(self.versions) <= 1:
            return {"ok": False, "message": "Nothing to undo."}
        dropped = self.versions.pop()
        if dropped.constraint in self.constraints:
            self.constraints.remove(dropped.constraint)
        restored = self.versions[-1]
        payload = self.version_payload(restored)
        # what undoing actually put back, so the grid can show it
        payload["moved"] = moved_meetings(dropped.assignment, restored.assignment)
        payload["moved_count"] = len(payload["moved"])
        payload["moves"] = self.move_list(dropped.assignment, restored.assignment)
        return {"ok": True, "version": payload}

    def move_list(self, before: Assignment | None, after: Assignment) -> list[dict]:
        """Each move in words: where it was, where it went."""
        if before is None:
            return []
        out = []
        for mid in moved_meetings(before, after):
            sec = self.u.section_by_id[self.u.meeting_by_id[mid].section_id]
            course = self.u.course_by_id[sec.course_id]
            fs, ts = before.slot.get(mid), after.slot[mid]
            out.append({
                "meeting_id": mid,
                "section_id": sec.id,
                "course": course.name,
                "course_ar": course.name_ar,
                "from": _where(fs, before.room.get(mid)),
                "to": _where(ts, after.room[mid]),
            })
        return out

    def version_payload(self, v: Version) -> dict:
        from agent.describe import describe

        return {
            "index": v.index,
            "label": v.label,
            "constraint": v.constraint,
            # both languages, built in Python, so the log reads in Arabic too
            "describe": describe(self.u, v.constraint) if v.constraint else None,
            "at": v.at,
            "metrics": v.metrics,
            "deltas": v.deltas,
            "moved": v.moved,
            "moved_count": len(v.moved),
            "moves": v.moves,
        }

    def change_log(self) -> list[dict]:
        return [self.version_payload(v) for v in self.versions]


def campus_key(u: University) -> str:
    """A fingerprint of everything a solve depends on. Order-independent, so
    a workbook that round-trips the demo campus shares its cache."""
    payload = {
        "sections": sorted(
            (s.id, s.course_id, s.instructor_id, s.enrollment,
             sorted(u.serving_cohorts.get(s.id, ())))
            for s in u.sections
        ),
        "courses": sorted((c.id, c.needs_lab) for c in u.courses),
        "rooms": sorted((r.id, r.building_id, r.capacity, r.accessible, r.kind)
                        for r in u.rooms),
        "instructors": sorted((i.id, sorted(i.unavailable_slots)) for i in u.instructors),
        "walk": sorted((a, b, m) for (a, b), m in u.walk.items()),
        "students": sorted(
            (sorted(s.section_ids), s.is_repeater, s.needs_accessibility)
            for s in u.students
        ),
        "meetings": sorted(m.id for m in u.meetings),
    }
    return hashlib.sha256(json.dumps(payload, default=str).encode()).hexdigest()


class BuildError(RuntimeError):
    """No schedule satisfies the campus and its setup rules."""


SESSION = Session()
