# Frontend

Upload a CSV dataset, poll the run, view the verified report. Talks to the
FastAPI backend in `src/api/`.

```
npm install
npm run dev     # proxies /runs and /health to http://localhost:8000 -- run the backend separately
```

The backend must be running (`python -m uvicorn src.api.main:app --reload`
from the repo root) for anything here to work; `mock` as the provider needs
no API key.

`npm run build` produces `frontend/dist`; nothing serves it in production
yet (see `KNOWN_ISSUES.md`).
