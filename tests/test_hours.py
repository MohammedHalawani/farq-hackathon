"""Hours are converted by code: the model writes clock times, never slot numbers."""

import pytest

from agent.schemas import parse_constraint, to_hour


@pytest.mark.parametrize("given,hour", [
    ("08:00", 8), ("8:00", 8), ("8", 8), (8, 8), ("١٢:٠٠", 12), ("١٢", 12),
    ("12:00", 12), ("12", 12), (12, 12), ("12.00", 12),
    ("13:00", 13), ("14", 14), (14, 14), ("16:00", 16), ("١٦:٠٠", 16),
    # no am/pm and before 8: the afternoon, since teaching starts at 08:00
    ("1", 13), ("٢", 14), (2, 14), ("3:00", 15), ("٤", 16),
    ("2pm", 14), ("2 pm", 14), ("2 PM", 14), ("2 p.m.", 14), ("٢ م", 14), ("٢ مساء", 14),
    ("١ ظهرا", 13), ("10am", 10), ("10 am", 10), ("١٠ ص", 10), ("10 صباحا", 10),
    ("12pm", 12), (" 14:00 ", 14),
])
def test_every_form(given, hour):
    assert to_hour(given) == hour


@pytest.mark.parametrize("bad,why", [
    ("07:00", "outside the teaching day"), ("17:00", "outside the teaching day"),
    ("7am", "outside the teaching day"), ("١٧", "outside the teaching day"),
    ("20", "outside the teaching day"), ("12:30", "not on the hour"),
    ("noon", "not a clock time"), ("بعد الظهر", "not a clock time"), ("", "not a clock time"),
    (True, "not a time"),
])
def test_rejected_with_a_clear_message(bad, why):
    with pytest.raises(ValueError, match=why):
        to_hour(bad)


def _brk(**times):
    return parse_constraint({"type": "campus_break", **times})["slots"]


def _unavailable(**times):
    return parse_constraint({"type": "instructor_unavailable", "instructor_id": "I01",
                             "days": ["Tuesday"], **times})["slots"]


def test_from_and_to():
    assert _brk(**{"from": "12:00", "to": "13:00"}) == [4]
    assert _brk(**{"from": "١٢", "to": "١"}) == [4]           # «من ١٢ إلى ١»
    assert _brk(**{"from": "10", "to": "12"}) == [2, 3]


def test_after_is_from_that_hour_to_the_end_of_the_day():
    assert _unavailable(**{"from": "14:00"}) == [6, 7]         # "after 2"
    assert _unavailable(**{"from": "٢"}) == [6, 7]             # «بعد ٢»
    assert _brk(**{"from": "12:00"}) == [4, 5, 6, 7]           # afternoon
    assert _brk(**{"from": "14:00", "to": ""}) == [6, 7]


def test_before_is_from_the_start_of_the_day_to_that_hour():
    assert _unavailable(**{"to": "10:00"}) == [0, 1]           # "before 10"
    assert _brk(**{"to": "12:00"}) == [0, 1, 2, 3]             # morning
    assert _brk(**{"from": None, "to": "10"}) == [0, 1]


def test_whole_day_for_a_person_or_a_section_but_not_for_a_break():
    assert _unavailable() == "all"
    assert _unavailable(**{"from": "08:00", "to": "16:00"}) == "all"
    sec = parse_constraint({"type": "section_avoid_slots", "section_id": "S19",
                            "days": ["Thursday"]})
    assert sec["slots"] == list(range(8))
    with pytest.raises(ValueError, match="say which hours"):
        _brk()


def test_slots_still_accepted_and_clock_times_win():
    assert _brk(slots=[4]) == [4]
    assert _unavailable(slots=[6, 7]) == [6, 7]
    assert _unavailable(slots="all") == "all"
    assert _brk(**{"from": "12:00", "to": "13:00"}, slots=[5]) == [4]


@pytest.mark.parametrize("times,why", [
    ({"from": "07:00"}, "outside the teaching day"),
    ({"to": "17:00"}, "outside the teaching day"),
    ({"from": "16:00"}, "no teaching hour"),
    ({"from": "13:00", "to": "12:00"}, "not after"),
    ({"from": "12:00", "to": "12:00"}, "not after"),
    ({"from": "12:30"}, "not on the hour"),
])
def test_bad_ranges_are_rejected(times, why):
    with pytest.raises(ValueError, match=why):
        _brk(**times)


def test_the_eval_expectations_still_compare_equal():
    # eval/requests.json keeps slot numbers; a clock-time proposal must match them
    got = parse_constraint({"type": "instructor_unavailable", "instructor_id": "I05",
                            "days": ["Wednesday"], "to": "10:00"})
    want = parse_constraint({"type": "instructor_unavailable", "instructor_id": "I05",
                             "days": [3], "slots": [0, 1]})
    assert got == want
