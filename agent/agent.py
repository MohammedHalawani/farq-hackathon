from __future__ import annotations

import json
import os
import re

from dotenv import load_dotenv

from agent.describe import describe, short_label
from agent.resolver import is_vague, one_course, resolve
from agent.schemas import CONSTRAINT_TOOL_SCHEMA, parse_constraint, to_day
from core.explain import explain_gap, explain_meeting, summarize_gap, summarize_meeting
from core.metrics import delta, moved_meetings
from core.models import DAYS, DAYS_AR, FIRST_HOUR, slot_day, slot_period
from core.solver import CHANGE_ROUNDS, solve

load_dotenv()

MODEL = os.environ.get("OLLAMA_MODEL", "gpt-oss:120b-cloud")
HOST = os.environ.get("OLLAMA_HOST", "http://localhost:11434")
MAX_STEPS = 8
MAX_TURNS = 8        # how much conversation the model is shown
MAX_TOOL_CHARS = 3000  # a tool result is evidence, not a document

SYSTEM = """You are the scheduling assistant for a university timetabling console.

HOW YOU WORK
- You act only through tools. You never edit the schedule yourself.
- Never state a number that did not come back from a tool. If you have not called a
  tool for it, you do not know it.
- Never invent or guess an ID. Every instructor, room, section, cohort and student ID
  must come from get_entity.
- Reply in the language the administrator wrote in (Arabic or English).
- Be brief. Two or three sentences unless asked for detail.

RESOLVING ENTITIES
Call get_entity for every person, room, section or cohort the administrator names.
- 0 matches  -> say you could not find it. Do not guess a near match.
- 2+ matches -> list them and ask which one. Do not pick one yourself.
- 1 match    -> use that ID and carry straight on. Never ask the administrator
               to confirm a single match, and never ask again for something the
               lookup already answered.
A department with a level ("عمارة المستوى الثاني", "BA year 3", "حاسب سنة أولى")
names one cohort: send the department and the level together in one query. A
department name is not a course.

WHAT THE ADMINISTRATOR IS ASKING FOR
- A rule to add ("X can't teach Tuesday afternoon", "close room B12", "د. ماجد
  ماله محاضرات الاثنين") -> call propose_constraint. A flat statement about when
  someone is or is not teaching is a rule to add, not a question about the
  current schedule. This only proposes: the administrator sees a confirmation
  card and decides. Say what you proposed and that it awaits confirmation.
- A hypothetical -> call what_if, which previews the effect without applying
  anything. The markers are "what if", "what would happen if", "try",
  "ماذا لو", "لو", "وش يصير لو", "جرّب لو", "إذا أغلقنا". If the sentence asks
  what *would* change, call what_if and never propose_constraint — the two are
  not interchangeable, and a hypothetical answered with a proposal is wrong.
- A question about the schedule ("why is there a gap", "ليش فيه فراغ", "why is this
  class here", "why only one class on Thursday", «ليش عندهم محاضرة وحدة بس يوم
  الخميس») -> call explain_gap (it also explains a one-class day) or
  explain_meeting, and phrase what comes back.
  These return the real blocking constraints; report them, do not speculate.

KINDS OF RULE
- "No classes at X for anyone" / "لا محاضرات من ١٢ إلى ١" / a prayer or lunch break
  for the whole campus -> campus_break with those hours, and the days only if the
  administrator named days (omit days for every day). It names no person, so do
  not call get_entity for it.
- "Course X needs a lab" / "مادة X تحتاج معمل" -> course_needs_lab with the course
  id. Look the course up with get_entity (kind "course").
- "Avoid days where a student comes in for only one class" / «لا تخلّون الطالب يجي
  ليوم فيه محاضرة وحدة» -> avoid_single_class_days: a preference the optimiser
  reduces, not a ban. Add `cohort` only if the administrator named one (look it
  up with get_entity); otherwise it covers every student.
- One person or one section -> instructor_unavailable, instructor_max_daily,
  section_avoid_slots, section_require_accessible. One room -> room_closed.

BEFORE THE FIRST BUILD
The administrator may state rules before any timetable exists. These are setup
rules: propose them exactly the same way, and say that once confirmed they are
applied when the timetable is built. Tools that read a timetable (what_if,
explain_gap, explain_meeting, get_schedule, get_metrics) answer "no timetable
built yet" until then — pass that on and tell the administrator to build first
(Data tab). Never invent an answer instead.

TIME
Teaching days are Sunday to Thursday; Friday and Saturday are the weekend and do
not exist. Give days by name ("Wednesday"); code converts them.
The teaching day runs 08:00 to 16:00. Give hours as clock times (24-hour
"HH:MM"); code converts them. Copy the times the administrator said; do not work
anything out.
- One hour, "at 8" / «الساعة ٨» -> at "08:00" (that hour only).
- "after 2" / «بعد ٢» -> from "14:00", until_end_of_day true.
- "before 10" / «قبل ١٠» -> to "10:00".
- "from 12 to 1" / «من ١٢ إلى ١» -> from "12:00", to "13:00".
- "morning" / «الصباح» -> to "12:00". "afternoon" / «بعد الظهر» -> from "12:00",
  until_end_of_day true.
- A whole day -> no times at all.
Never give `from` alone: say where it ends with `to` or until_end_of_day."""

