"""Scores one pipeline run on the two things this project's thesis
actually cares about:

groundedness -- of the citations the writer made, how many survived the
verifier's recompute + semantic check. This is read straight off the
VerifiedReport the pipeline already produced; no golden answer needed.

coverage -- of the dataset's known reference facts (independently computed
by src/eval/reference.py), how many did the analyst surface as a finding.
This doesn't require the analyst to phrase things the way a human would;
it just checks whether the number shows up anywhere among its findings.

Neither metric requires pre-writing the questions the LLM should ask --
the analyst picks its own questions; what's checked is whether whatever
it picks holds up, and whether it finds what's actually there.
"""
from src.artifacts import AnalystArtifact, VerifiedReport
from src.eval.reference import ReferenceFact

_NUMERIC_TOLERANCE = 0.01


def _numeric_close(a, b, tolerance: float = _NUMERIC_TOLERANCE) -> bool:
    try:
        a_f, b_f = float(a), float(b)
    except (TypeError, ValueError):
        return False
    return abs(a_f - b_f) <= tolerance * max(abs(b_f), 1e-9)


def groundedness(report: VerifiedReport) -> dict:
    total = len(report.verdicts)
    passed = sum(1 for v in report.verdicts if v.passed)
    return {
        "citations_checked": total,
        "citations_passed": passed,
        "citations_removed": len(report.removed_claims),
        "pass_rate": passed / total if total else None,
    }


def coverage(artifact: AnalystArtifact, facts: list[ReferenceFact]) -> dict:
    detail = []
    for fact in facts:
        if isinstance(fact.value, str):
            found = any(isinstance(f.value, str) and f.value.strip().lower() == fact.value.strip().lower() for f in artifact.findings)
        else:
            found = any(_numeric_close(f.value, fact.value) for f in artifact.findings if isinstance(f.value, (int, float)))
        detail.append({"fact": fact.name, "description": fact.description, "found": found})

    covered = sum(1 for d in detail if d["found"])
    return {
        "facts_total": len(facts),
        "facts_covered": covered,
        "coverage_rate": covered / len(facts) if facts else None,
        "detail": detail,
    }
