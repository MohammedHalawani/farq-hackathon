from __future__ import annotations

import json
import os

from dotenv import load_dotenv

from agent.describe import describe, short_label
from agent.resolver import resolve
from agent.schemas import CONSTRAINT_TOOL_SCHEMA, parse_constraint
from core.explain import explain_gap, explain_meeting
from core.metrics import delta, moved_meetings
from core.models import DAYS, FIRST_HOUR, slot_day, slot_period
from core.solver import solve

load_dotenv()

MODEL = os.environ.get("ANTHROPIC_MODEL", "claude-opus-5")
MAX_STEPS = 8

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
- 1 match    -> use its ID.

WHAT THE ADMINISTRATOR IS ASKING FOR
- A rule to add ("X can't teach Tuesday afternoon", "close room B12")
  -> call propose_constraint. This only proposes: the administrator sees a
     confirmation card and decides. Say what you proposed and that it awaits confirmation.
- A hypothetical ("what if...", "ماذا لو", "لو أغلقنا")
  -> call what_if. It previews the effect without applying anything.
- A question about the schedule ("why is there a gap", "ليش فيه فراغ", "why is this
  class here") -> call explain_gap or explain_meeting and phrase what comes back.
  These return the real blocking constraints; report them, do not speculate.

TIME
Days are 0=Sunday, 1=Monday, 2=Tuesday, 3=Wednesday, 4=Thursday. The teaching day is
8 one-hour slots: slot 0 = 08:00 ... slot 7 = 15:00. "After 2pm" means slots 6 and 7.
"Morning" is slots 0-3, "afternoon" is slots 4-7."""

TOOLS = [
    {
        "name": "get_entity",
        "description": (
            "Fuzzy-match a name the administrator typed against instructors, rooms, "
            "sections, cohorts and students. Handles Arabic and English, and typos. "
            "Always use this before naming any ID."
        ),
        "strict": True,
        "input_schema": {
            "type": "object",
            "additionalProperties": False,
            "required": ["name_query"],
            "properties": {
                "name_query": {"type": "string"},
                "kind": {
                    "type": "string",
                    "enum": ["instructor", "room", "section", "cohort", "student"],
                    "description": "Optional filter when you know what you are looking for.",
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
        "strict": True,
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
        "strict": True,
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
        "strict": True,
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
        "strict": True,
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
        "strict": True,
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
        "strict": True,
        "input_schema": {
            "type": "object",
            "additionalProperties": False,
            "required": [],
            "properties": {},
        },
    },
]


class Tools:
    """Every tool runs deterministic Python. The model only chooses which to call."""

    def __init__(self, session) -> None:
        self.s = session
        self.card: dict | None = None

    def run(self, name: str, args: dict) -> dict:
        fn = getattr(self, f"t_{name}", None)
        if fn is None:
            return {"error": f"No tool named {name}."}
        try:
            return fn(**args)
        except Exception as e:
            return {"error": f"{type(e).__name__}: {e}"}

    def t_get_entity(self, name_query: str, kind: str | None = None) -> dict:
        matches = resolve(self.s.u, name_query, kind)
        return {
            "query": name_query,
            "match_count": len(matches),
            "matches": matches,
            "note": (
                "No match. Tell the administrator it was not found."
                if not matches
                else "Exactly one match; use this ID."
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
        if self.s.current is None:
            return {"error": "No schedule yet. Run the solver first."}
        r = solve(
            self.s.u,
            self.s.active_profile,
            constraints=self.s.constraints + [c],
            base=self.s.current,
            minimal_change=True,
            rounds=4,
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
            "moved": moved[:20],
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


class Agent:
    def __init__(self) -> None:
        self.key = os.environ.get("ANTHROPIC_API_KEY")
        self._client = None

    @property
    def client(self):
        if self._client is None:
            import anthropic

            self._client = anthropic.Anthropic(api_key=self.key)
        return self._client

    def handle(self, message: str, session, history: list) -> dict:
        if not self.key:
            return {
                "reply": (
                    "No ANTHROPIC_API_KEY is set, so the assistant is offline. "
                    "Copy .env.example to .env and add a key."
                ),
                "card": None,
                "history": history,
                "offline": True,
            }

        tools = Tools(session)
        messages = history + [{"role": "user", "content": message}]

        for _ in range(MAX_STEPS):
            response = self.client.messages.create(
                model=MODEL,
                max_tokens=16000,
                system=SYSTEM,
                tools=TOOLS,
                thinking={"type": "adaptive"},
                output_config={"effort": "medium"},
                messages=messages,
            )
            messages.append({"role": "assistant", "content": response.content})
            if response.stop_reason != "tool_use":
                break
            results = []
            for block in response.content:
                if block.type != "tool_use":
                    continue
                out = tools.run(block.name, dict(block.input))
                results.append(
                    {
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": json.dumps(out, ensure_ascii=False, default=str),
                    }
                )
            messages.append({"role": "user", "content": results})

        reply = "\n".join(
            b.text for b in response.content if b.type == "text"
        ).strip()
        return {
            "reply": reply or "(no reply)",
            "card": tools.card,
            "history": messages,
            "offline": False,
        }


AGENT = Agent()