RAW_TOOLS = [
    {
        "name": "get_entity",
        "description": (
            "Fuzzy-match a name the administrator typed against instructors, rooms, "
            "courses, sections, cohorts and students. Handles Arabic and English, and typos. "
            "Always use this before naming any ID."
        ),
        "input_schema": {
            "type": "object",
            "additionalProperties": False,
            "required": ["name_query"],
            "properties": {
                "name_query": {"type": "string"},
                "kind": {
                    "type": "string",
                    "enum": ["instructor", "room", "course", "section", "cohort", "student"],
                    "description": (
                        "Optional hint. A 'cohort' is a department and level "
                        "(BA-L3, «عمارة المستوى الثاني»): keep the department in the "
                        "query. A 'course' is one named subject (C04, Networks); a "
                        "'section' is one class group of it (S19). Omit it if unsure."
                    ),
                },
            },
        },
    },
    {
        "name": "propose_constraint",
        "description": (
            "Propose one scheduling rule for the administrator to confirm. Does NOT "
            "change the schedule. Use for any request to add a rule."
        ),
        "input_schema": {
            "type": "object",
            "additionalProperties": False,
            "required": ["constraint"],
            "properties": {"constraint": CONSTRAINT_TOOL_SCHEMA},
        },
    },
    {
        "name": "what_if",
        "description": (
            "Preview a rule: re-solves in the background and returns the metric changes "
            "and how many meetings would move. Applies nothing."
        ),
        "input_schema": {
            "type": "object",
            "additionalProperties": False,
            "required": ["constraint"],
            "properties": {"constraint": CONSTRAINT_TOOL_SCHEMA},
        },
    },
    {
        "name": "explain_gap",
        "description": (
            "Why a student or cohort has an idle gap on a given day. Returns the gap "
            "hours and, for each class next to it, the hard constraint that blocks "
            "moving it in, or what the move would cost."
        ),
        "input_schema": {
            "type": "object",
            "additionalProperties": False,
            "required": ["entity_id", "day"],
            "properties": {
                "entity_id": {"type": "string", "description": "A student ID or a cohort ID"},
                "day": {"type": "string", "description": "Day name, Sunday .. Thursday"},
            },
        },
    },
    {
        "name": "explain_meeting",
        "description": "Why one meeting sits in its current slot and room.",
        "input_schema": {
            "type": "object",
            "additionalProperties": False,
            "required": ["meeting_id"],
            "properties": {"meeting_id": {"type": "string", "description": "e.g. S12-m1"}},
        },
    },
    {
        "name": "get_schedule",
        "description": "The current weekly schedule for one instructor, room, section, cohort or student.",
        "input_schema": {
            "type": "object",
            "additionalProperties": False,
            "required": ["entity_type", "entity_id"],
            "properties": {
                "entity_type": {
                    "type": "string",
                    "enum": ["instructor", "room", "section", "cohort", "student"],
                },
                "entity_id": {"type": "string"},
            },
        },
    },
    {
        "name": "get_metrics",
        "description": "The current schedule's metrics, and the baseline's for comparison.",
        "input_schema": {
            "type": "object",
            "additionalProperties": False,
            "required": [],
            "properties": {},
        },
    },
]


