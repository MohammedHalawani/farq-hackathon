# Jadwal — the semester timetable, built in seconds

Today a university timetable is built **by hand**: one level at a time, from the
study plan and the number of sections, typed into an Excel file and then retyped
into the registration system. It takes **one to one and a half weeks** each
semester. The hardest part is avoiding long gaps in students' days, and once the
file goes to the supervisor, nothing can change. (Source: a timetable
coordinator at our university.)

Jadwal replaces that process with one pipeline:

| Step | What happens | Who does it |
|---|---|---|
| 1 · Data in | The coordinator uploads the Excel file she already prepares. Every cell is parsed and validated by code, with row-numbered errors in Arabic and English. | code, **no LLM** |
| 2 · Rules in | She states rules in Arabic ("لا محاضرات من ١٢ إلى ١"). The agent turns each into a schema-checked rule; she confirms it. | agent + admin |
| 3 · Build | CP-SAT builds every level at once: no instructor, room or student clashes, minimal gaps. ~35 s. | solver, **no LLM** |
| 4 · Review and change | "Why is there a gap?" gets a deterministic answer. Changes after hand-off re-solve with the smallest possible move. | agent + solver |
| 5 · Data out | She downloads the finished timetable as Excel, one sheet per level. | code |

The principle: **the LLM never edits the schedule, never reads the data file and
never computes a number.** Data comes from code. The LLM only turns a sentence
into a structured constraint, which deterministic Python validates, the
administrator confirms, and CP-SAT guarantees. Every applied change is
versioned and can be undone.

## The workbook

`GET /api/data/template` (or **Download the template** on the Data tab) gives the
built-in demo campus in this format. Upload it unchanged and you get exactly the
same campus: `tests/test_excel_roundtrip.py` checks that the baseline metrics
are identical, and the solver produces byte-identical schedules.

Sheet names may be Arabic, English or both (`الشعب (Sections)`). Headers may be
the Arabic label, the English key, or `label (key)` as the template writes them.

| Sheet | Columns | Notes |
|---|---|---|
| `Courses` | `course_code`, `name_ar`, `name_en`?, `department`, `level`, `needs_lab`? | yes/no, default no |
| `Sections` | `section_id`, `course_code`, `instructor_name`, `enrollment`?, `cohorts`? | enrollment defaults to 20; `cohorts` (e.g. `CS-L1,CS-L2`) are the level timetables this section is blocked against, derived from the student groups if empty |
| `StudentGroups`? | `group_id`, `department`, `level`, `student_count`, `section_ids`, `repeater`?, `needs_accessibility`? | optional, see below |
| `Rooms` | `room_id`, `building`, `capacity`, `accessible`?, `kind`? | kind is `lecture` (default) or `lab` |
| `Buildings`? | `building_id`, `name_ar`?, `name_en`?, then one column per building id with walking minutes | or a `WalkMinutes` sheet (`from_building`, `to_building`, `minutes`); 5 minutes assumed where missing |
| `Instructors`? | `instructor_name`, `name_en`?, `unavailable`? | e.g. `Tue 14-16; Sun all` (Arabic day names work too) |

`?` marks optional. Every section meets twice a week on different days, one hour
each, 08:00–16:00.

**Without `StudentGroups`** the groups are derived the way the coordinator works:
for each department and level, `k` groups where `k` is the most sections any
course in that level has; group `g` takes section `g mod n` of each course, and
the level's enrollment is split evenly across its groups. The report says so.

**The validation report** lists errors (unknown course code, section without an
instructor, capacity ≤ 0, a group naming a section that does not exist, no room
large enough, an instructor with more meetings than free hours) and warnings,
each with its sheet and row. Errors block the upload and leave the current
campus loaded; warnings do not. The same file always produces the same campus:
IDs are assigned in order of first appearance.

**Download the result** with `GET /api/data/export` or the button on the
Timetable tab: a `Timetable` sheet with one row per meeting (level, course,
section, instructor, day, time, room, building, the per-section form filled in
by hand today) and one day × hour grid per level. Sheets are right-to-left.

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

