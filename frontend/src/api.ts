// Relative paths so this works both in dev (proxied by vite.config.ts) and
// in production (expected to sit behind the same origin/reverse proxy as
// the API) without a build-time base URL.
const BASE = "";

export type Provider = "mock" | "anthropic" | "openai";

export type RunStatus =
  | { status: "pending"; row_counts: Record<string, number> }
  | { status: "running"; stage: string }
  | {
      status: "done";
      findings: number;
      failed_tasks: string[];
      citations_checked: number;
      citations_passed: number;
      removed_claims: number;
      pdf_ready: boolean;
    }
  | { status: "failed"; error: string };

export type CreateRunResponse = {
  run_id: string;
  status: "pending";
  row_counts: Record<string, number>;
};

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

async function asJson<T>(resp: Response): Promise<T> {
  if (!resp.ok) {
    const body = await resp.json().catch(() => ({ detail: resp.statusText }));
    throw new ApiError(resp.status, body.detail ?? resp.statusText);
  }
  return resp.json() as Promise<T>;
}

export async function createRun(files: File[], provider: Provider): Promise<CreateRunResponse> {
  const form = new FormData();
  for (const file of files) form.append("files", file);
  form.append("provider", provider);
  const resp = await fetch(`${BASE}/runs`, { method: "POST", body: form });
  return asJson(resp);
}

export async function getRun(runId: string): Promise<RunStatus & { run_id: string }> {
  const resp = await fetch(`${BASE}/runs/${runId}`);
  return asJson(resp);
}

export function reportHtmlUrl(runId: string): string {
  return `${BASE}/runs/${runId}/report.html`;
}

export function reportPdfUrl(runId: string): string {
  return `${BASE}/runs/${runId}/report.pdf`;
}

export function reportJsonUrl(runId: string): string {
  return `${BASE}/runs/${runId}/report`;
}