TOOLS = [
    {
        "type": "function",
        "function": {
            "name": t["name"],
            "description": t["description"],
            "parameters": t["input_schema"],
        },
    }
    for t in RAW_TOOLS
]


NO_TIMETABLE = {
    "error": "No timetable built yet — build it first (Data tab, step 3). Rules "
    "proposed now are setup rules and are applied when the timetable is built."
}


class Tools:
    """Every tool runs deterministic Python. The model only chooses which to call."""

    def __init__(self, session, dry_run: bool = False) -> None:
        self.s = session
        self.card: dict | None = None
        self.dry_run = dry_run
        self.calls: list[tuple[str, dict]] = []
        self.lookups: list[dict] = []
        self.overlay: dict | None = None
        # candidates of the last ambiguous lookup, named as the database stores
        # them, so the choice the admin clicks never passes through the model
        self.choices: list[dict] | None = None
        # code-written explanations, shown first and verbatim in the reply
        self.lang = "en"
        self.summaries: list[str] = []

    def run(self, name: str, args: dict) -> dict:
        if name == "explain_gap" and "day" in args:
            # the day is a name the model copies, turned into a number by code
            try:
                args["day"] = to_day(args["day"])
            except ValueError as e:
                self.calls.append((name, args))
                return {"error": str(e)}
        self.calls.append((name, args))
        fn = getattr(self, f"t_{name}", None)
        if fn is None:
            return {"error": f"No tool named {name}."}
        try:
            return fn(**args)
        except Exception as e:
            return {"error": f"{type(e).__name__}: {e}"}

    def t_get_entity(self, name_query: str, kind: str | None = None) -> dict:
        matches = resolve(self.s.u, name_query, kind)
        vague = is_vague(name_query)
        course = one_course(matches)
        if course is not None:
            # a course and its own sections: one thing, named two ways
            self.lookups.append({"query": name_query, "count": 1, "vague": False})
            secs = [m["id"] for m in matches if m["kind"] == "section"]
            return {
                "query": name_query,
                "match_count": len(matches),
                "matches": matches,
                "note": (
                    f"One course, {course}, and its section(s) {', '.join(secs)}. "
                    f"For a rule about the whole course use course_id {course}. "
                    "For a rule about one section use its section id, and ask which "
                    "section only if there are several."
                ),
            }
        self.lookups.append({"query": name_query, "count": len(matches), "vague": vague})
        if len(matches) > 1 and not vague:
            self.choices = _choices(self.s.u, matches)
        return {
            "query": name_query,
            "match_count": len(matches),
            "matches": matches,
            "note": (
                "This names no specific person or place. Ask the administrator "
                "who or what they mean. Do NOT say it was not found."
                if vague
                else "No match. Tell the administrator it was not found."
                if not matches
                else (
                    f"Exactly one match: the {matches[0]['kind']} "
                    f"{matches[0]['id']}. Use that id and carry on with the "
                    "request. Do not ask the administrator to confirm it"
                    + (
                        f", and do not be put off that you searched for a "
                        f"{kind} — the hint was wrong, this is the entity they "
                        "meant."
                        if kind and kind != matches[0]["kind"]
                        else "."
                    )
                )
                if len(matches) == 1
                else "Ambiguous. Ask the administrator which one they mean."
            ),
        }

    def t_propose_constraint(self, constraint: dict) -> dict:
        c = parse_constraint(constraint)
        self._check_ids(c)
        self.card = {
            "kind": "confirm",
            "constraint": c,
            "describe": describe(self.s.u, c),
            "label": short_label(self.s.u, c),
        }
        return {
            "status": "awaiting_confirmation",
            "constraint": c,
            "card": self.card["describe"],
            "note": "Shown to the administrator as a confirmation card. Not applied. "
            + (
                "No timetable is built yet: once confirmed this is a setup rule, "
                "applied when the timetable is built."
                if self.s.current is None
                else "The timetable is already built: once confirmed, it is re-solved "
                "now with the smallest possible change. Do not say it waits for a build."
            ),
        }

    def t_what_if(self, constraint: dict) -> dict:
        c = parse_constraint(constraint)
        self._check_ids(c)
        if self.dry_run:
            return {"feasible": True, "meetings_moved": 0, "metric_changes": {},
                    "note": "Preview skipped (evaluation mode)."}
        if self.s.current is None:
            return NO_TIMETABLE
        r = solve(
            self.s.u,
            self.s.active_profile,
            constraints=self.s.constraints + [c],
            base=self.s.current,
            minimal_change=True,
            rounds=CHANGE_ROUNDS,
        )
        if r.assignment is None:
            blocking = self.s._blocking(c)
            self.card = {
                "kind": "what_if",
                "constraint": c,
                "describe": describe(self.s.u, c),
                "label": short_label(self.s.u, c),
                "feasible": False,
                "blocking": [short_label(self.s.u, b) for b in blocking],
            }
            return {
                "feasible": False,
                "message": "No schedule satisfies this together with the confirmed rules.",
                "conflicting_rules": self.card["blocking"],
            }
        from core.metrics import full_metrics

        after = full_metrics(self.s.u, r.assignment, self.s.constraints + [c])
        d = delta(self.s.current_metrics, after)
        moved = moved_meetings(self.s.current, r.assignment)
        self.card = {
            "kind": "what_if",
            "constraint": c,
            "describe": describe(self.s.u, c),
            "label": short_label(self.s.u, c),
            "feasible": True,
            "deltas": d,
            "moved_count": len(moved),
            "moved": moved,
            "moves": self.s.move_list(self.s.current, r.assignment),
        }
        return {
            "feasible": True,
            "meetings_moved": len(moved),
            "metric_changes": {
                k: {"before": v["before"], "after": v["after"], "better_is": v["better"]}
                for k, v in d.items()
                if v["delta"] != 0
            },
            "note": "Preview only. The administrator can apply it from the card.",
        }

    def t_explain_gap(self, entity_id: str, day: int) -> dict:
        if self.s.current is None:
            return NO_TIMETABLE
        out = explain_gap(self.s.u, self.s.current, self.s.constraints, entity_id, day)
        self._summary(summarize_gap(out, self.lang))
        if "error" not in out:
            self.overlay = {
                "kind": "gap",
                "entity_type": "student" if entity_id in self.s.u.student_by_id else "cohort",
                "entity_id": entity_id,
                "day": day,
                "day_name": out["day"],
                "gap_hours": out.get("gap_hours", []),
                "blocked": _blocked_moves(out.get("moves_considered", [])),
            }
        return out

    def t_explain_meeting(self, meeting_id: str) -> dict:
        if self.s.current is None:
            return NO_TIMETABLE
        out = explain_meeting(self.s.u, self.s.current, self.s.constraints, meeting_id)
        self._summary(summarize_meeting(out, self.lang))
        return out

    def _summary(self, text: str | None) -> None:
        if text and text not in self.summaries:
            self.summaries.append(text)

    def t_get_schedule(self, entity_type: str, entity_id: str) -> dict:
        from api.main import _meetings_for

        if self.s.current is None:
            return NO_TIMETABLE
        a = self.s.current
        rows = []
        for mid in _meetings_for(entity_type, entity_id):
            if mid not in a.slot:
                continue
            if entity_type == "room" and a.room[mid] != entity_id:
                continue
            sec = self.s.u.section_by_id[self.s.u.meeting_by_id[mid].section_id]
            rows.append(
                {
                    "meeting_id": mid,
                    "course": self.s.u.course_by_id[sec.course_id].name,
                    "day": DAYS[slot_day(a.slot[mid])],
                    "hour": f"{FIRST_HOUR + slot_period(a.slot[mid]):02d}:00",
                    "room": a.room[mid],
                }
            )
        rows.sort(key=lambda r: (DAYS.index(r["day"]), r["hour"]))
        return {"entity_type": entity_type, "entity_id": entity_id, "meetings": rows}

    def t_get_metrics(self) -> dict:
        if self.s.current is None:
            return NO_TIMETABLE
        keep = lambda m: {k: v for k, v in m.items() if not isinstance(v, (list, dict))}
        return {"current": keep(self.s.current_metrics), "baseline": keep(self.s.baseline_metrics)}

    def _check_ids(self, c: dict) -> None:
        u = self.s.u
        for key, table, what in (
            ("instructor_id", u.instructor_by_id, "instructor"),
            ("room_id", u.room_by_id, "room"),
            ("section_id", u.section_by_id, "section"),
            ("course_id", u.course_by_id, "course"),
            ("cohort", set(u.cohorts), "cohort"),
        ):
            if c.get(key) is not None and c[key] not in table:
                raise ValueError(
                    f"'{c[key]}' is not a real {what} ID. Call get_entity first."
                )


