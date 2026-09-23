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
ollama signin                        # once; cloud models only, nothing runs locally
ollama pull gpt-oss:120b-cloud

./serve.sh                           # or: ./serve.sh 8001
```

Open <http://localhost:8000>.

`serve.sh` syncs dependencies, starts Ollama if it is not already up, tells you
whether the agent model is available, and serves the console. The long form is
`uv sync && uv run uvicorn api.main:app`.

The first **Run solver** takes about 35 s: three profiles solved in parallel,
~30 s each, then cached in `.cache/`. Results are deterministic — the same seed
produces byte-identical schedules on every run, on any machine, because a solve
is bounded by a fixed number of search rounds rather than by the clock. A slower
machine takes longer; it does not get a different answer.

Without Ollama running, everything except the Agent tab works; the agent says
what is missing instead of failing.

## What the optimiser buys

Baseline is a conventional greedy scheduler. It avoids instructor, room and
cohort clashes, and staggers each level against the one below so a student
repeating a course has some chance of fitting it in — the way a registrar
does. What it never does is look at an individual student, and it ignores
accessibility completely.

| Metric | Baseline | Student-friendly | Room-efficient | **Balanced** |
|---|---|---|---|---|
| Accessibility violations | 40 | 0 | 0 | **0** |
| % repeaters conflict-free | 54.1 | 100.0 | 100.0 | **100.0** |
| % students conflict-free | 94.3 | 100.0 | 100.0 | **100.0** |
| Total student clashes | 38 | 0 | 0 | **0** |
| % students with a 2h+ gap | 44.0 | 1.0 | 3.7 | **0.7** |
| % students with any gap | 88.7 | 18.3 | 29.7 | **14.3** |
| Avg idle minutes / student / day | 31.2 | 2.5 | 4.8 | **2.0** |
| Avg walking minutes | 5.49 | 3.35 | 2.11 | **2.27** |
| Avg room fill rate | 0.789 | 0.750 | 0.821 | **0.805** |
| Instructor load std. dev. | 0.34 | 0.499 | 0.618 | **0.471** |

Read the gap rows, not the average. A 5-course load is about two classes a day,
so the *average* idle time is small either way; the damage is concentrated.
Under the baseline **44% of students have an unbroken 2-hour hole in some day**
and 88.7% have at least one gap. The optimiser takes that to 0.7% and 14.3%.

The staggering the baseline does is real but only half-works: it rescues 54% of
repeaters and silently fails the rest. That is the honest shape of current
practice — not a strawman that fails everyone.

The one row the optimiser loses is instructor load spread (0.34 → 0.471). The
baseline spreads teaching evenly because it has nothing else to satisfy; the
optimiser trades a little of that for zero clashes and zero accessibility
violations. The profiles differ mainly on room fill and walking, since idle time
is already near zero for all three.

**Not a proven optimum.** The optimiser does neighbourhood search: it improves
one piece of the schedule at a time and never makes it worse. It returns a far
better schedule than the baseline, not a mathematically optimal one.

## The views

**1 · Compare** — baseline against the three profiles, every metric side by side.

**2 · Timetable** — any student, cohort, instructor or room as a weekly grid.
Clashes red, accessibility violations orange. Opens on a student who needs
accessible rooms, showing the baseline, so the problem is visible before the fix.

**3 · Agent** — resolves entities, proposes a structured constraint, and waits.
Nothing reaches the schedule until Apply is pressed. What-if previews without
applying.

**4 · Change log** — every applied change with its timestamp.

**Motion** is three primitives and one functional loader, per Hallmark's ceiling:
the headline figures count up, rows and cells reveal in a one-shot stagger, and
the meetings a re-solve moved flash once so "31 moved" is something you can see
rather than read. The solve bar is driven by real work — one tick per search
round, 39 of them — not a timer. Everything animates `transform` and `opacity`
only, and `prefers-reduced-motion` collapses all of it to a crossfade.

## Demo

Ask the questions before making the changes — a change reshuffles the schedule,
so a gap you asked about may no longer be there afterwards.

1. **Run solver** (~35 s) — accessibility violations 40 → 0, repeaters
   conflict-free 54% → 100%, students with a 2h+ gap 44% → 0.7%.
2. **Timetable** opens on student ST049, who needs accessible rooms, showing the
   baseline: 10 flagged meetings, inaccessible rooms and 12-minute transits.
   Switch to *Optimised* — zero.
3. Agent: `ليش عند عمارة المستوى الثاني فراغ ٣ ساعات يوم الخميس؟` (~4 s). The
   answer comes from `core/explain.py`, which tries every neighbouring class in
   every gap slot and reports what happened to each one: *"د. أحمد الغامدي
   already teaches Visual Communication then"*, *"د. أحمد الغامدي is not
   available at 12:00"*, *"nothing forbids the move, but it would clash with 19
   students' other classes"*, and — honestly — *"the move is allowed but
   pointless: it would not shorten any student's day"*.
4. Agent: `د. أحمد ما يقدر يدرّس الثلاثاء بعد الساعة ٢` — two instructors are
   named أحمد, so it asks which. Answer `د. أحمد العلي`, confirm the card, and
   the schedule re-solves in ~5 s **moving 2 meetings out of 120**.
5. Agent: `What if we close room B12?` (~9 s) — B12 carries 27 meetings, so the
   preview shows real movement: 31 meetings and the metric deltas. Apply it from
   the card. The preview and the apply run the identical solve, so the applied
   result matches the preview exactly.
6. **Undo** — instant, and it restores both the schedule and the rule list.

**When the agent is asked for something impossible** — say an instructor is
blocked Sunday–Tuesday and then also Wednesday–Thursday — the re-solve fails,
nothing is applied, and the card names the earlier rule it conflicts with:
*"Surveying (S17, د. أحمد العلي) has no slot left under these rules"* →
conflicts with *"Instructor unavailable — د. أحمد العلي · Sunday, Monday,
Tuesday · all day"*. It takes under a second.

## How the optimiser works

A profile-aware greedy pass builds a schedule that already satisfies every hard
constraint. CP-SAT then re-optimises it one neighbourhood at a time — a day, a
pair of instructors, a cohort — with the current objective as a hard upper
bound, so a round can only improve the schedule or leave it alone. Each round is
solved by a single worker under a deterministic budget, which is what makes the
whole search reproducible.

Hard constraints: no instructor or room overlap, room capacity, the two meetings
of a section on different days, instructor availability, an accessible room for
any section carrying a student who needs one, and at most 6 walking minutes
between consecutive classes for those students.

Soft, weighted by profile: student clashes (repeaters weighted higher), idle
gaps, long walks, wasted room capacity, instructor peak load.

Re-solves after a confirmed change are repairs, not rebuilds. Every placement
that is still legal under the new rule is held fixed and only the broken ones
are re-placed, then CP-SAT polishes with a penalty on every meeting that moved.
Blocking an instructor for one afternoon moves 2 meetings out of 120; closing a
room that hosts 27 meetings moves 31. A re-solve takes about 5–6 seconds, and
what-if runs the same solve so its preview is exact rather than indicative.

## Evaluation

`eval/requests.json` holds 50 requests, 60% Arabic and 40% English, mixing
constraints, what-ifs and questions, with ambiguous names, English
transliterations of Arabic names, typos and dialect.

```bash
uv run python eval/run_eval.py
```

Current result on `gpt-oss:120b-cloud`: **50/50**, stable across repeated runs
(it was 38/50 before the resolver fixes below).

Treat that as a regression suite, not a held-out benchmark — the system prompt
and the resolver were fixed against these cases. The fixes were general, not
per-case: English transliterations for every instructor, stripping generic nouns
("شعبة S19" → `S19`), treating the `kind` argument as a hint rather than a
filter, and matching entity IDs exactly instead of fuzzily. Every failure the
eval ever caught was caught at the confirmation card — the agent proposed, it
never applied.

Solving is stubbed during evaluation, so it scores the agent's decisions, not
the solver.

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
agent/resolver.py   Arabic/English fuzzy entity resolution
agent/describe.py   plain-language confirmation cards
agent/agent.py      the Ollama tool loop
api/main.py         JSON API, serves web/
web/                the console (no build step)
```
