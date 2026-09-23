"""Score the agent's tool choices against eval/requests.json.

  uv run python eval/run_eval.py [--limit N] [--workers N]
"""

from __future__ import annotations

import argparse
import json
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

    return False, f"unknown expectation {kind}"


def run_one(req: dict) -> dict:
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


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int)
    ap.add_argument("--workers", type=int, default=6)
    args = ap.parse_args()

    ok, why = AGENT.available()
    if not ok:
        print(why)
        return 2

    requests = json.loads(REQUESTS.read_text())
    if args.limit:
        requests = requests[: args.limit]

    print("Generating the schedule the agent will reason over …", flush=True)
    SESSION.generate_all()
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