BLOCK_ICONS = [
    ("already teaches", "instructor", "instructor busy", "المدرّس مشغول"),
    ("is not available", "unavailable", "not available", "غير متاح"),
    ("confirmed rule", "rule", "a confirmed rule", "قاعدة مؤكدة"),
    ("needs a lab", "room", "no free lab", "لا يوجد معمل متاح"),
    ("no room", "room", "no free room", "لا توجد قاعة"),
    ("every accessible room", "access", "no accessible room", "لا قاعة مهيّأة"),
    ("all ", "room", "no free room", "لا توجد قاعة"),
    ("different days", "days", "same section, same day", "نفس الشعبة بنفس اليوم"),
]


def _classify(reason: str) -> tuple[str, str, str]:
    for needle, kind, en, ar in BLOCK_ICONS:
        if needle in reason:
            return kind, en, ar
    return "other", reason[:40], reason[:40]


def _blocked_moves(moves: list[dict]) -> list[dict]:
    """One row per attempted move, with why it failed in a few words."""
    out = []
    for m in moves:
        if m["blocked_by"]:
            kind, en, ar = _classify(m["blocked_by"][0])
            detail_en = m["blocked_by"][0]
            detail_ar = (m.get("blocked_by_ar") or m["blocked_by"])[0]
        else:
            kind = "cost"
            en = ar = ""
            detail_en = m.get("verdict", "")
            detail_ar = m.get("verdict_ar", detail_en)
            if "clash with" in detail_en:
                kind, en, ar = "clash", "students would clash", "سيتعارض طلاب"
            else:
                kind, en, ar = "pointless", "would not help", "لن يفيد"
        out.append({
            "meeting_id": m["meeting_id"],
            "section_id": m["section_id"],
            "course": m["course"],
            "course_ar": m["course_ar"],
            "from_hour": m["from_hour"],
            "to_hour": m["to_hour"],
            "kind": kind,
            "label_en": en,
            "label_ar": ar,
            "detail": detail_en,
            "detail_ar": detail_ar,
        })
    return out


