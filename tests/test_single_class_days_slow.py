"""Real builds, from an empty cache. About 40 s each, so opt-in:

    RUN_SLOW=1 uv run pytest tests/test_single_class_days_slow.py -s
"""

import os
import time

import pytest

import api.state as state_mod

pytestmark = pytest.mark.skipif(not os.environ.get("RUN_SLOW"), reason="set RUN_SLOW=1")

RULE = {"type": "avoid_single_class_days"}
NOON = {"type": "campus_break", "days": [0, 1, 2, 3, 4], "slots": [4]}
AHMED = {"type": "instructor_unavailable", "instructor_id": "I01", "days": [2], "slots": [6, 7]}


def build(tmp_path, rules, change=False):
    tmp_path.mkdir(parents=True, exist_ok=True)
    state_mod.CACHE = tmp_path / "cache"            # never a cached schedule
    s = state_mod.Session()
    for r in rules:
        assert s.apply_constraint(r, "test")["ok"]
    started = time.time()
    c = s.generate_all()
    out = {"seconds": round(time.time() - started, 1), "baseline": c["baseline"],
           "balanced": c["profiles"]["balanced"]["metrics"]}
    if change:
        out["moved"] = s.apply_constraint(AHMED, "test")["version"]["moved_count"]
    b, m = out["baseline"], out["balanced"]
    print(f"\n  {rules and '+'.join(r['type'] for r in rules) or 'no rules'}: build {out['seconds']}s"
          f" | 2h+ gap {b['pct_students_with_2h_gap']} -> {m['pct_students_with_2h_gap']}"
          f" | single-class-day {b['pct_students_with_single_class_day']}% -> "
          f"{m['pct_students_with_single_class_day']}% (days {b['single_class_days']} -> "
          f"{m['single_class_days']})" + (f" | change moves {out['moved']}" if change else ""))
    return out


def test_without_the_rule_the_demo_numbers_hold(tmp_path):
    plain = build(tmp_path / "a", [])
    assert (plain["baseline"]["pct_students_with_2h_gap"], plain["balanced"]["pct_students_with_2h_gap"]) == (44.0, 0.7)
    brk = build(tmp_path / "b", [NOON], change=True)
    assert (brk["baseline"]["pct_students_with_2h_gap"], brk["balanced"]["pct_students_with_2h_gap"]) == (32.7, 0.7)
    assert brk["moved"] == 6


@pytest.mark.parametrize("extra", [[], [NOON]], ids=["rule", "rule+break"])
def test_the_rule_cuts_single_class_days_without_long_gaps(tmp_path, extra):
    without = build(tmp_path / "off", extra)
    with_rule = build(tmp_path / "on", extra + [RULE], change=True)
    assert with_rule["balanced"]["single_class_days"] < without["balanced"]["single_class_days"]
    assert (with_rule["balanced"]["pct_students_with_single_class_day"]
            < without["balanced"]["pct_students_with_single_class_day"])
    assert with_rule["balanced"]["pct_students_with_2h_gap"] <= 1.5
    assert with_rule["seconds"] <= 60
