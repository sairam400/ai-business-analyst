import { reportHtmlUrl, reportJsonUrl, reportPdfUrl } from "../api";
import "./ReportSummary.css";

type DoneStatus = {
  status: "done";
  findings: number;
  failed_tasks: string[];
  citations_checked: number;
  citations_passed: number;
  removed_claims: number;
  pdf_ready: boolean;
};

export function ReportSummary({ runId, status }: { runId: string; status: DoneStatus }) {
  const { citations_checked, citations_passed } = status;
  const passedPct = citations_checked ? (citations_passed / citations_checked) * 100 : 0;
  const removedPct = citations_checked ? 100 - passedPct : 0;

  return (
    <div className="report-summary">
      <div className="stat-tiles">
        <div className="stat-tile">
          <span className="stat-value">{status.findings}</span>
          <span className="stat-label">findings</span>
        </div>
        <div className="stat-tile">
          <span className="stat-value">
            {citations_passed}/{citations_checked}
          </span>
          <span className="stat-label">citations verified</span>
        </div>
        <div className="stat-tile">
          <span className="stat-value">{status.removed_claims}</span>
          <span className="stat-label">claims removed</span>
        </div>
      </div>

      {citations_checked > 0 && (
        <div className="meter" role="img" aria-label={`${citations_passed} of ${citations_checked} citations verified`}>
          <div className="meter-fill meter-passed" style={{ width: `${passedPct}%` }} />
          {removedPct > 0 && <div className="meter-fill meter-removed" style={{ width: `${removedPct}%` }} />}
        </div>
      )}

      {status.failed_tasks.length > 0 && (
        <p className="note">{status.failed_tasks.length} analysis task(s) could not be completed.</p>
      )}

      <div className="report-actions">
        <a className="action-link" href={reportHtmlUrl(runId)} target="_blank" rel="noreferrer">
          View report
        </a>
        <a
          className={`action-link ${status.pdf_ready ? "" : "action-link-disabled"}`}
          href={status.pdf_ready ? reportPdfUrl(runId) : undefined}
          aria-disabled={!status.pdf_ready}
          title={status.pdf_ready ? undefined : "PDF rendering isn't available on this server (missing native libs)"}
        >
          Download PDF
        </a>
        <a className="action-link" href={reportJsonUrl(runId)} target="_blank" rel="noreferrer">
          Raw JSON
        </a>
      </div>
    </div>
  );
}