def _choices(u, matches: list[dict]) -> list[dict]:
    """One button per candidate: the stored name, the English name if there is
    one, and the text sent back when it is clicked."""
    out = []
    for m in matches:
        kind, eid = m["kind"], m["id"]
        name, name_en, reply = eid, "", eid
        if kind == "instructor":
            i = u.instructor_by_id[eid]
            name, name_en, reply = i.name, i.name_en, i.name
        elif kind == "course":
            c = u.course_by_id[eid]
            name, name_en, reply = c.name_ar, c.name, c.name_ar
        elif kind == "section":
            c = u.course_by_id[u.section_by_id[eid].course_id]
            name, name_en = f"{eid} — {c.name_ar}", f"{eid} — {c.name}"
        elif kind == "student":
            st = u.student_by_id[eid]
            name, name_en = st.name, st.name_en
        out.append({"kind": kind, "id": eid, "name": name, "name_en": name_en,
                    "reply": reply})
    # two candidates can share a stored name; then the id is what tells them apart
    names = [c["reply"] for c in out]
    for c in out:
        if names.count(c["reply"]) > 1:
            c["reply"] = c["id"]
    return out


_TIME = re.compile(r"\b(\d{1,2})[:.٫](\d{2})\b")
_NUMBER = re.compile(r"\d+")
# every id carries a digit: S01, S01-m1, CS-L3, B12, B1-101, ST049, I01, C04
_ID = re.compile(r"\b[A-Z]{1,3}(?:\d+(?:-[A-Za-z]?\d+)?|-L\d+)\b")
_NUMBER_WORDS = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7,
    "eight": 8, "nine": 9, "ten": 10,
    "ساعتين": 2, "ساعتان": 2, "اثنتين": 2, "اثنين": 2, "ثلاث": 3, "ثلاثة": 3,
    "أربع": 4, "اربع": 4, "أربعة": 4, "خمس": 5, "خمسة": 5, "ست": 6, "ستة": 6,
    "سبع": 7, "سبعة": 7, "ثمان": 8, "ثماني": 8, "تسع": 9, "عشر": 10,
}
_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩", "0123456789")


