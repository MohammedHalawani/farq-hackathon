from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from api.state import SESSION
from core.metrics import ACCESSIBLE_TRANSIT_LIMIT, student_day_meetings
from core.models import DAYS, DAYS_AR, FIRST_HOUR, N_PERIODS, slot_day, slot_period

WEB = Path(__file__).resolve().parent.parent / "web"

app = FastAPI(title="Smart University Scheduling Agent")


@app.get("/api/meta")
def meta() -> dict:
    u = SESSION.u
    return {
        "days": DAYS,
        "days_ar": DAYS_AR,
        "periods": [f"{FIRST_HOUR + p:02d}:00" for p in range(N_PERIODS)],
        "accessible_transit_limit": ACCESSIBLE_TRANSIT_LIMIT,
        "counts": {
            "students": len(u.students),
            "sections": len(u.sections),
            "rooms": len(u.rooms),
            "instructors": len(u.instructors),
            "repeaters": sum(1 for s in u.students if s.is_repeater),
            "needs_accessibility": sum(1 for s in u.students if s.needs_accessibility),
        },
    }


@app.post("/api/generate")
def generate() -> dict:
    with SESSION.lock:
        return SESSION.generate_all()


@app.get("/api/progress")
def progress() -> dict:
    """Real progress, not a guess: one tick per profile actually solved."""
    return SESSION.progress


@app.get("/api/entities")
def entities() -> dict:
    u = SESSION.u
    return {
        "instructors": [
            {"id": i.id, "name": i.name, "sections": len(
                [s for s in u.sections if s.instructor_id == i.id])}
            for i in u.instructors
        ],
        "rooms": [
            {
                "id": r.id,
                "building": r.building_id,
                "capacity": r.capacity,
                "accessible": r.accessible,
            }
            for r in u.rooms
        ],
        "cohorts": [{"id": c, "name": c} for c in u.cohorts],
        "sections": [
            {
                "id": s.id,
                "course": u.course_by_id[s.course_id].name,
                "course_ar": u.course_by_id[s.course_id].name_ar,
                "cohort": s.cohort,
                "instructor": u.instructor_by_id[s.instructor_id].name,
                "enrollment": s.enrollment,
            }
            for s in u.sections
        ],
        "students": [
            {
                "id": s.id,
                "name": s.name,
                "cohort": f"{s.department}-L{s.level}",
                "repeater": s.is_repeater,
                "needs_accessibility": s.needs_accessibility,
            }
            for s in u.students
        ],
        "featured": _featured(),
    }


def _featured() -> dict:
    """A repeater and an accessibility student who both suffered in the baseline."""
    u, base = SESSION.u, SESSION.baseline
    from core.metrics import student_conflicts, student_transits

    repeater = max(
        (s for s in u.students if s.is_repeater),
        key=lambda s: student_conflicts(u, base, s.id),
        default=None,
    )
    def access_pain(s):
        t = student_transits(u, base, s.id)
        return max(t) if t else 0

    access = max(
        (s for s in u.students if s.needs_accessibility), key=access_pain, default=None
    )
    return {
        "repeater": repeater.id if repeater else None,
        "needs_accessibility": access.id if access else None,
    }


def _which(assignment_name: str):
    if assignment_name == "baseline":
        return SESSION.baseline
    if SESSION.current is None:
        raise HTTPException(409, "Generate a schedule first.")
    return SESSION.current


@app.get("/api/schedule/{entity_type}/{entity_id}")
def schedule(entity_type: str, entity_id: str, source: str = "current") -> dict:
    u = SESSION.u
    a = _which(source)
    meeting_ids = _meetings_for(entity_type, entity_id)
    cells = []
    for mid in meeting_ids:
        if mid not in a.slot:
            continue
        m = u.meeting_by_id[mid]
        sec = u.section_by_id[m.section_id]
        room = u.room_by_id[a.room[mid]]
        cells.append(
            {
                "meeting_id": mid,
                "section_id": sec.id,
                "course": u.course_by_id[sec.course_id].name,
                "course_ar": u.course_by_id[sec.course_id].name_ar,
                "instructor": u.instructor_by_id[sec.instructor_id].name,
                "cohort": sec.cohort,
                "enrollment": sec.enrollment,
                "room": room.id,
                "building": room.building_id,
                "capacity": room.capacity,
                "accessible": room.accessible,
                "day": slot_day(a.slot[mid]),
                "period": slot_period(a.slot[mid]),
                "conflict": False,
                "accessibility_issue": None,
            }
        )
    _annotate(entity_type, entity_id, a, cells)
    return {"entity_type": entity_type, "entity_id": entity_id, "cells": cells}


