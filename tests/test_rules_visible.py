"""What the administrator can see: the rule catalog, and the line for a request
no rule type covers."""

from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from agent.agent import AGENT
from agent.catalog import BUILTIN_RULES, GROUPS, KINDS, QUESTIONS, RULE_TYPES, unavailable_line
from agent.schemas import CONSTRAINTS
from api.main import app


def test_the_catalog_is_the_schema_s_rule_types():
    assert set(RULE_TYPES) == set(CONSTRAINTS)


def test_every_type_has_a_group_a_kind_names_and_examples():
    for t, info in RULE_TYPES.items():
        assert info["group"] in GROUPS and info["group"] != "ask", t
        assert info["kind"] in KINDS, t
        for k in ("name_en", "name_ar", "example_en", "example_ar"):
            assert info[k].strip(), (t, k)
    assert {t for t, i in RULE_TYPES.items() if i["kind"] == "preference"} == {"avoid_single_class_days"}
    # before the build: campus break, daily max, fewer single-class days
    assert {t for t, i in RULE_TYPES.items() if i["setup"]} == {
        "campus_break", "instructor_max_daily", "avoid_single_class_days"}
    assert QUESTIONS and len(BUILTIN_RULES) == 7


def test_the_page_gets_the_catalog():
    rules = TestClient(app).get("/api/meta").json()["rules"]
    assert [x["type"] for x in rules["types"]] == list(RULE_TYPES)
    assert rules["builtin"][0]["ar"] and rules["goals"]["en"]


def test_the_unavailable_line_lists_every_rule_in_both_languages():
    en, ar = unavailable_line()
    assert ar.startswith("هذا النوع غير متاح حاليًا. القواعد المتاحة:")
    assert all(i["name_ar"] in ar for i in RULE_TYPES.values())
    assert all(i["name_en"] in en for i in RULE_TYPES.values())


class FakeModel:
    def __init__(self, script):
        self.script = list(script)

    def list(self):
        from agent.agent import MODEL

        return SimpleNamespace(models=[SimpleNamespace(model=MODEL)])

    def chat(self, **_):
        return {"message": self.script.pop(0)}


def _call(name, args):
    return {"content": "", "tool_calls": [{"function": {"name": name, "arguments": args}}]}


@pytest.fixture
def client():
    c = TestClient(app)
    c.post("/api/data/reset")
    yield c
    c.post("/api/data/reset")


def _say(client, monkeypatch, message, script):
    monkeypatch.setattr(AGENT, "_client", FakeModel(script))
    return client.post("/api/agent/message", json={"message": message}).json()


def test_a_preference_no_rule_covers_gets_the_code_written_line(client, monkeypatch):
    out = _say(client, monkeypatch, "د. أحمد العلي يفضّل الصباح", [
        _call("get_entity", {"name_query": "د. أحمد العلي"}),
        {"content": "عذرًا، لا يمكنني إضافة تفضيلات أوقات للمدرّسين حاليًا."},
    ])
    en, ar = unavailable_line()
    assert out["status_line"]["text_ar"] == ar and out["status_line"]["text_en"] == en
    assert out["reply"].startswith("عذرًا")                  # the model's text, untouched
    chat = client.get("/api/agent/state").json()["chat"]
    assert chat[-1] == out["status_line"]                     # and it survives a reload


def test_an_unknown_type_proposal_gets_the_line_too(client, monkeypatch):
    out = _say(client, monkeypatch, "Dr. Ahmed prefers mornings", [
        _call("propose_constraint", {"constraint": {"type": "instructor_preference",
                                                    "instructor_id": "I01"}}),
        {"content": "That rule type does not exist."},
    ])
    assert out["status_line"] is not None


@pytest.mark.parametrize("message,script", [
    # asking which one is meant: the rule exists
    ("Block the professor on Monday", [{"content": "Which professor do you mean?"}]),
    ("د. أحمد ما يقدر الثلاثاء بعد ٢", [
        _call("get_entity", {"name_query": "د. أحمد"}), {"content": "أيّهما تقصد؟"}]),
    # a real proposal
    ("لا محاضرات من ١٢ إلى ١", [
        _call("propose_constraint", {"constraint": {"type": "campus_break", "from": "12:00",
                                                    "to": "13:00"}}),
        {"content": "اقترحت القاعدة."}]),
    # a question answered with a tool, even if it could not answer
    ("كم نسبة الطلاب بدون تعارض؟", [_call("get_metrics", {}),
                                    {"content": "لا يمكنني ذلك قبل بناء الجدول."}]),
    # a name that does not exist
    ("د. زياد ما يدرّس الأربعاء", [_call("get_entity", {"name_query": "د. زياد"}),
                                   {"content": "لم أجد د. زياد."}]),
])
def test_no_line_when_a_rule_type_did_match(client, monkeypatch, message, script):
    assert _say(client, monkeypatch, message, script)["status_line"] is None
