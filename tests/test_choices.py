"""When a name is ambiguous, the choices on screen come from the resolver,
never from the model's wording."""

from types import SimpleNamespace

from fastapi.testclient import TestClient

from agent.agent import AGENT, Tools
from data.generator import generate

AHMEDS = [
    {"kind": "instructor", "id": "I01", "name": "د. أحمد العلي",
     "name_en": "Dr. Ahmed Alali", "reply": "د. أحمد العلي"},
    {"kind": "instructor", "id": "I02", "name": "د. أحمد الغامدي",
     "name_en": "Dr. Ahmed Alghamdi", "reply": "د. أحمد الغامدي"},
]


class FakeModel:
    """Looks the name up, then asks — misspelling one of them, the way the real
    model once did («الغاممي»)."""

    def __init__(self, script):
        self.script = list(script)

    def list(self):
        from agent.agent import MODEL

        return SimpleNamespace(models=[SimpleNamespace(model=MODEL)])

    def chat(self, **_):
        return {"message": self.script.pop(0)}


def _lookup(query):
    return {"content": "", "tool_calls": [
        {"function": {"name": "get_entity", "arguments": {"name_query": query}}}]}


def test_ambiguous_lookup_records_the_stored_names():
    t = Tools(SimpleNamespace(u=generate(), current=None))
    t.run("get_entity", {"name_query": "د. أحمد"})
    assert t.choices == AHMEDS


def test_a_single_match_offers_no_choices():
    t = Tools(SimpleNamespace(u=generate(), current=None))
    t.run("get_entity", {"name_query": "د. أحمد العلي"})
    assert t.choices is None


def test_choices_reach_the_api_verbatim(monkeypatch):
    from api.main import app

    fake = FakeModel([
        _lookup("د. أحمد"),
        {"content": "أيّهما تقصد: د. أحمد العلي أو د. أحمد الغاممي؟"},
    ])
    monkeypatch.setattr(AGENT, "_client", fake)
    out = TestClient(app).post(
        "/api/agent/message", json={"message": "د. أحمد ما يقدر الثلاثاء بعد ٢"}
    ).json()
    assert "الغاممي" in out["reply"]                 # the model's slip stays in its text
    assert out["choices"] == AHMEDS                   # but never reaches the buttons
    assert [c["reply"] for c in out["choices"]] == ["د. أحمد العلي", "د. أحمد الغامدي"]


def test_a_proposal_clears_the_choices(monkeypatch):
    fake = FakeModel([
        _lookup("د. أحمد"),
        _lookup("د. أحمد العلي"),
        {"content": "", "tool_calls": [{"function": {"name": "propose_constraint", "arguments": {
            "constraint": {"type": "instructor_unavailable", "instructor_id": "I01",
                           "days": [2], "slots": [6, 7]}}}}]},
        {"content": "اقترحت القاعدة."},
    ])
    monkeypatch.setattr(AGENT, "_client", fake)
    session = SimpleNamespace(u=generate(), current=None)
    out = AGENT.handle("د. أحمد العلي ما يقدر الثلاثاء بعد ٢", session, [])
    assert out["card"] is not None and out["choices"] is None


def test_same_stored_name_falls_back_to_the_id():
    from agent.agent import _choices

    u = generate()
    twin = u.students[1]
    u.students[0].name = twin.name
    got = _choices(u, [{"kind": "student", "id": u.students[0].id},
                       {"kind": "student", "id": twin.id}])
    assert [c["name"] for c in got] == [twin.name, twin.name]
    assert [c["reply"] for c in got] == [u.students[0].id, twin.id]