_ABBREVIATIONS = ("د.", "أ.", "Dr.", "Prof.", "dr.")


def _first_sentence(text: str) -> str:
    text = re.sub(r"[*_`#>]+", "", text or "").strip()
    # "د. سارة" is one name, not the end of a sentence
    for abbr in _ABBREVIATIONS:
        text = text.replace(abbr + " ", abbr + "\x00")     # not whitespace to \s
    for part in re.split(r"(?<=[.!?؟])\s+|\n+", text):
        part = part.strip(" -•\t")
        if part:
            return part.replace("\x00", " ")
    return ""


def _facts(text: str) -> tuple[set[str], set[int]]:
    """(times as HH:MM, every other number) that a text states. The digits in
    an id (the 3 of CS-L3) are part of a name, not a number."""
    text = text.translate(_DIGITS)
    times = {f"{int(h):02d}:{m}" for h, m in _TIME.findall(text)}
    rest = _ID.sub(" ", _TIME.sub(" ", text))
    numbers = {int(n) for n in _NUMBER.findall(rest)}
    numbers |= {n for w, n in _NUMBER_WORDS.items() if re.search(rf"(?<!\w){w}(?!\w)", text.lower())}
    return times, numbers


def _names(u) -> list[str]:
    out = [d for d in DAYS] + list(DAYS_AR)
    for i in u.instructors:
        out += [i.name, i.name_en]
    for c in u.courses:
        out += [c.name, c.name_ar]
    for st in u.students:
        out += [st.name, st.name_en]
    for b in u.buildings:
        out += [b.name, b.name_ar]
    return [n for n in out if n and len(n) > 2]


def sentence_is_grounded(sentence: str, summary: str, u) -> bool:
    """True when the sentence states no time, and no number, day, name or id
    that the summary does not.

    No time at all: the summary already gives the hours exactly, and a wrong
    range is easily built from right parts ("10:00 to 12:00" when 10:00 is a
    class and 12:00 the end of the gap). A bare hour ("at 11") is a time too."""
    _, s_numbers = _facts(summary)
    times, numbers = _facts(sentence)
    if times:
        return False
    if re.search(r"\b(at|from|to|until|الساعة|من|إلى|الى|حتى)\s+\d{1,2}\b",
                 sentence.translate(_DIGITS)):
        return False
    if not numbers <= s_numbers:
        return False
    for token in _ID.findall(sentence):
        if token not in summary:
            return False
    return all(name not in sentence or name in summary for name in _names(u))


