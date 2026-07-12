# Known issues

- **WeasyPrint requires native Pango/Cairo libraries.** Running `src/report`
  natively on Windows without WSL will fail to import weasyprint unless a
  GTK3 runtime is installed separately. Confirmed working inside the
  project's Docker image (see below) — that's the supported path, not a
  workaround.
- **PDF rendering is now confirmed working for real**, not just wired up.
  `docker compose run --rm backend python -m src.demo_cli --provider
  anthropic` produced `docs/sample_report.pdf` — 5 pages, charts, footnote
  links, sources table, all rendering correctly. Previously this repo's
  `render_pdf` had only been tested against a faked `weasyprint` module;
  that gap is closed.
- **The writer's citations pass the verifier about 57% of the time on real
  runs**, not the ~100% the mock scenario implied. 5 eval runs against
  `claude-sonnet-4-5`, 38 citations total, 22 passed. Almost every failure
  is the semantic check catching correct numbers wrapped in framing the
  finding doesn't support — a single aggregate value described as
  "monthly," a total count described as "per month." See
  `docs/verifier_catch_example.md` for a worked example pulled straight
  from a run, no tampering. This means the verifier is doing its job; it
  also means the writer's prompt needs tightening against that specific
  failure pattern before this number goes up. That's the next real
  iteration, not something fixed in this pass.
- **The eval harness's coverage metric doesn't produce a meaningful number
  yet.** It scored 0/6 on every one of the 5 real runs. The 6 reference
  facts (`src/eval/reference.py`) are exact, hand-picked aggregate queries
  (overall return rate, top *category* by revenue); a real analyst tends to
  pick differently-scoped questions that are equally valid but don't match
  those exact facts (per-*product* revenue, per-category return rate
  breakdowns instead of one overall rate). Groundedness is the trustworthy
  metric right now — coverage needs a redesign (looser matching, or more
  representative reference facts) before its number means anything.
- **`run_python` is process-isolated, not sandboxed.** It runs in a subprocess
  with a scratch directory, a stripped environment, and a monkey-patched
  socket module to block outbound network calls, but it is not a real
  security boundary (no seccomp/container-per-call). Acceptable for a local
  demo tool operating on data the user already trusts; would need real
  sandboxing (e.g. gVisor, a per-call container) before running untrusted
  code server-side for multiple tenants.
- **`src/api/` has no authentication, rate limiting, or run expiry.** Any
  caller can trigger LLM calls (real spend, with `provider=anthropic` or
  `openai`) and every run's status.json/artifacts/uploaded CSVs persist under
  `runs/` and `data/uploads/` indefinitely -- fine for a local demo behind a
  trusted network, not for a public deployment. `CORS_ORIGINS` defaults to
  `*` for the same reason (no auth/cookies in play, but tighten it before
  exposing this beyond local dev). Chart embedding in the API's
  `GET .../report.html` (via `render_html`'s `chart_url_base` and the
  `GET .../charts/{chart_id}.png` endpoint) is plumbed but still untested
  against a real chart through that specific code path -- the live runs
  that produced charts so far went through `demo_cli`, not the API.
- **`frontend/` has no production serving story yet.** `npm run dev` proxies
  `/runs` and `/health` to `http://localhost:8000` (see `vite.config.ts`), and
  that's the only integration path exercised so far -- verified with a real
  `uvicorn` process and Playwright (upload the sample CSVs, poll to done,
  confirm no console errors), not just mocked. `npm run build` produces
  `frontend/dist`, but neither the `Dockerfile` nor `docker-compose.yml`
  build or serve it (both are backend-only); in production the built assets
  would need a static host or a reverse proxy in front of both services,
  since the app assumes `/runs` etc. are same-origin.
