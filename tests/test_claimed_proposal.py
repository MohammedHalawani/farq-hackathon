"""A reply may only say a rule was proposed when a card exists."""

from types import SimpleNamespace

import pytest

from agent.agent import AGENT, NOTHING_PROPOSED, RETRY_NOTE, claims_proposal
from data.generator import generate

BREAK_CALL = {"content": "", "tool_calls": [{"function": {
    "name": "propose_constraint",
    "arguments": {"constraint": {"type": "campus_break", "days": ["Wednesday"],
                                 "from": "12:00", "until_end_of_day": True}}}}]}


class FakeModel:
    """Plays a script, and records what it was sent."""

    def __init__(self, script):
        self.script = list(script)
        self.seen: list[list] = []

    def list(self):
        from agent.agent import MODEL

        return SimpleNamespace(models=[SimpleNamespace(model=MODEL)])

    def chat(self, **kw):
        self.seen.append(kw["messages"])
        return {"message": self.script.pop(0)}


@pytest.fixture
def session():
    return SimpleNamespace(u=generate(), current=None)


def _run(monkeypatch, session, message, script):
    fake = FakeModel(script)
    monkeypatch.setattr(AGENT, "_client", fake)
    return AGENT.handle(message, session, []), fake


def test_a_claim_without_a_tool_call_is_retried_and_the_card_appears(monkeypatch, session):
    out, fake = _run(monkeypatch, session, "خلّوا الأربعاء بعد الظهر فاضي للكل، لا محاضرات", [
        {"content": "قمت باقتراح قاعدة استراحة عامة يوم الأربعاء، وهي بانتظار تأكيدك."},
        BREAK_CALL,
        {"content": "اقترحت استراحة عامة يوم الأربعاء بعد الظهر؛ أكّدها من البطاقة."},
    ])
    assert out["card"] is not None
    assert out["card"]["constraint"] == {"type": "campus_break", "days": [3], "slots": [4, 5, 6, 7]}
    assert fake.seen[1][-1] == {"role": "user", "content": RETRY_NOTE}
    assert out["reply"].startswith("اقترحت استراحة عامة")


def test_still_no_card_after_the_retry_says_nothing_was_proposed(monkeypatch, session):
    out, fake = _run(monkeypatch, session, "خلّوا الأربعاء بعد الظهر فاضي للكل، لا محاضرات", [
        {"content": "تم اقتراح قاعدة استراحة عامة. ستظهر لك بطاقة التأكيد."},
        {"content": "تم اقتراح القاعدة."},                 # retried, still no tool call
    ])
    assert out["card"] is None
    assert out["reply"] == NOTHING_PROPOSED["ar"]
    assert len(fake.seen) == 2, "one retry, no more"


def test_english_claim_gets_the_english_line(monkeypatch, session):
    out, _ = _run(monkeypatch, session, "No lectures after 2 on Thursday", [
        {"content": "I've proposed a campus break; it is awaiting your confirmation."},
        {"content": "Done, the rule is proposed."},
    ])
    assert out["card"] is None
    assert out["reply"] == NOTHING_PROPOSED["en"]


def test_a_tool_error_on_retry_is_still_nothing_proposed(monkeypatch, session):
    bad = {"content": "", "tool_calls": [{"function": {"name": "propose_constraint",
           "arguments": {"constraint": {"type": "campus_break", "from": "17:00"}}}}]}
    out, _ = _run(monkeypatch, session, "No lectures after 5", [
        {"content": "I have proposed a campus break after 5pm."},
        bad,
        {"content": "I proposed it."},
    ])
    assert out["card"] is None and out["reply"] == NOTHING_PROPOSED["en"]


def test_a_real_proposal_is_not_retried(monkeypatch, session):
    out, fake = _run(monkeypatch, session, "خلّوا الأربعاء بعد الظهر فاضي للكل", [
        BREAK_CALL,
        {"content": "اقترحت القاعدة وهي بانتظار تأكيدك."},
    ])
    assert out["card"] is not None and len(fake.seen) == 2


def test_asking_which_one_is_not_a_claim_to_retry(monkeypatch, session):
    out, fake = _run(monkeypatch, session, "د. أحمد ما يقدر الثلاثاء بعد ٢", [
        {"content": "", "tool_calls": [{"function": {"name": "get_entity",
                                                      "arguments": {"name_query": "د. أحمد"}}}]},
        {"content": "أيّهما تقصد؟ بعد التحديد تظهر بطاقة التأكيد."},
    ])
    assert len(fake.seen) == 2, "an ambiguous lookup is a question, not a failed proposal"
    assert out["choices"] and out["reply"].startswith("أيّهما تقصد")


@pytest.mark.parametrize("text,claims", [
    ("قمت باقتراح قاعدة **campus_break**", True),
    ("تم اقتراح قاعدة استراحة عامة", True),
    ("أنشأت القاعدة", True),
    ("القاعدة الآن في انتظار تأكيدك", True),
    ("ستظهر لك بطاقة التأكيد", True),
    ("I've proposed a rule", True),
    ("I have created the constraint", True),
    ("We proposed the change", True),
    ("It is pending your approval", True),
    ("أيّهما تقصد؟", False),
    ("Which Dr. Ahmed do you mean?", False),
    ("I will propose it once you pick one", False),
    ("لا يوجد فراغ يوم الاثنين", False),
])
def test_claim_wording(text, claims):
    assert claims_proposal(text) is claims
