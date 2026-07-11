import { useEffect, useState } from "react";
import { ApiError, createRun, getRun, type Provider, type RunStatus } from "./api";
import { UploadForm } from "./components/UploadForm";
import { RunProgress } from "./components/RunProgress";
import { ReportSummary } from "./components/ReportSummary";
import "./App.css";

const POLL_INTERVAL_MS = 1200;

function App() {
  const [runId, setRunId] = useState<string | null>(null);
  const [status, setStatus] = useState<RunStatus | null>(null);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    if (!runId || !status || status.status === "done" || status.status === "failed") return;
    const timer = setTimeout(async () => {
      try {
        const next = await getRun(runId);
        setStatus(next);
      } catch {
        // transient poll failure -- try again on the next tick rather than surfacing an error
      }
    }, POLL_INTERVAL_MS);
    return () => clearTimeout(timer);
  }, [runId, status]);

  const handleSubmit = async (files: File[], provider: Provider) => {
    setSubmitError(null);
    setSubmitting(true);
    try {
      const created = await createRun(files, provider);
      setRunId(created.run_id);
      setStatus({ status: "pending", row_counts: created.row_counts });
    } catch (err) {
      setSubmitError(err instanceof ApiError ? err.message : "could not start the run");
    } finally {
      setSubmitting(false);
    }
  };

  const reset = () => {
    setRunId(null);
    setStatus(null);
    setSubmitError(null);
  };

  return (
    <>
      <h1>AI Business Analyst</h1>
      <p className="subtitle">Upload a CSV dataset and get a verified, board-ready report.</p>

      {!runId && <UploadForm onSubmit={handleSubmit} disabled={submitting} />}
      {submitError && <p className="form-error" role="alert">{submitError}</p>}

      {runId && status && status.status !== "done" && status.status !== "failed" && (
        <RunProgress status={status} />
      )}

      {runId && status?.status === "failed" && (
        <div className="run-failed">
          <p>Run failed: {status.error}</p>
          <button type="button" onClick={reset}>
            Try again
          </button>
        </div>
      )}

      {runId && status?.status === "done" && (
        <>
          <ReportSummary runId={runId} status={status} />
          <button type="button" className="reset-button" onClick={reset}>
            Analyze another dataset
          </button>
        </>
      )}
    </>
  );
}

export default App;
