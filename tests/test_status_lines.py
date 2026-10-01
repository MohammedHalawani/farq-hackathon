"""Status lines are part of the session chat, in both languages, so a reload
shows the same conversation as before it."""

import pytest
from fastapi.testclient import TestClient

import api.state as state_mod
from api.main import app
from api.state import SESSION
from core.solver import SolveResult

NOON = {"type": "campus_break", "days": [0, 1, 2, 3, 4], "slots": [4]}
AHMED = {"type": "instructor_unavailable", "instructor_id": "I01", "days": [2], "slots": [6, 7]}


@pytest.fixture
def client():
    c = TestClient(app)
    c.post("/api/data/reset")          # a fresh demo campus and an empty chat
    yield c
    c.post("/api/data/reset")


def _status(client) -> list[dict]:
    return [m for m in client.get("/api/agent/state").json()["chat"] if m.get("status")]


def test_setup_line_is_in_the_session_chat(client):
    out = client.post("/api/changes/apply", json={"constraint": NOON}).json()
    assert out["ok"] and out["stage"] == "setup"
    lines = _status(client)
    assert lines == [out["chat"]]
    assert lines[0]["text_ar"].startswith("حُفظت كقاعدة إعداد")
    assert lines[0]["text_en"].startswith("Saved as a setup rule")


def test_applied_and_undo_lines_are_in_the_session_chat(client, monkeypatch):
    # a built timetable without the 35-second build: the baseline as version 0
    SESSION._push("Initial schedule", None, SESSION.baseline)
    moved = SESSION.baseline.copy()
    first = next(iter(moved.slot))
    moved.slot[first] = (moved.slot[first] + 1) % 40
    monkeypatch.setattr(state_mod, "solve",
                        lambda *a, **k: SolveResult("FEASIBLE", moved, 0, 0.0, "balanced"))

    out = client.post("/api/changes/apply", json={"constraint": AHMED}).json()
    assert out["ok"] and out["version"]["moved_count"] == 1
    assert out["chat"]["text_ar"] == "تم التطبيق. نُقلت 1 محاضرة."
    assert out["chat"]["text_en"] == "Applied. 1 meetings moved."

    undo = client.post("/api/changes/undo").json()
    assert undo["ok"] and undo["chat"]["text_ar"] == "تم التراجع."
    nothing = client.post("/api/changes/undo").json()
    assert not nothing["ok"] and nothing["chat"]["text_en"] == "Nothing to undo."

    assert _status(client) == [out["chat"], undo["chat"], nothing["chat"]]


def test_a_rejected_rule_says_so_in_both_languages(client, monkeypatch):
    monkeypatch.setattr(state_mod, "solve",
                        lambda *a, **k: SolveResult("INFEASIBLE", None, None, 0.0, "balanced",
                                                    message="Statics has no slot left."))
    out = client.post("/api/changes/apply", json={"constraint": AHMED}).json()
    assert not out["ok"]
    line = _status(client)[-1]
    assert line["text_en"].startswith("Could not apply: Statics has no slot left.")
    assert line["text_ar"].startswith("تعذّر التطبيق")
    assert "Instructor unavailable" not in line["text_ar"]
    assert "المدرّس غير متاح" in line["text_ar"]


def test_the_step_tracker_has_no_english_in_arabic(client):
    from agent.trace import for_apply

    out = client.post("/api/changes/apply", json={"constraint": NOON}).json()
    for s in out["trace"] + for_apply(SESSION.u, AHMED, {"ok": False, "blocking": [NOON],
                                                         "message": "x has no slot"}, 120):
        assert not any("a" <= ch.lower() <= "z" for ch in s["detail_ar"] + s["step_ar"]), s
