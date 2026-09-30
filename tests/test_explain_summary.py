"""Explanations are written by code and shown verbatim. The model may add one
sentence, and only if it states nothing the summary does not."""

from types import SimpleNamespace

import pytest

from agent.agent import AGENT, compose, sentence_is_grounded
from core.baseline import build_baseline
from core.explain import explain_gap, explain_meeting, summarize_gap, summarize_meeting
from data.generator import generate

# on the demo baseline, CS-L3 has 11:00 and 13:00 empty on Sunday
ENTITY, DAY = "CS-L3", 0


@pytest.fixture(scope="module")
def campus():
    u = generate()
    return SimpleNamespace(u=u, current=build_baseline(u), constraints=[])


class FakeModel:
    def __init__(self, script):
        self.script = list(script)

    def list(self):
        from agent.agent import MODEL

        return SimpleNamespace(models=[SimpleNamespace(model=MODEL)])

    def chat(self, **_):
        return {"message": self.script.pop(0)}


def _ask(monkeypatch, session, message, tool, args, model_text):
    fake = FakeModel([
        {"content": "", "tool_calls": [{"function": {"name": tool, "arguments": args}}]},
        {"content": model_text},
    ])
    monkeypatch.setattr(AGENT, "_client", fake)
    return AGENT.handle(message, session, [])["reply"]


def test_gap_summary_states_the_exact_hours(campus):
    out = explain_gap(campus.u, campus.current, [], ENTITY, DAY)
    ar, en = summarize_gap(out, "ar"), summarize_gap(out, "en")
    assert ar.startswith("فراغ CS-L3 يوم الأحد: 11:00–12:00، 13:00–14:00 (ساعتان).")
    assert en.startswith("CS-L3 has a gap on Sunday: 11:00–12:00, 13:00–14:00 (2 hours).")
    # one line per reason, one reason per move tried
    assert ar.count("\n• ") == en.count("\n• ") == len(out["moves_considered"])
    assert "Moving" not in ar and "already teaches" not in ar


def test_a_model_that_states_the_wrong_hours_is_dropped(monkeypatch, campus):
    wrong = "الفراغ من 10:00 إلى 12:00 بسبب تعارض المدرسين."
    reply = _ask(monkeypatch, campus, "ليش عند حاسب المستوى الثالث فراغ يوم الأحد؟",
                 "explain_gap", {"entity_id": ENTITY, "day": "الأحد"}, wrong)
    summary = summarize_gap(explain_gap(campus.u, campus.current, [], ENTITY, DAY), "ar")
    assert reply == summary
    assert "10:00 إلى 12:00" not in reply


def test_a_grounded_sentence_is_kept_and_only_one(monkeypatch, campus):
    text = "الخلاصة: كل نقل ممكن يسبب تعارضًا أو يصطدم بمحاضرة أخرى. وهذا سطر ثانٍ لا يظهر."
    reply = _ask(monkeypatch, campus, "ليش عند حاسب المستوى الثالث فراغ يوم الأحد؟",
                 "explain_gap", {"entity_id": ENTITY, "day": "Sunday"}, text)
    summary = summarize_gap(explain_gap(campus.u, campus.current, [], ENTITY, DAY), "ar")
    assert reply.startswith(summary)
    assert reply.endswith("الخلاصة: كل نقل ممكن يسبب تعارضًا أو يصطدم بمحاضرة أخرى.")
    assert "سطر ثانٍ" not in reply


def test_english_question_gets_the_english_summary(monkeypatch, campus):
    reply = _ask(monkeypatch, campus, "Why does CS-L3 have a gap on Sunday?",
                 "explain_gap", {"entity_id": ENTITY, "day": "Sunday"},
                 "The gap runs from 10:00 to 11:00.")          # wrong again
    assert reply == summarize_gap(explain_gap(campus.u, campus.current, [], ENTITY, DAY), "en")


def test_meeting_summary_is_shown_first(monkeypatch, campus):
    reply = _ask(monkeypatch, campus, "ليش محاضرة S01-m1 في وقتها هذا؟",
                 "explain_meeting", {"meeting_id": "S01-m1"},
                 "المحاضرة يوم الثلاثاء الساعة 09:00.")          # wrong day and hour
    summary = summarize_meeting(explain_meeting(campus.u, campus.current, [], "S01-m1"), "ar")
    assert reply == summary
    assert summary.startswith("البرمجة (S01-m1) يوم الأحد الساعة 08:00 في القاعة")


@pytest.mark.parametrize("sentence,ok", [
    ("كل نقل ممكن يصطدم بشيء.", True),
    ("الفراغ ساعتان.", True),                       # 2 is in the summary
    ("الفراغ ثلاث ساعات.", False),                  # 3 is not
    ("The gap is at 15:00.", False),
    ("The gap is at 11:00.", False),               # no times: the summary has them
    ("The gap is 10:00 to 12:00.", False),         # each time appears, the range is wrong
    ("It starts at 11 and ends at 14.", False),    # a bare hour is a time too
    ("16 or 19 students would clash.", True),      # counts from the summary
    ("Ask د. سارة القحطاني instead.", True),       # named in the summary
    ("Ask د. أحمد العلي instead.", False),          # not named in the summary
    ("Section S99 is the cause.", False),
    ("It is worse on Monday.", False),             # a day the summary never names
    ("I checked every move.", True),
])
def test_grounding(campus, sentence, ok):
    summary = summarize_gap(explain_gap(campus.u, campus.current, [], ENTITY, DAY), "en")
    assert sentence_is_grounded(sentence, summary, campus.u) is ok
    assert compose([summary], sentence, campus.u) == (
        f"{summary}\n\n{sentence}" if ok else summary)