The first **Build the timetable** takes about 35 s: three profiles solved in parallel,
~30 s each, then cached in `.cache/`. Results are deterministic — the same seed
produces byte-identical schedules on every run, on any machine, because a solve
is bounded by a fixed number of search rounds rather than by the clock. A slower
machine takes longer; it does not get a different answer.

Without Ollama running, everything except the Agent tab works (including the whole Data tab: upload, build, download); the agent says
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

**0 · Data**: the coordinator's job as three numbered steps: bring in the
workbook (with its validation report), the confirmed setup rules, and the build,
with its elapsed time beside «يدويًا: أسبوع إلى أسبوع ونص». On uploaded data,
which has no personas, the Timetable opens on the first cohort.

**1 · Compare** — baseline against the three profiles, every metric side by side.

**2 · Timetable** — opens on **Noura**, who needs accessible rooms, showing the
baseline. A persona switcher sits above the grid: Noura, **Faisal** (repeating
Statics), and **د. أحمد العلي**. Their IDs are pinned in the generator and a test
asserts the baseline really does fail them.

A **Before / after** mode puts the baseline and the optimised schedule side by
side for the same person, each with a problem count, and labels every bad cell
in words: *"Structural Analysis and Statics both at 10:00"*, *"Room B1-202 ·
floor 2 · no step-free access"*, *"12 min walk (limit 6)"*. Cleared cells are
ticked. Every one of those strings is built in `core/metrics.py`.

**3 · Agent** — resolves entities, proposes a structured constraint, and waits.
Nothing reaches the schedule until Apply is pressed. What-if previews without
applying.

Beside the chat a **step tracker** shows what the agent actually did — read
request, entity resolution (with the match count), rule built, schema
validation, waiting for approval, then re-solving (kept vs moved) and a rules
check. Steps appear one at a time. On an impossible rule the failing step turns
red and names the rule it conflicts with. The trace is assembled in Python from
the lookups and the solve; the model does not write it.

After a change the timetable shows each moved meeting's **old slot as a faded
dashed ghost** and outlines where it landed, with a side list reading
*"Landscape S55: Tuesday 15:00 · B1-103 → Tuesday 12:00 · B1-103"*. Ask why a
gap exists and the gap slots are hatched, with an icon and a short reason on
every class that tried to fill it.

**4 · Change log**: every applied change with its timestamp.

**Setup rules.** Before the first build the agent still proposes and the admin
still confirms, but a confirmed rule is kept, after a feasibility check, and every
profile is built with it. Two rule types exist for this: `campus_break` (no
class for anyone in those hours, e.g. a prayer break) and `course_needs_lab`
(only rooms of kind `lab`). Tools that read a timetable answer *no timetable
built yet* until one exists.

**Motion** is three primitives and one functional loader, per Hallmark's ceiling:
the headline figures count up, rows and cells reveal in a one-shot stagger, and
the meetings a re-solve moved flash once so "31 moved" is something you can see
rather than read. The solve bar is driven by real work — one tick per search
round, 39 of them — not a timer. Everything animates `transform` and `opacity`
only, and `prefers-reduced-motion` collapses all of it to a crossfade.

## Demo

The pipeline, from a fresh clone (`rm -rf .cache`), about four minutes:

1. **Data** tab → **Download the template**, then drag it back onto the upload
   box. The report shows 16 levels, 40 courses, 60 sections, 300 students,
   **0 errors, 0 warnings**.
2. **Agent**: `لا محاضرات من ١٢ إلى ١` → a *Campus break* card (every day,
   12:00–13:00). Confirm. It is checked for feasibility (under a second) and
   saved as a setup rule, listed under step 2 on the Data tab.
3. **Build the timetable** (~40 s) next to «يدويًا: أسبوع إلى أسبوع ونص». It
   jumps to the Timetable, where no class sits at 12:00 (0 of 120 meetings; the
   downloaded Excel confirms it).
4. **Agent**: `ليش عند عمارة المستوى الثاني فراغ يوم الاثنين؟`. AR-L2 has 11:00–14:00
   empty on Monday. The answer comes from `core/explain.py`: one of the
   reasons is the campus break the coordinator just added.
