# Smart University Scheduling Agent

Timetable optimizer (OR-Tools CP-SAT) plus an LLM agent that lets an administrator
add constraints, run what-if scenarios and ask for explanations, in Arabic or English.

## Run

```bash
uv sync
cp .env.example .env   # add your ANTHROPIC_API_KEY
uv run uvicorn api.main:app
```

Then open http://localhost:8000