def compose(summaries: list[str], model_reply: str, u) -> str:
    """The code-written summary, verbatim, then at most one sentence of the
    model's, and only if it adds no fact of its own."""
    summary = "\n\n".join(summaries)
    sentence = _first_sentence(model_reply)
    if sentence and sentence_is_grounded(sentence, summary, u):
        return f"{summary}\n\n{sentence}"
    return summary


RETRY_NOTE = (
    "Check: your last reply says a rule was proposed, but you called no tool, so "
    "nothing was proposed and there is no confirmation card. Call propose_constraint "
    "now (or what_if if the request was a hypothetical). Respond with the tool call."
)
NOTHING_PROPOSED = {
    "ar": "لم يُقترح أي تغيير. هل يمكن إعادة صياغة الطلب؟",
    "en": "Nothing was proposed. Could you rephrase the request?",
}
PROPOSED = {
    "ar": "القاعدة مقترحة وبانتظار تأكيدك في البطاقة.",
    "en": "The rule is proposed and waits for your confirmation on the card.",
}

# Past-tense claims that a rule now exists, after folding hamza and taa marbuta.
_CLAIMS_AR = (
    "اقترحت", "قمت باقتراح", "تم اقتراح", "قمت بانشاء", "تم انشاء", "انشات",
    "بطاقه التاكيد", "بانتظار تاكيد", "في انتظار تاكيد", "بانتظار التاكيد",
    "في انتظار التاكيد", "بانتظار موافقت", "في انتظار موافقت",
)
_CLAIMS_EN = re.compile(
    r"\b(?:i|we)(?:'ve| have)?\s+(?:just\s+)?(?:proposed|created|added|drafted|submitted)\b"
    r"|\bproposed (?:a|the|this|your) (?:rule|constraint|change)\b"
    r"|\bconfirmation card\b"
    r"|\b(?:awaiting|pending|waiting for) (?:your )?(?:confirmation|approval)\b",
    re.IGNORECASE,
)


def _fold_ar(text: str) -> str:
    text = re.sub("[\u064b-\u0652\u0640]", "", text)          # diacritics, tatweel
    text = re.sub("[إأآ]", "ا", text)
    return text.replace("ة", "ه").replace("ى", "ي")


def claims_proposal(reply: str) -> bool:
    """True when the reply says a rule was proposed or awaits confirmation."""
    if not reply:
        return False
    if _CLAIMS_EN.search(reply):
        return True
    folded = _fold_ar(reply)
    return any(c in folded for c in _CLAIMS_AR)


def _asking(tools) -> bool:
    """It is legitimately asking which one was meant: a lookup was ambiguous,
    vague or empty, so no card is expected yet."""
    return bool(tools.choices) or any(
        l["vague"] or l["count"] != 1 for l in tools.lookups
    )


def _recent(history: list) -> list:
    """Keep the tail of the conversation, cut at a clean user turn so a tool
    result is never separated from the call that produced it."""
    if len(history) <= MAX_TURNS:
        return list(history)
    tail = history[-MAX_TURNS:]
    for i, m in enumerate(tail):
        if m.get("role") == "user":
            return tail[i:]
    return []


_ARABIC = re.compile(r"[\u0600-\u06FF]")
_LATIN = re.compile(r"[A-Za-z]")


