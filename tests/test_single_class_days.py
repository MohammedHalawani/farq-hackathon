"""avoid_single_class_days: an opt-in preference. Without it, nothing moves."""

import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).parent))
from _fingerprint import model_hash, warmstart_hash  # noqa: E402

from agent.agent import Tools
from agent.describe import describe
from agent.schemas import parse_constraint
from core.baseline import build_baseline
from core.explain import explain_gap, summarize_gap
from core.metrics import compute, full_metrics, student_day_meetings
from core.solver import PROFILES, single_day_scope
from data.generator import generate

RULE = {"type": "avoid_single_class_days"}
NOON = {"type": "campus_break", "days": [0, 1, 2, 3, 4], "slots": [4]}

# the CP-SAT model (names cleared) and the greedy start on main, before the rule
MAIN = {
    "none/student_friendly": ("5ffc6c623fd47294b8a28944a6322cdd6f110a387193f4dac1490b737e663769",
        "f15e1b722955f70ce199f443b4e762b9588dcc28e0d9473d200917a7f4863959"),
    "none/room_efficient": ("2ee678ebd2cdfd316546fab7eeeec898872226d8e637742a375ecca4324c91fe",
        "f848b0dde21772da04fe7c9ac015e3a22103cd4c79edc921097e88479816c1be"),
    "none/balanced": ("6c55d0950c7d9398767e1ab0adcfdaf4f11dbbf25781c2d614fdfc5c4e792bc9",
        "66277a2524d603085de6dd077c4c81cc0007bd52bfb0d271c7b6a4ce29273b9e"),
    "noon/student_friendly": ("3fbf49e88d7d420b13f10f647fd09fbd4f74dc520f367cbb3252b89aed9fea25",
        "333bacd18d82ccaa023c11f90e331845c18338df4152b7b8cc5ea9a2c0a21289"),
    "noon/room_efficient": ("fc3787983c4fa8abf6ecf6c3021a63078162f1e0a5943f02f861b574602b83ea",
        "4e6067e4a2c69af9dca5fb053b0e008b2176bac678ea9d5f97e271a53936d836"),
    "noon/balanced": ("e05b1f37863fac790462f0a55789dbb76a95d44c2803157072c73a00c30d8721",
        "333bacd18d82ccaa023c11f90e331845c18338df4152b7b8cc5ea9a2c0a21289"),
}


@pytest.fixture(scope="module")
def u():
    return generate()


# --- without the rule nothing changes ---------------------------------------


@pytest.mark.parametrize("key", sorted(MAIN))
def test_without_the_rule_the_model_and_start_are_main_s(u, key):
    which, profile = key.split("/")
    rules = [] if which == "none" else [NOON]
    assert (model_hash(u, profile, rules), warmstart_hash(u, profile, rules)) == MAIN[key]


def test_the_rule_does_change_the_model(u):
    assert model_hash(u, "balanced", [RULE]) != MAIN["none/balanced"][0]
    assert model_hash(u, "balanced", [NOON, RULE]) != MAIN["noon/balanced"][0]


def test_existing_weights_are_untouched():
    old = {
        "student_friendly": {"conflict": 1000, "repeater_conflict": 2500, "idle": 40, "walk": 15, "waste": 1, "peak": 5},
        "room_efficient": {"conflict": 1000, "repeater_conflict": 2500, "idle": 5, "walk": 3, "waste": 10, "peak": 5},
        "balanced": {"conflict": 1000, "repeater_conflict": 2500, "idle": 20, "walk": 8, "waste": 4, "peak": 8},
    }
    for name, weights in old.items():
        assert {k: PROFILES[name][k] for k in weights} == weights


def test_compute_is_unchanged_and_the_new_figure_sits_beside_it(u):
    a = build_baseline(u)
    base = compute(u, a)
    full = full_metrics(u, a)
    assert {k: full[k] for k in base} == base
    by_hand = sum(
        1 for st in u.students
        if any(len({p for p, _, _ in ms}) == 1 for ms in student_day_meetings(u, a, st.id).values())
    )
    assert full["pct_students_with_single_class_day"] == round(100 * by_hand / len(u.students), 1)


# --- the rule ------------------------------------------------------------------


def test_schema():
    assert parse_constraint(RULE) == {"type": "avoid_single_class_days", "cohort": None}
    assert parse_constraint({**RULE, "cohort": "CS-L3"})["cohort"] == "CS-L3"
    with pytest.raises(ValueError):
        parse_constraint({**RULE, "weight": 9})


def test_scope(u):
    assert single_day_scope(u, []) is None
    assert single_day_scope(u, [NOON]) is None
    assert single_day_scope(u, [RULE]) == {st.id for st in u.students}
    cs3 = single_day_scope(u, [{**RULE, "cohort": "CS-L3"}])
    assert cs3 and all(u.student_by_id[s].department == "CS" and u.student_by_id[s].level == 3
                       for s in cs3)


def test_card_is_a_preference_in_both_languages(u):
    d = describe(u, parse_constraint(RULE))
    ar = d["title_ar"] + " · " + " · ".join(r.get("value_ar") or r["value"] for r in d["rows"])
    en = d["title_en"] + " · " + " · ".join(r["value"] for r in d["rows"])
    assert ar.startswith("تقليل الأيام التي فيها محاضرة واحدة فقط · كل الطلاب")
    assert "منع" not in ar
    assert "preference" in en and "all students" in en
    assert describe(u, parse_constraint({**RULE, "cohort": "CE-L2"}))["rows"][0]["value"] == "CE-L2"


def test_the_agent_accepts_it_and_checks_the_cohort(u):
    t = Tools(SimpleNamespace(u=u, current=None))
    out = t.run("propose_constraint", {"constraint": {**RULE, "cohort": "CS-L3"}})
    assert out["status"] == "awaiting_confirmation" and t.card is not None
    bad = Tools(SimpleNamespace(u=u, current=None)).run(
        "propose_constraint", {"constraint": {**RULE, "cohort": "XX-L9"}})
    assert "error" in bad and "cohort" in bad["error"]


def test_a_one_class_day_is_explained_in_both_languages(u):
    a = build_baseline(u)
    out = explain_gap(u, a, [], "BA-L2", 2)              # Tuesday: only Operations at 08:00
    assert out["single_class"]["hour"] == "08:00" and out["moves_considered"]
    ar, en = summarize_gap(out, "ar"), summarize_gap(out, "en")
    assert ar.startswith("يوم الثلاثاء لـ BA-L2 فيه محاضرة واحدة فقط: إدارة العمليات الساعة 08:00.")
    assert en.startswith("BA-L2 has only one class on Tuesday: Operations at 08:00.")
    assert ar.count("\n• ") == en.count("\n• ") == len(out["moves_considered"])
