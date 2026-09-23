# Jadwal — Smart University Scheduling Agent

A timetable optimiser that treats accessibility as a hard requirement, and an
agent that lets an administrator change the schedule by talking to it, in
Arabic or English.

The principle: **the LLM never edits the schedule and never computes a number.**
It resolves entities and emits structured constraints. Deterministic Python
validates them, the administrator confirms, and CP-SAT guarantees every encoded
rule holds. Every applied change is versioned and can be undone.

## Run

```bash
uv sync
cp .env.example .env        # add your ANTHROPIC_API_KEY
uv run uvicorn api.main:app
```

Open <http://localhost:8000>.

The first **Run solver** takes about 30 s (three profiles solved in parallel)
and is then cached in `.cache/`. The optimiser is deterministic: the same seed
gives byte-identical schedules on every run.

Without an API key everything except the Agent tab works; the agent says it is
offline instead of failing.

## What it does

**1 · Compare** runs a conventional greedy baseline and three optimiser
profiles and puts every metric side by side.

| Metric | Baseline | Balanced profile |
|---|---|---|
| % students conflict-free | 87.7 | **100** |
| % repeaters conflict-free | 0.0 | **100** |
| Accessibility violations | 43 | **0** |
| Avg idle time / student / day | 17.8 min | **3.7 min** |
| Avg walking minutes | 5.84 | **2.80** |

The baseline mimics current practice — it avoids instructor, room and cohort
clashes and nothing else — so it fails exactly where real timetables fail: on
repeaters, who carry a course from a lower level, and on the students who need
accessible rooms.

**2 · Timetable** shows any student, cohort, instructor or room as a weekly
grid. Clashes are red, accessibility violations orange. It opens on a student
who needs accessible rooms, on the baseline, so the problem is visible before
the fix.

**3 · Agent** takes a request, resolves the entities, and proposes a structured
constraint. Nothing reaches the schedule until the administrator presses Apply
on the confirmation card. What-if previews the same thing without applying it.

**4 · Change log** lists every applied change with its timestamp.

## Demo

1. **Run solver.** Accessibility violations drop 43 → 0; repeaters conflict-free
   0% → 100%.
2. **Timetable** opens on student ST049 (needs accessible rooms) against the
   baseline: inaccessible rooms and 12-minute transits. Switch to *Optimised* —
   all clear.
3. Agent: `د. أحمد ما يقدر يدرّس الثلاثاء بعد الساعة ٢`
   Two instructors are named أحمد, so the agent asks which. Answer
   `د. أحمد العلي`, confirm the card, and the schedule re-solves with the
   smallest possible change.
4. Agent: `What if we close room B12?` → a preview with metric deltas and the
   number of meetings that would move. Apply it from the card.
5. Agent: `ليش عند إدارة الأعمال المستوى الثالث فراغ ٣ ساعات يوم الثلاثاء؟`
   The answer comes from `core/explain.py`, which tests each neighbouring class
   against every hard constraint and reports what actually blocks the move, or
   what the move would cost.
6. **Undo** on the change log or the agent panel.

## How the optimiser works

A profile-aware greedy pass builds a schedule that already satisfies every hard
constraint, then CP-SAT re-optimises it one neighbourhood at a time — a day, a
pair of instructors, a cohort — with the current objective as a hard upper
bound, so a round can only improve the schedule. Each round is solved by a
single worker under a deterministic budget, which is what makes the whole search
reproducible.

Hard: no instructor or room overlap, capacity, the two meetings of a section on
different days, instructor availability, accessible rooms for any section with a
student who needs one, and at most 6 walking minutes between consecutive classes
for those students. Soft, weighted by profile: student clashes (repeaters
weighted higher), idle gaps, long walks, wasted room capacity, instructor peak
load.

## Evaluation

`eval/requests.json` holds 50 requests, 60% Arabic and 40% English, mixing
constraints, what-ifs and questions, with ambiguous names, typos and dialect.

```bash
uv run python eval/run_eval.py
```

It prints accuracy per category and per language and lists every failure with
what the agent did instead. Solving is stubbed during evaluation, so it scores
the agent's decisions, not the solver.

## Layout

```
data/generator.py   seeded synthetic university
core/models.py      domain types
core/baseline.py    greedy scheduler (current practice)
core/warmstart.py   hard-feasible profile-aware start
core/solver.py      CP-SAT model + neighbourhood search
core/metrics.py     every number the UI shows
core/explain.py     deterministic explanations
agent/schemas.py    strict constraint schemas
agent/resolver.py   Arabic-aware fuzzy entity resolution
agent/describe.py   plain-language confirmation cards
agent/agent.py      the LLM tool loop
api/main.py         JSON API, serves web/
web/                the console (no build step)
```
