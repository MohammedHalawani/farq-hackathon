from __future__ import annotations

import re
from pathlib import Path
from urllib.parse import unquote

from email.parser import BytesParser
from email.policy import HTTP

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from agent.trace import for_apply, for_message
from agent.catalog import RULE_TYPES, unavailable_line
from agent.catalog import as_payload as rules_catalog
from api.state import SESSION, BuildError
from core.metrics import (
    ACCESSIBLE_TRANSIT_LIMIT,
    problem_labels,
    student_day_meetings,
)
from core.models import DAYS, DAYS_AR, FIRST_HOUR, N_PERIODS, slot_day, slot_period
from data.excel_io import export_template, export_timetable, load_workbook
from data.generator import PERSONAS, generate as generate_demo

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
        # rule types, built-in rules and the "You can ask for" menu, from one place
        "rules": rules_catalog(),
        "counts": {
            "students": len(u.students),
            "sections": len(u.sections),
            "rooms": len(u.rooms),
            "instructors": len(u.instructors),
            "repeaters": sum(1 for s in u.students if s.is_repeater),
            "needs_accessibility": sum(1 for s in u.students if s.needs_accessibility),
            "courses": len(u.courses),
            "levels": len({(c.department, c.level) for c in u.courses}),
            "buildings": len(u.buildings),
        },
        "data": _data_state(),
    }


def _data_state() -> dict:
    return {
        "source": SESSION.source,
        "is_demo": SESSION.is_demo,
        "report": SESSION.report,
        "built": SESSION.current is not None,
        "build_seconds": SESSION.build_seconds,
        "setup_rules": SESSION.setup_rules() if SESSION.current is None else [],
    }


@app.post("/api/generate")
def generate() -> dict:
    with SESSION.lock:
        try:
            return SESSION.generate_all()
        except BuildError as e:
            raise HTTPException(422, str(e))


XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def _xlsx(data: bytes, filename: str) -> Response:
    return Response(
        data, media_type=XLSX,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@app.get("/api/data/template")
def data_template() -> Response:
    """The demo campus as the coordinator's workbook: fill it in, or upload it
    straight back."""
    return _xlsx(export_template(generate_demo()), "jadwal-template.xlsx")


def _file_from(body: bytes, content_type: str) -> tuple[bytes, str]:
    """A raw .xlsx body, or the first file of a multipart form (parsed with the
    standard library, so no extra dependency)."""
    if not content_type.startswith("multipart/"):
        return body, "upload.xlsx"
    msg = BytesParser(policy=HTTP).parsebytes(
        f"Content-Type: {content_type}\r\n\r\n".encode() + body
    )
    for part in msg.iter_parts():
        if part.get_filename():
            return part.get_payload(decode=True) or b"", part.get_filename()
    raise HTTPException(400, "No file in the upload.")


@app.post("/api/data/upload")
async def data_upload(request: Request) -> dict:
    body = await request.body()
    if not body:
        raise HTTPException(400, "Empty upload.")
    data, name = _file_from(body, request.headers.get("content-type", ""))
    name = unquote(request.headers.get("x-filename", "")) or name
    u, report = load_workbook(data)
    report["filename"] = name
    if u is None:
        # nothing replaced: the current campus stays loaded
        return {"ok": False, "report": report, "data": _data_state()}
    with SESSION.lock:
        try:
            SESSION.load(u, is_demo=False, report=report, source=name)
        except RuntimeError as e:
            report["ok"] = False
            report["errors"].append({
                "sheet": None, "row": None,
                "en": f"the data cannot be laid out at all: {e}",
                "ar": f"تعذّر ترتيب البيانات في أي جدول: {e}",
            })
            return {"ok": False, "report": report, "data": _data_state()}
    return {"ok": True, "report": report, "data": _data_state(), "counts": meta()["counts"]}


@app.get("/api/data/export")
def data_export() -> Response:
    """The current version of the timetable, ready to hand to the supervisor."""
    if SESSION.current is None:
        raise HTTPException(409, "No timetable built yet — build it first.")
    v = len(SESSION.versions) - 1
    return _xlsx(export_timetable(SESSION.u, SESSION.current), f"jadwal-timetable-v{v}.xlsx")


@app.post("/api/data/reset")
def data_reset() -> dict:
    with SESSION.lock:
        SESSION.load(generate_demo(), is_demo=True)
    return {"ok": True, "data": _data_state(), "counts": meta()["counts"]}


@app.get("/api/setup/rules")
def setup_rules() -> dict:
    return {"rules": SESSION.setup_rules() if SESSION.current is None else [],
            "built": SESSION.current is not None}


@app.delete("/api/setup/rules/{index}")
def remove_setup_rule(index: int) -> dict:
    with SESSION.lock:
        return SESSION.remove_setup_rule(index)


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
        "personas": _personas(),
    }