5. **Agent**: `د. أحمد ما يقدر الثلاثاء بعد ٢`. Two instructors are named أحمد,
   so it asks which. Answer `د. أحمد العلي`, confirm the card, and the timetable
   re-solves in ~7 s, **moving 5 meetings out of 120**.
6. **Timetable** → **Download timetable (Excel)**.
7. **Change log** → **Undo**. The change is gone and the setup rule stays.

One honest caveat: the gap metrics count a campus break hour as idle, like any
other empty hour between two classes. With the 12–1 break, balanced goes from
0.7% to 2.3% of students with a 2h+ gap. The objective was deliberately left
unchanged.

The optimiser story on the untouched demo campus (no setup rules). Ask the
questions before making the changes: a change reshuffles the schedule, so a
gap you asked about may no longer be there afterwards.

1. **Use the demo campus**, then **Build the timetable** (~35 s): accessibility
   violations 40 → 0, repeaters conflict-free 54% → 100%, students with a 2h+
   gap 44% → 0.7%.
2. **Timetable** opens on student ST049, who needs accessible rooms, showing the
   baseline: 10 flagged meetings, inaccessible rooms and 12-minute transits.
   Switch to *Optimised*: zero.
3. Agent: `ليش عند عمارة المستوى الثاني فراغ ٣ ساعات يوم الخميس؟` (~4 s). The
   answer comes from `core/explain.py`, which tries every neighbouring class in
   every gap slot and reports what happened to each one: *"د. أحمد الغامدي
   already teaches Visual Communication then"*, *"د. أحمد الغامدي is not
   available at 12:00"*, *"nothing forbids the move, but it would clash with 19
   students' other classes"*, and, honestly, *"the move is allowed but
   pointless: it would not shorten any student's day"*.
4. Agent: `د. أحمد ما يقدر يدرّس الثلاثاء بعد الساعة ٢`. Answer `د. أحمد العلي`,
   confirm the card, and the schedule re-solves in ~5 s **moving 2 meetings out
   of 120**.
5. Agent: `What if we close room B12?` (~9 s). B12 carries 27 meetings, so the
   preview shows real movement: 31 meetings and the metric deltas. Apply it from
   the card. The preview and the apply run the identical solve, so the applied
   result matches the preview exactly.
6. **Undo**: instant, and it restores both the schedule and the rule list.

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
between consecutive classes for those students. Plus, when present: campus
breaks, and lab rooms for courses that need a lab.

Soft, weighted by profile: student clashes (repeaters weighted higher), idle
gaps, long walks, wasted room capacity, instructor peak load.

Re-solves after a confirmed change are repairs, not rebuilds. Every placement
that is still legal under the new rule is held fixed and only the broken ones
are re-placed, then CP-SAT polishes with a penalty on every meeting that moved.
Blocking an instructor for one afternoon moves 2 meetings out of 120; closing a
room that hosts 27 meetings moves 31. A re-solve takes about 5–6 seconds, and
what-if runs the same solve so its preview is exact rather than indicative.

## Evaluation

`eval/requests.json` holds 60 cases, 62% Arabic and 38% English, mixing
constraints, setup rules (campus breaks, lab courses), what-ifs and questions, with ambiguous names, English
transliterations of Arabic names, typos and dialect.

```bash
uv run python eval/run_eval.py
```

Current result on `gpt-oss:120b-cloud`: **60/60**. The original 50 have been
stable across repeated runs (they were 38/50 before the resolver fixes below).
Case 60 is a whole session on a fresh campus: state a campus break, confirm it,
ask a question before the build, build (for real, and check that no class is in
the break), then ask about the result.

Treat that as a regression suite, not a held-out benchmark — the system prompt
and the resolver were fixed against these cases. The fixes were general, not
per-case: English transliterations for every instructor, stripping generic nouns
("شعبة S19" → `S19`), treating the `kind` argument as a hint rather than a
filter, and matching entity IDs exactly instead of fuzzily. Every failure the
eval ever caught was caught at the confirmation card — the agent proposed, it
never applied.

Solving is stubbed during evaluation, so it scores the agent's decisions, not
the solver. The one exception is the build in case 60.

## Layout

```
data/generator.py   seeded synthetic university
data/excel_io.py    the coordinator's workbook in and out
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