def _meetings_for(entity_type: str, entity_id: str) -> list[str]:
    u = SESSION.u
    if entity_type == "student":
        st = u.student_by_id.get(entity_id)
        if st is None:
            raise HTTPException(404, "Unknown student")
        return [m.id for sid in st.section_ids for m in u.meetings_of_section[sid]]
    if entity_type == "cohort":
        return [
            m.id
            for s in u.sections
            if entity_id in u.serving_cohorts[s.id]
            for m in u.meetings_of_section[s.id]
        ]
    if entity_type == "instructor":
        return [
            m.id
            for s in u.sections
            if s.instructor_id == entity_id
            for m in u.meetings_of_section[s.id]
        ]
    if entity_type == "room":
        return [m.id for m in u.meetings]
    if entity_type == "section":
        return [m.id for m in u.meetings_of_section.get(entity_id, [])]
    raise HTTPException(404, "Unknown entity type")


def _annotate(entity_type: str, entity_id: str, a, cells: list[dict]) -> None:
    u = SESSION.u
    if entity_type == "room":
        cells[:] = [c for c in cells if c["room"] == entity_id]
    seen: dict[tuple[int, int], list[dict]] = {}
    for c in cells:
        seen.setdefault((c["day"], c["period"]), []).append(c)
    for group in seen.values():
        if len(group) > 1:
            for c in group:
                c["conflict"] = True

    if entity_type != "student":
        return
    st = u.student_by_id[entity_id]
    need = st.needs_accessibility
    by_meeting = {c["meeting_id"]: c for c in cells}
    for c in cells:
        if need and not c["accessible"]:
            c["accessibility_issue"] = "inaccessible room"
    if not need:
        return
    for _, ms in student_day_meetings(u, a, entity_id).items():
        for (p1, r1, m1), (p2, r2, m2) in zip(ms, ms[1:]):
            if p2 - p1 != 1:
                continue
            mins = u.walk_minutes(r1, r2)
            if mins > ACCESSIBLE_TRANSIT_LIMIT:
                for mid in (m1, m2):
                    if mid in by_meeting:
                        by_meeting[mid]["accessibility_issue"] = f"{mins} min transit"


@app.get("/api/changes")
def changes() -> dict:
    return {"versions": SESSION.change_log(), "constraints": SESSION.constraints}


class Message(BaseModel):
    message: str


@app.post("/api/agent/message")
def agent_message(body: Message) -> dict:
    from agent.agent import AGENT

    with SESSION.lock:
        SESSION.chat.append({"role": "admin", "text": body.message})
        try:
            out = AGENT.handle(body.message, SESSION, SESSION.history)
        except Exception as e:
            note = f"The assistant failed: {type(e).__name__}: {e}"
            SESSION.chat.append({"role": "agent", "text": note})
            return {"reply": note, "card": None, "error": True}
        SESSION.history = out["history"]
        SESSION.pending = out["card"]
        SESSION.chat.append({"role": "agent", "text": out["reply"]})
        return {"reply": out["reply"], "card": out["card"], "offline": out["offline"]}


@app.get("/api/agent/state")
def agent_state() -> dict:
    return {"chat": SESSION.chat, "card": SESSION.pending}


@app.post("/api/agent/reset")
def agent_reset() -> dict:
    with SESSION.lock:
        SESSION.chat, SESSION.history, SESSION.pending = [], [], None
    return {"ok": True}


class ApplyBody(BaseModel):
    constraint: dict | None = None


@app.post("/api/changes/apply")
def apply_change(body: ApplyBody) -> dict:
    from agent.describe import short_label

    with SESSION.lock:
        c = body.constraint or (SESSION.pending or {}).get("constraint")
        if c is None:
            raise HTTPException(400, "Nothing to apply.")
        if SESSION.current is None:
            raise HTTPException(409, "Generate a schedule first.")
        result = SESSION.apply_constraint(c, short_label(SESSION.u, c))
        if result["ok"]:
            SESSION.pending = None
        return result


@app.post("/api/changes/undo")
def undo() -> dict:
    with SESSION.lock:
        return SESSION.undo()


@app.get("/")
def index() -> FileResponse:
    return FileResponse(WEB / "index.html")


app.mount("/", StaticFiles(directory=WEB), name="web")
