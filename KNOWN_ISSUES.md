# Known issues

- **WeasyPrint requires native Pango/Cairo libraries.** PDF rendering is only
  verified inside the Docker image (Linux). Running `src/report` natively on
  Windows without WSL will fail to import weasyprint unless GTK3 runtime is
  installed separately.
- **`run_python` is process-isolated, not sandboxed.** It runs in a subprocess
  with a scratch directory, a stripped environment, and a monkey-patched
  socket module to block outbound network calls, but it is not a real
  security boundary (no seccomp/container-per-call). Acceptable for a local
  demo tool operating on data the user already trusts; would need real
  sandboxing (e.g. gVisor, a per-call container) before running untrusted
  code server-side for multiple tenants.
