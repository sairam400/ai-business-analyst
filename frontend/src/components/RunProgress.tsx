import type { RunStatus } from "../api";
import "./RunProgress.css";

const STAGES: { key: string; label: string }[] = [
  { key: "profiler", label: "Profiling data" },
  { key: "analyst", label: "Running analysis" },
  { key: "writer", label: "Writing report" },
  { key: "verifier", label: "Verifying claims" },
  { key: "render", label: "Rendering PDF" },
];

type StepState = "pending" | "active" | "complete";

function stepStates(status: RunStatus): StepState[] {
  if (status.status === "done") return STAGES.map(() => "complete");
  if (status.status === "pending") return STAGES.map(() => "pending");
  if (status.status === "running") {
    const activeIndex = STAGES.findIndex((s) => s.key === status.stage);
    return STAGES.map((_, i) => (i < activeIndex ? "complete" : i === activeIndex ? "active" : "pending"));
  }
  return STAGES.map(() => "pending");
}

export function RunProgress({ status }: { status: RunStatus }) {
  const states = stepStates(status);
  return (
    <ol className="run-progress" aria-label="Pipeline progress">
      {STAGES.map((stage, i) => (
        <li key={stage.key} className={`step step-${states[i]}`}>
          <span className="step-marker" aria-hidden="true">
            {states[i] === "complete" ? "✓" : i + 1}
          </span>
          <span className="step-label">{stage.label}</span>
        </li>
      ))}
    </ol>
  );
}
