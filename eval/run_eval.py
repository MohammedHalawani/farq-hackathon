"""Score the agent's tool choices against eval/requests.json.

  uv run python eval/run_eval.py [--limit N] [--workers N]
  uv run python eval/run_eval.py --repeat 10 --ids 19,31      # pass rate per case
  uv run python eval/run_eval.py --repeat 10 --time-cases     # every case naming a day or an hour

Three workers by default: more trips Ollama cloud's concurrency limit (429),
and those errors score as failures.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agent.agent import AGENT, MODEL, Tools  # noqa: E402
from agent.schemas import parse_constraint  # noqa: E402
from api.state import SESSION  # noqa: E402

REQUESTS = Path(__file__).parent / "requests.json"


def same_constraint(got: dict, want: dict) -> bool:
    try:
        got = parse_constraint(got)
        want = parse_constraint(want)
    except Exception:
        return False
    if got.get("type") != want.get("type"):
        return False
    for k in set(got) | set(want):
        a, b = got.get(k), want.get(k)
        if isinstance(a, list) and isinstance(b, list):
            if sorted(a) != sorted(b):
                return False
        elif a != b:
            return False
    return True


def _missed(out: dict) -> bool:
    """A real miss: a specific name that matched nothing."""
    return any(l["count"] == 0 and not l["vague"] for l in out.get("lookups", []))


def _needs_a_name(out: dict) -> bool:
    """Either the query named nothing specific, or it matched several things."""
    return any(l["vague"] or l["count"] > 1 for l in out.get("lookups", []))


def grade(req: dict, out: dict) -> tuple[bool, str]:
    calls = out.get("calls", [])
    by_name: dict[str, list] = {}
    for name, args in calls:
        by_name.setdefault(name, []).append(args)
    made = lambda tool: by_name.get(tool, [])
    proposed = made("propose_constraint") + made("what_if")
    called = sorted(by_name) or ["nothing"]
    expect = req["expect"]
    kind = expect["kind"]
    reply = out.get("reply", "")

    if kind == "constraint":
        if not made("propose_constraint"):
            return False, f"never called propose_constraint (called: {called})"
        got = made("propose_constraint")[-1].get("constraint", {})
        if same_constraint(got, expect["constraint"]):
            return True, ""
        return False, f"proposed {json.dumps(got, ensure_ascii=False)}"

    if kind == "tool" and expect["tool"] == "what_if":
        if not made("what_if"):
            return False, f"never called what_if (called: {called})"
        got = made("what_if")[-1].get("constraint", {})
        if same_constraint(got, expect["constraint"]):
            return True, ""
        return False, f"previewed {json.dumps(got, ensure_ascii=False)}"

    if kind == "tool":
        tool, want_args = expect["tool"], expect.get("args", {})
        if not made(tool):
            return False, f"never called {tool} (called: {called})"
        for args in made(tool):
            if all(str(args.get(k)) == str(v) for k, v in want_args.items()):
                return True, ""
        return False, f"{tool} called with {json.dumps(made(tool), ensure_ascii=False)}"

    if kind == "ask_clarification":
        # It asked if it changed nothing and did not simply report "not found".
        if proposed:
            return False, "proposed a change instead of asking"
        if not reply:
            return False, "said nothing"
        if "choices" in expect:
            # the buttons come from the resolver: exactly these stored names
            shown = [c["name"] for c in out.get("choices") or []]
            if shown != expect["choices"]:
                return False, f"buttons {shown}, expected {expect['choices']}"
        # It asked if it punctuated a question, if a lookup came back vague or
        # ambiguous, or if it answered without touching a tool at all.
        if "?" in reply or "؟" in reply or _needs_a_name(out) or not calls:
            return True, ""
        return False, f"reported not-found instead of asking: {reply[:70]!r}"

    if kind == "not_found":
        if proposed:
            return False, "proposed a change for an entity that does not exist"
        if not made("get_entity"):
            return False, "never looked the entity up"
        if not _missed(out):
            return False, "no lookup came back empty for a specific name"
        return True, ""

    if kind == "no_timetable":
        # before a build it must neither change anything nor make a number up
        if proposed:
            return False, "proposed a change instead of answering"
        if not reply:
            return False, "said nothing"
        return True, ""

    return False, f"unknown expectation {kind}"


def run_sequence(req: dict) -> dict:
    """A coordinator's session on a fresh campus: state a setup rule, confirm
    it, ask before the build, build, then ask about the result. The build is
    real so the rule is checked on the timetable it produced."""
    from api.state import Session
    from core.models import slot_period

    sess = Session()
    history: list = []
    for n, st in enumerate(req["steps"], start=1):
        expect = st["expect"]
        if st.get("then") == "build" and "text" not in st:
            sess.generate_all()
            hit = [m for m, s in sess.current.slot.items()
                   if slot_period(s) in expect["slots"]]
            if hit:
                return {**req, "ok": False, "why": f"step {n}: {len(hit)} classes in "
                        "the break", "reply": ""}
            continue
        tools = Tools(sess, dry_run=True)
        try:
            out = AGENT.handle(st["text"], sess, history, tools=tools)
        except Exception as e:
            return {**req, "ok": False, "why": f"step {n}: {type(e).__name__}: {e}",
                    "reply": ""}
        history = out["history"]
        ok, why = grade({**req, "expect": expect}, out)
        if not ok:
            return {**req, "ok": False, "why": f"step {n}: {why}", "reply": out["reply"]}
        if st.get("then") == "apply":
            r = sess.apply_constraint(out["card"]["constraint"], "eval")
            if not r["ok"] or r.get("stage") != "setup":
                return {**req, "ok": False, "why": f"step {n}: not kept as a setup rule",
                        "reply": out["reply"]}
    return {**req, "ok": True, "why": "", "reply": ""}


def run_one(req: dict) -> dict:
    if "steps" in req:
        return run_sequence(req)
    tools = Tools(SESSION, dry_run=True)
    try:
        out = AGENT.handle(req["text"], SESSION, [], tools=tools)
    except Exception as e:
        out = {"reply": "", "calls": tools.calls, "lookups": tools.lookups,
               "error": f"{type(e).__name__}: {e}"}
    ok, why = grade(req, out)
    if out.get("error"):
        ok, why = False, out["error"]
    return {**req, "ok": ok, "why": why, "reply": out.get("reply", "")}


DAY_WORDS = re.compile(
    r"sunday|monday|tuesday|wednesday|thursday|week|"
    r"أحد|احد|اثنين|إثنين|ثلاثاء|أربعاء|اربعاء|خميس|اسبوع|أسبوع|بكرة",
    re.IGNORECASE,
)
HOUR_WORDS = re.compile(
    r"\b\d{1,2}\s*(?:am|pm)\b|\b(?:at|after|before)\s+\d|morning|afternoon|o'clock|"
    r"الساعه|الساعة|صباح|الظهر|العصر|[٠-٩]|من\s*\d|إلى\s*\d",
    re.IGNORECASE,
)


def _texts(req: dict) -> str:
    return " ".join([req.get("text", "")] + [s.get("text", "") for s in req.get("steps", [])])


def names_a_day_or_hour(req: dict) -> bool:
    t = _texts(req)
    return bool(DAY_WORDS.search(t) or HOUR_WORDS.search(t))


def stability(requests: list[dict], repeat: int, workers: int) -> int:
    """Run every case `repeat` times and print its pass rate."""
    jobs = [r for r in requests for _ in range(repeat)]
    with ThreadPoolExecutor(max_workers=workers) as pool:
        results = list(pool.map(run_one, jobs))
    by_id: dict[int, list] = defaultdict(list)
    for r in results:
        by_id[r["id"]].append(r)
    worst = 0
    print(f"{'case':>5}  {'pass':>6}  text")
    for i in sorted(by_id):
        rows = by_id[i]
        n = sum(1 for r in rows if r["ok"])
        flag = "" if n == len(rows) else "  <-"
        print(f"  #{i:<3} {n:>2}/{len(rows):<3} {rows[0]['text'][:60]}{flag}")
        for why in sorted({r["why"][:110] for r in rows if not r["ok"]}):
            print(f"         {why}")
        worst = max(worst, len(rows) - n)
    total = sum(1 for r in results if r["ok"])
    print(f"\n  {total}/{len(results)} runs passed across {len(by_id)} cases")
    return 0 if worst == 0 else 1


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int)
    ap.add_argument("--workers", type=int, default=3)
    ap.add_argument("--repeat", type=int, default=1, help="runs per case; prints pass rates")
    ap.add_argument("--ids", help="comma-separated case ids")
    ap.add_argument("--time-cases", action="store_true",
                    help="only the cases whose text names a day or an hour")
    args = ap.parse_args()

    ok, why = AGENT.available()
    if not ok:
        print(why)
        return 2

    requests = json.loads(REQUESTS.read_text())
    if args.ids:
        wanted = {int(x) for x in args.ids.split(",")}
        requests = [r for r in requests if r["id"] in wanted]
    if args.time_cases:
        requests = [r for r in requests if names_a_day_or_hour(r)]
    if args.limit:
        requests = requests[: args.limit]

    print("Generating the schedule the agent will reason over …", flush=True)
    SESSION.generate_all()
    if args.repeat > 1:
        print(f"Running {len(requests)} cases x {args.repeat} on {MODEL} …\n", flush=True)
        return stability(requests, args.repeat, args.workers)
    print(f"Running {len(requests)} requests on {MODEL} …\n", flush=True)

    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        results = list(pool.map(run_one, requests))
    results.sort(key=lambda r: r["id"])

    by_cat: dict[str, list] = defaultdict(list)
    by_lang: dict[str, list] = defaultdict(list)
    for r in results:
        by_cat[r["category"]].append(r)
        by_lang[r["lang"]].append(r)

    def line(label: str, rows: list) -> str:
        n = sum(1 for r in rows if r["ok"])
        pct = 100 * n / len(rows)
        return f"  {label:<20} {n:>3}/{len(rows):<3} {pct:5.1f}%"

    print("Accuracy by category")
    for cat in sorted(by_cat):
        print(line(cat, by_cat[cat]))
    print("\nAccuracy by language")
    for lang in sorted(by_lang):
        print(line(lang, by_lang[lang]))
    total = sum(1 for r in results if r["ok"])
    print(f"\n  {'OVERALL':<20} {total:>3}/{len(results):<3} {100 * total / len(results):5.1f}%")

    failures = [r for r in results if not r["ok"]]
    if failures:
        print(f"\nFailures ({len(failures)})")
        for r in failures:
            print(f"  #{r['id']:<3} [{r['category']}/{r['lang']}] {r['text']}")
            print(f"       -> {r['why']}")
            if r["reply"]:
                print(f"       reply: {r['reply'][:110].strip()}")
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