def _personas() -> list[dict]:
    """The three pinned faces, with a tag computed from the real data. They
    exist only on the built-in demo campus."""
    if not SESSION.is_demo:
        return []
    u = SESSION.u
    out = []
    for eid, (name, name_en, kind) in PERSONAS.items():
        if kind == "instructor":
            n = sum(
                len(u.meetings_of_section[s.id])
                for s in u.sections
                if s.instructor_id == eid
            )
            out.append({
                "id": eid, "entity_type": "instructor", "kind": kind,
                "name": name, "name_en": name_en, "initial": name_en[4:5] or name[0],
                "tag_en": f"instructor · {n} meetings a week",
                "tag_ar": f"مدرّس · {n} محاضرة أسبوعيًا",
            })
            continue
        st = u.student_by_id[eid]
        cohort = f"{st.department}-L{st.level}"
        if kind == "accessibility":
            tag_en, tag_ar = "needs accessible rooms", "تحتاج قاعات مهيّأة"
        else:
            lower = [
                s for s in st.section_ids if u.section_by_id[s].level < st.level
            ]
            course = u.course_by_id[u.section_by_id[lower[0]].course_id]
            tag_en = f"repeating {course.name}"
            tag_ar = f"معيد لمقرر {course.name_ar}"
        out.append({
            "id": eid, "entity_type": "student", "kind": kind,
            "name": name, "name_en": name_en, "initial": name_en[0],
            "cohort": cohort, "tag_en": tag_en, "tag_ar": tag_ar,
        })
    return out


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
    labels = problem_labels(u, a, entity_type, entity_id)
    for c in cells:
        c["problems"] = labels.get(c["meeting_id"], [])
    return {
        "entity_type": entity_type,
        "entity_id": entity_id,
        "source": source,
        "cells": cells,
        "problem_count": sum(len(c["problems"]) for c in cells),
    }


def _meetings_for(entity_type: str, entity_id: str) -> list[str]:
    u = SESSION.u
    if entity_type == "student":
        st = u.student_by_id.get(entity_id)
        if st is None:
            raise HTTPException(404, "Unknown student")
        return [m.id for sid in st.section_ids for m in u.meetings_of_section[sid]]
    if entity_type == "cohort":
        # everything this cohort's students actually attend, which is what
        # explain_gap and problem_labels reason over — including the extra
        # lower-level course a repeater carries
        sections: list[str] = []
        for st in u.students:
            if f"{st.department}-L{st.level}" != entity_id:
                continue
            for sid in st.section_ids:
                if sid not in sections:
                    sections.append(sid)
        return [m.id for sid in sorted(sections) for m in u.meetings_of_section[sid]]
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
        # a request no rule type covers gets a line written here, not by the model
        status_line = SESSION.say(*unavailable_line()) if matched_nothing(out) else None
        trace = (
            []
            if out["offline"]
            else for_message(SESSION.u, body.message, out["tools"], out["card"])
        )
        return {
            "reply": out["reply"],
            "card": out["card"],
            "offline": out["offline"],
            "trace": trace,
            "overlay": out.get("overlay"),
            "choices": out.get("choices"),
            "status_line": status_line,
        }


# tools that answer a question: a turn that used one was not an unsupported rule
ANSWERING_TOOLS = {"explain_gap", "explain_meeting", "get_schedule", "get_metrics", "what_if"}
_REFUSALS_EN = re.compile(
    r"not (?:yet )?(?:supported|available|possible)|isn't (?:supported|available|possible)|"
    r"(?:can't|cannot|can not|unable to) (?:add|set|create|record|express|handle|support)|"
    r"(?:don't|do not|doesn't|does not) (?:have|support) (?:a|any|that|this)|"
    r"no (?:rule|constraint) (?:type )?(?:for|that|covers)",
    re.IGNORECASE,
)
_REFUSALS_AR = ("غير مدعوم", "غير متاح", "غير متوفر", "لا يمكنني", "لا استطيع",
                "لا يمكن اضافه", "لا يمكن تطبيق", "لا يتوفر", "لا تتوفر", "ليس من ضمن",
                "ليست من ضمن", "خارج نطاق", "لا يوجد نوع", "لا توجد قاعده", "لا يوجد قيد")


def _fold(text: str) -> str:
    text = re.sub("[\u064b-\u0652\u0640]", "", text)
    return re.sub("[إأآ]", "ا", text).replace("ة", "ه").replace("ى", "ي")


def matched_nothing(out: dict) -> bool:
    """True when the request matched no rule type: nothing proposed, nothing
    previewed or explained, no name left unclear, and either a proposal failed
    on an unknown type or the model's reply says it cannot do it."""
    if out.get("offline") or out.get("card") or out.get("choices"):
        return False
    tools = out.get("tools")
    calls = getattr(tools, "calls", [])
    if any(name in ANSWERING_TOOLS for name, _ in calls):
        return False
    if any(l["vague"] or l["count"] != 1 for l in getattr(tools, "lookups", [])):
        return False                         # it is asking which one, or not found
    unknown_type = any(
        name == "propose_constraint"
        and (args.get("constraint") or {}).get("type") not in RULE_TYPES
        for name, args in calls
    )
    reply = out.get("reply") or ""
    return unknown_type or bool(_REFUSALS_EN.search(reply)) or any(
        r in _fold(reply) for r in _REFUSALS_AR
    )


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
        result = SESSION.apply_constraint(c, short_label(SESSION.u, c))
        if result["ok"]:
            SESSION.pending = None
        result["trace"] = for_apply(SESSION.u, c, result, len(SESSION.u.meetings))
        return result


@app.post("/api/changes/undo")
def undo() -> dict:
    with SESSION.lock:
        return SESSION.undo()


@app.get("/")
def index() -> FileResponse:
    return FileResponse(WEB / "index.html")


app.mount("/", StaticFiles(directory=WEB), name="web")
