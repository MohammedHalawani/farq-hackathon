from __future__ import annotations

import json
import os

from dotenv import load_dotenv

from agent.describe import describe, short_label
from agent.resolver import is_vague, resolve
from agent.schemas import CONSTRAINT_TOOL_SCHEMA, parse_constraint
from core.explain import explain_gap, explain_meeting
from core.metrics import delta, moved_meetings
from core.models import DAYS, FIRST_HOUR, slot_day, slot_period
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
  class here") -> call explain_gap or explain_meeting and phrase what comes back.
  These return the real blocking constraints; report them, do not speculate.

TIME
Days are 0=Sunday, 1=Monday, 2=Tuesday, 3=Wednesday, 4=Thursday. Friday and Saturday
are the weekend and do not exist. The teaching day is 8 one-hour slots:
slot 0 = 08:00, slot 1 = 09:00 ... slot 7 = 15:00.
- "after N o'clock" / "بعد الساعة N" includes the slot that starts at N.
  "after 2pm" is slots 6,7. "after 12" is slots 4,5,6,7.
- "before N o'clock" excludes the slot starting at N. "before 10am" is slots 0,1.
- "morning" is slots 0-3, "afternoon" is slots 4-7, a whole day is slots 0-7."""

RAW_TOOLS = [
    {
        "name": "get_entity",
        "description": (
            "Fuzzy-match a name the administrator typed against instructors, rooms, "
            "sections, cohorts and students. Handles Arabic and English, and typos. "
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
                    "enum": ["instructor", "room", "section", "cohort", "student"],
                    "description": (
                        "Optional hint. A 'section' is one class group (S19); a "
                        "'cohort' is a department and level (BA-L3). Omit it if unsure."
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
                "day": {"type": "integer", "description": "0=Sunday .. 4=Thursday"},
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


class Tools:
    """Every tool runs deterministic Python. The model only chooses which to call."""

    def __init__(self, session, dry_run: bool = False) -> None:
        self.s = session
        self.card: dict | None = None
        self.dry_run = dry_run
        self.calls: list[tuple[str, dict]] = []
        self.lookups: list[dict] = []

    def run(self, name: str, args: dict) -> dict:
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
        self.lookups.append({"query": name_query, "count": len(matches), "vague": vague})
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
            "note": "Shown to the administrator as a confirmation card. Not applied.",
        }

    def t_what_if(self, constraint: dict) -> dict:
        c = parse_constraint(constraint)
        self._check_ids(c)
        if self.dry_run:
            return {"feasible": True, "meetings_moved": 0, "metric_changes": {},
                    "note": "Preview skipped (evaluation mode)."}
        if self.s.current is None:
            return {"error": "No schedule yet. Run the solver first."}
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
        from core.metrics import compute

        after = compute(self.s.u, r.assignment)
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
            return {"error": "No schedule yet. Run the solver first."}
        return explain_gap(self.s.u, self.s.current, self.s.constraints, entity_id, day)

    def t_explain_meeting(self, meeting_id: str) -> dict:
        if self.s.current is None:
            return {"error": "No schedule yet. Run the solver first."}
        return explain_meeting(self.s.u, self.s.current, self.s.constraints, meeting_id)

    def t_get_schedule(self, entity_type: str, entity_id: str) -> dict:
        from api.main import _meetings_for

        if self.s.current is None:
            return {"error": "No schedule yet. Run the solver first."}
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
            return {"error": "No schedule yet. Run the solver first."}
        keep = lambda m: {k: v for k, v in m.items() if not isinstance(v, (list, dict))}
        return {"current": keep(self.s.current_metrics), "baseline": keep(self.s.baseline_metrics)}

    def _check_ids(self, c: dict) -> None:
        u = self.s.u
        for key, table, what in (
            ("instructor_id", u.instructor_by_id, "instructor"),
            ("room_id", u.room_by_id, "room"),
            ("section_id", u.section_by_id, "section"),
        ):
            if key in c and c[key] not in table:
                raise ValueError(
                    f"'{c[key]}' is not a real {what} ID. Call get_entity first."
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

    def handle(self, message: str, session, history: list, tools=None) -> dict:
        ok, why = self.available()
        if not ok:
            return {"reply": why, "card": None, "history": history, "offline": True,
                    "calls": [], "lookups": [], "tools": tools or Tools(session)}

        tools = tools or Tools(session)
        messages = _recent(history) + [{"role": "user", "content": message}]
        reply = ""

        for _ in range(MAX_STEPS):
            response = self.client.chat(
                model=MODEL,
                messages=[{"role": "system", "content": SYSTEM}] + messages,
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
            reply = msg.get("content") or reply
            calls = msg.get("tool_calls") or []
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

        if not (reply or "").strip():
            # It ran out of steps without writing an answer: ask once more with
            # the tools withheld so it has to put the answer in words.
            final = self.client.chat(
                model=MODEL,
                messages=[{"role": "system", "content": SYSTEM}] + messages,
                think=False,
                options={"temperature": 0},
            )
            reply = final["message"].get("content") or ""

        return {
            "reply": (reply or "").strip() or "(no reply)",
            "card": tools.card,
            "history": messages,
            "offline": False,
            "calls": tools.calls,
            "lookups": tools.lookups,
            "tools": tools,
        }


AGENT = Agent()
