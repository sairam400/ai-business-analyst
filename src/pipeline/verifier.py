"""Recomputes every cited finding against the source data and checks the
writer's prose actually describes what it claims. Two independent checks
per citation -- a mechanical recompute (does the query still produce this
number?) and a semantic check (does the sentence describe what the number
actually measures?) -- deliberately kept separate so a citation can't pass
by being numerically right but semantically misleading, or vice versa.
Any citation that fails either check gets its sentence stripped from the
final report rather than failing the whole run.
"""
import re

from src.artifacts import (
    AnalystArtifact,
    Draft,
    Finding,
    RemovedClaim,
    ReportSection,
    VerifiedReport,
    VerifierVerdict,
)
from src.config import SETTINGS
from src.pipeline.llm_json import complete_json
from src.providers.base import Provider
from src.tools import ToolError

SYSTEM_PROMPT = (
    "You are the verifier stage of a business analytics pipeline. You will be given "
    "a list of citations: a finding (its question, value, unit) and the sentence(s) "
    "that cite it in a report. For each, judge whether the sentence faithfully "
    "describes what the finding measures -- flag it if it mislabels the metric, "
    "overstates certainty, or implies something the finding doesn't support. Do NOT "
    "flag it for the number itself; number accuracy is checked separately.\n\n"
    "Respond with JSON only: "
    '{"judgments": [{"finding_id": "F1", "faithful": true, "reason": "<short reason, esp. if false>"}, ...]}'
)

_FOOTNOTE_PATTERN = re.compile(r"\[F(\d+)\]")
_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+")


class VerifierError(Exception):
    pass


def _sentences(text: str) -> list[str]:
    return [s for s in _SENTENCE_SPLIT.split(text) if s.strip()]


def _cited_ids(text: str) -> set[str]:
    return {f"F{n}" for n in _FOOTNOTE_PATTERN.findall(text)}


def _flatten(value):
    if isinstance(value, dict):
        for v in value.values():
            yield from _flatten(v)
    elif isinstance(value, (list, tuple)):
        for v in value:
            yield from _flatten(v)
    else:
        yield value


def _values_match(claimed, candidate, tolerance: float) -> bool:
    try:
        claimed_f, candidate_f = float(claimed), float(candidate)
    except (TypeError, ValueError):
        return str(claimed).strip().lower() == str(candidate).strip().lower()
    return abs(claimed_f - candidate_f) <= tolerance * max(abs(claimed_f), 1e-9)


def _recompute(finding: Finding, tools: dict) -> list:
    if finding.method == "sql":
        result = tools["run_sql"](finding.query)
        return list(_flatten(result["rows"]))
    result = tools["run_python"](finding.query)
    return list(_flatten(result["result"]))


def _mechanical_check(finding: Finding, tools: dict) -> VerifierVerdict:
    try:
        candidates = _recompute(finding, tools)
    except ToolError as exc:
        return VerifierVerdict(
            finding_id=finding.id, claimed_value=finding.value, recomputed_value=None,
            passed=False, reason=f"could not recompute: {exc}",
        )
    for candidate in candidates:
        if _values_match(finding.value, candidate, SETTINGS.verify_tolerance):
            return VerifierVerdict(
                finding_id=finding.id, claimed_value=finding.value, recomputed_value=candidate, passed=True,
            )
    return VerifierVerdict(
        finding_id=finding.id, claimed_value=finding.value,
        recomputed_value=candidates[0] if candidates else None, passed=False,
        reason=f"query no longer produces the claimed value {finding.value!r} (got {candidates})",
    )


def _semantic_check(fids: list[str], findings_by_id: dict, all_text: str, provider: Provider) -> dict:
    if not fids:
        return {}
    citations = [
        {
            "finding_id": fid,
            "question": findings_by_id[fid].question,
            "value": findings_by_id[fid].value,
            "unit": findings_by_id[fid].unit,
            "sentences": [s.strip() for s in _sentences(all_text) if fid in _cited_ids(s)],
        }
        for fid in fids
    ]
    data = complete_json(provider, SYSTEM_PROMPT, f"Citations to check:\n{citations}")
    judgments = {j["finding_id"]: j for j in data.get("judgments", [])}
    return {
        fid: judgments[fid] if fid in judgments else {"faithful": True, "reason": ""}
        for fid in fids
    }


def _redact(text: str, failed_ids: set) -> str:
    kept = [s for s in _sentences(text) if not (_cited_ids(s) & failed_ids)]
    return " ".join(kept)


def run_verifier(draft: Draft, artifact: AnalystArtifact, tools: dict, provider: Provider) -> VerifiedReport:
    findings_by_id = {f.id: f for f in artifact.findings}
    all_text = "\n".join([draft.executive_summary] + [s.body for s in draft.sections])
    cited_ids = sorted(_cited_ids(all_text), key=lambda x: int(x[1:]))

    unknown = [fid for fid in cited_ids if fid not in findings_by_id]
    if unknown:
        raise VerifierError(f"draft cites finding id(s) not present in the artifact: {unknown}")

    verdicts = {}
    mechanically_passed = []
    for fid in cited_ids:
        verdict = _mechanical_check(findings_by_id[fid], tools)
        verdicts[fid] = verdict
        if verdict.passed:
            mechanically_passed.append(fid)

    judgments = _semantic_check(mechanically_passed, findings_by_id, all_text, provider)
    for fid, judgment in judgments.items():
        if not judgment.get("faithful", False):
            verdicts[fid] = verdicts[fid].model_copy(update={
                "passed": False,
                "reason": judgment.get("reason") or "sentence does not faithfully describe the finding",
            })

    failed_ids = {fid for fid, v in verdicts.items() if not v.passed}
    removed_claims = [RemovedClaim(finding_id=fid, reason=verdicts[fid].reason) for fid in cited_ids if fid in failed_ids]

    executive_summary = _redact(draft.executive_summary, failed_ids)
    sections = []
    for s in draft.sections:
        body = _redact(s.body, failed_ids)
        if body.strip():
            sections.append(ReportSection(heading=s.heading, body=body))

    return VerifiedReport(
        executive_summary=executive_summary,
        sections=sections,
        findings=artifact.findings,
        verdicts=list(verdicts.values()),
        removed_claims=removed_claims,
    )
