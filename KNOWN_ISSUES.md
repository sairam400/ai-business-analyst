# Known issues

- **WeasyPrint requires native Pango/Cairo libraries.** PDF rendering is only
  verified inside the Docker image (Linux). Running `src/report` natively on
  Windows without WSL will fail to import weasyprint unless GTK3 runtime is
  installed separately.
- **`src/report/render.py`'s PDF path (`render_pdf`) is untested against real WeasyPrint on this
  machine.** Docker Desktop wasn't running when it was built, so `render_pdf`'s control flow is
  covered by unit tests against a faked `weasyprint` module (`tests/test_render.py`), and the
  graceful-failure path (`RenderError` when native libs are missing) is confirmed for real on
  native Windows -- but an actual PDF has not been produced and eyeballed yet. `render_html`
  (the Jinja2 templating, footnote linking, and XSS-escaping of LLM-authored text) has been
  exercised end to end against real data. Before treating this as done: `docker build -t aiba .`
  and run the CLI inside the container, or install a GTK3 runtime natively, and check the
  rendered `report.pdf` looks right.
- **`run_python` is process-isolated, not sandboxed.** It runs in a subprocess
  with a scratch directory, a stripped environment, and a monkey-patched
  socket module to block outbound network calls, but it is not a real
  security boundary (no seccomp/container-per-call). Acceptable for a local
  demo tool operating on data the user already trusts; would need real
  sandboxing (e.g. gVisor, a per-call container) before running untrusted
  code server-side for multiple tenants.
- **No live Anthropic API key was available while building the pipeline or
  the eval harness (`src/eval/`).** The profiler, analyst, writer, and
  verifier are built and tested against `MockProvider` (scripted,
  deterministic, no network) so every code path, retry loop, and the render
  gate are exercised, but no real Claude call has happened yet, and the
  harness's groundedness/coverage scores have only ever been measured
  against the mock scenario (a smoke test of the harness, not a real
  measurement -- coverage against mock is low by construction, since the
  scripted scenario only asks 2 of the 6 reference questions). Set
  `ANTHROPIC_API_KEY` in `.env` and run `python -m src.eval.run_eval
  --provider anthropic --runs 5` to get real numbers before treating this
  as production-verified end to end.
- **`src/api/` has no authentication, rate limiting, or run expiry.** Any
  caller can trigger LLM calls (real spend, with `provider=anthropic` or
  `openai`) and every run's status.json/artifacts/uploaded CSVs persist under
  `runs/` and `data/uploads/` indefinitely -- fine for a local demo behind a
  trusted network, not for a public deployment. `CORS_ORIGINS` defaults to
  `*` for the same reason (no auth/cookies in play, but tighten it before
  exposing this beyond local dev). Chart embedding in the API's
  `GET .../report.html` (via `render_html`'s `chart_url_base` and the new
  `GET .../charts/{chart_id}.png` endpoint) is plumbed but untested against
  a real chart, since the mock scenario never calls `make_chart` -- exercise
  this once a live provider run actually produces one.
- **`frontend/` has no production serving story yet.** `npm run dev` proxies
  `/runs` and `/health` to `http://localhost:8000` (see `vite.config.ts`), and
  that's the only integration path exercised so far -- verified with a real
  `uvicorn` process and Playwright (upload the sample CSVs, poll to done,
  confirm no console errors), not just mocked. `npm run build` produces
  `frontend/dist`, but neither the `Dockerfile` nor `docker-compose.yml`
  build or serve it (both are backend-only); in production the built assets
  would need a static host or a reverse proxy in front of both services,
  since the app assumes `/runs` etc. are same-origin.