class Agent:
    """Ollama cloud, native tool calling. One small surface, so the model can be
    swapped with an env var."""

    def __init__(self) -> None:
        self._client = None

    @property
    def client(self):
        if self._client is None:
            import ollama

            self._client = ollama.Client(host=HOST)
        return self._client

    def available(self) -> tuple[bool, str]:
        try:
            names = {m.model for m in self.client.list().models}
        except Exception as e:
            return False, (
                f"Cannot reach Ollama at {HOST} ({type(e).__name__}). "
                "Start it with `ollama serve`."
            )
        if MODEL not in names:
            return False, (
                f"Model '{MODEL}' is not available. Run `ollama pull {MODEL}` "
                "(cloud models also need `ollama signin`)."
            )
        return True, ""

    def _loop(self, system: str, messages: list, tools, require_tool: bool = False) -> str:
        """Let the model call tools until it answers in words. With
        `require_tool`, a first answer that calls no tool ends the loop empty."""
        reply = ""
        for step in range(MAX_STEPS):
            response = self.client.chat(
                model=MODEL,
                messages=[{"role": "system", "content": system}] + messages,
                tools=TOOLS,
                think=False,
                options={"temperature": 0},
            )
            msg = response["message"]
            messages.append(
                {
                    "role": "assistant",
                    "content": msg.get("content") or "",
                    **({"tool_calls": msg["tool_calls"]} if msg.get("tool_calls") else {}),
                }
            )
            calls = msg.get("tool_calls") or []
            if require_tool and step == 0 and not calls:
                return ""
            reply = msg.get("content") or reply
            if not calls:
                break
            for call in calls:
                fn = call["function"]
                args = fn.get("arguments") or {}
                if isinstance(args, str):
                    try:
                        args = json.loads(args)
                    except json.JSONDecodeError:
                        args = {}
                out = tools.run(fn["name"], dict(args))
                payload = json.dumps(out, ensure_ascii=False, default=str)
                if len(payload) > MAX_TOOL_CHARS:
                    payload = payload[:MAX_TOOL_CHARS] + ' …", "truncated": true}'
                messages.append(
                    {"role": "tool", "tool_name": fn["name"], "content": payload}
                )
        return reply

    def handle(self, message: str, session, history: list, tools=None) -> dict:
        ok, why = self.available()
        if not ok:
            return {"reply": why, "card": None, "history": history, "offline": True,
                    "calls": [], "lookups": [], "tools": tools or Tools(session),
                    "overlay": None, "choices": None}

        tools = tools or Tools(session)
        messages = _recent(history) + [{"role": "user", "content": message}]
        # tool results are in English; without this the model echoes them back
        # to an Arabic question in English
        lang = "Arabic" if len(_ARABIC.findall(message)) > len(_LATIN.findall(message)) else "English"
        system = SYSTEM + f"\n\nThe administrator's latest message is in {lang}. Reply in {lang}."
        tools.lang = "ar" if lang == "Arabic" else "en"
        reply = self._loop(system, messages, tools)

        if not (reply or "").strip():
            # It ran out of steps without writing an answer: ask once more with
            # the tools withheld so it has to put the answer in words.
            final = self.client.chat(
                model=MODEL,
                messages=[{"role": "system", "content": system}] + messages,
                think=False,
                options={"temperature": 0},
            )
            reply = final["message"].get("content") or ""

        if tools.card is None and claims_proposal(reply) and not _asking(tools):
            # It says it proposed a rule but called no tool: nothing exists for
            # the administrator to confirm. Say so, and demand the call once.
            messages.append({"role": "user", "content": RETRY_NOTE})
            again = self._loop(system, messages, tools, require_tool=True)
            if tools.card is None:
                reply = NOTHING_PROPOSED[tools.lang]
            else:
                reply = again if (again or "").strip() and not _asking(tools) \
                    else PROPOSED[tools.lang]

        reply = (reply or "").strip()
        if tools.summaries:
            reply = compose(tools.summaries, reply, session.u)
        return {
            "reply": reply or "(no reply)",
            "card": tools.card,
            "history": messages,
            "offline": False,
            "calls": tools.calls,
            "lookups": tools.lookups,
            "tools": tools,
            "overlay": tools.overlay,
            # a proposal settles the question, so there is nothing left to pick
            "choices": tools.choices if tools.card is None else None,
        }


AGENT = Agent()
