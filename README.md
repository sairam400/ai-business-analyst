# AI Business Analyst

Upload a CSV, get back a board-ready PDF report — with every number in it
checked against the source data before the report is allowed to render.

This is the third in a set of three projects built around one idea: LLM
output that reports numbers is only useful if those numbers can be trusted.
The first two projects dealt with retrieval and tool-use. This one is about
closing the loop on generation itself — instead of trusting an LLM to get
the math right, a separate verifier agent recomputes every cited figure
against the database and checks that the sentence citing it actually
describes what it claims. Anything that fails either check gets stripped
from the report rather than shipped.

**[Sample report →](docs/sample_report.pdf)** — a real run against
`--provider anthropic`, not the mock. The verifier caught and stripped two
claims from this exact run before it rendered; the reasoning is in
[`docs/verifier_catch_example.md`](docs/verifier_catch_example.md).

## How it works

```
CSV(s) --> profiler --> analyst --> writer --> verifier --> PDF
```

- **Profiler** inspects whatever tables got loaded (columns, types, null
  rates, detected foreign-key relationships) and asks the model what
  analyses actually make sense for *this* schema — it doesn't assume
  e-commerce data unless the columns say so.
- **Analyst** runs each suggested analysis through a tool-use loop
  (`run_sql`, `run_python`, `make_chart`) and finalizes each one as a typed
  `Finding` with the exact query that produced it.
- **Writer** turns the findings into executive prose. It's only allowed to
  state a number that traces back to a real finding id, and every sentence
  with a number has to carry a footnote (`[F3]`) — enforced structurally,
  with a retry loop if it slips.
- **Verifier** is the actual point of the project. For every citation in the
  draft it re-runs the finding's query against the live data and separately
  checks the citing sentence for faithfulness (right number, wrong label is
  still a failure). A citation that fails either check gets its sentence
  redacted and logged, not silently kept.
- **Renderer** turns the verified report into HTML (Jinja2) and PDF
  (WeasyPrint), with a sources table mapping every footnote back to its
  query and recomputed value.

A FastAPI backend wraps this as an upload-and-poll API, and a small React
frontend sits on top of that.

## Stack

Python (FastAPI, pydantic, pandas, SQLite, WeasyPrint), Anthropic/OpenAI as
swappable LLM providers behind one interface, React + Vite + TypeScript for
the frontend.

## Running it

**Fastest path — no server, no API key:**

```
pip install -r requirements.txt
python -m src.demo_cli
```

Runs the full pipeline against the bundled sample e-commerce dataset with a
scripted mock provider, prints every stage, writes `report.html` (and
`report.pdf` if your machine has WeasyPrint's native deps — see
`KNOWN_ISSUES.md`).

**Backend + frontend:**

```
cp .env.example .env        # add ANTHROPIC_API_KEY if you want real LLM calls
python -m uvicorn src.api.main:app --reload
cd frontend && npm install && npm run dev
```

Open the frontend, upload the CSVs in `data/sample/`, pick `mock` as the
provider if you don't have a key set, and watch it run.

**Eval harness**, for a real read on quality instead of a demo:

```
python -m src.eval.run_eval --provider anthropic --runs 5
```

Scores each run on groundedness (of the writer's citations, how many
survive the verifier) and coverage (of a handful of facts computed by hand
against the seeded sample data, how many did the analyst find). No golden
Q&A set required — the analyst picks its own questions; this checks whether
what it picks holds up.

Actual results, 5 runs against `claude-sonnet-4-5` in Docker:

| run | findings | failed tasks | citations passed | pass rate |
|---|---|---|---|---|
| `110b14ec1456` | 8 | 0 | 3/8 | 37.5% |
| `de67c197a806` | 8 | 0 | 5/8 | 62.5% |
| `40ca4c150c11` | 8 | 0 | 7/8 | 87.5% |
| `1efb2a9a1ee0` | 6 | 2 | 2/6 | 33.3% |
| `b1dfe2b52190` | 8 | 0 | 5/8 | 62.5% |
| **mean** | | | | **56.7%** |

Zero crashes across the 5 runs (that wasn't true before the analyst fix
above). Coverage came back 0/6 on every run, which is a real result but not
the one it looks like — see the gaps section below.

Mean pass rate of 56.7% is below the harness's own default gate (80%), so
it exits non-zero, which is correct: **most of the writer's citations
failed the verifier on real runs.** Looking at *why* (see
`docs/verifier_catch_example.md` for a worked example) — it's almost always
the semantic check, not the mechanical one. The number is right; the writer
adds framing the finding doesn't support ("monthly" for a single aggregate,
"per month" for a total count, "trend" for one data point). The verifier
catching that at a ~43% rate is the system working as designed, not a bug
— but it also means the writer's prompt needs to stop inviting that framing
in the first place. That's the honest next iteration, not something this
pass fixed.

**Docker:** `docker compose up` builds and runs the backend. `docs/sample_report.pdf`
was rendered this way — PDF output is confirmed working, not just wired up.

## Tests

```
python -m unittest discover -s tests
```

86 tests, all passing, covering every pipeline stage, the tool-use
guardrails (SQL injection, mutation smuggling, sandboxed `run_python`), the
verifier's redaction logic, and the API layer end to end.

## Where this is honest about its gaps

Full list in `KNOWN_ISSUES.md`, but the short version: everything above has
been tested against a scripted `MockProvider`, not a live Claude call, so
"the pipeline works" is verified — "the LLM's judgment is good" isn't, yet.
PDF rendering needs native Pango/Cairo libs that aren't available on this
dev machine outside Docker. The API has no auth, which is fine for local
use and not fine for putting it on the public internet as-is. None of these
are hidden — they're the actual next steps.
