"""Turns findings into executive prose. The writer cannot invent numbers:
it only ever gets to reference finding ids, and everything it writes is
checked against that constraint before being accepted. This is a
structural check (every metric-shaped number in the text carries a
footnote to a real finding id) -- whether the cited *value* is actually
correct is the verifier's job in the next stage, deliberately kept
separate so this check can't be gamed by citing a real id next to a
wrong number.
"""
import re

from src.artifacts import AnalystArtifact, Draft, ReportSection
from src.pipeline.llm_json import complete_json
from src.providers.base import Provider

SYSTEM_PROMPT = (
    "You are the writer stage of a business analytics pipeline. You turn a list of "
    "findings into board-ready executive prose for a PDF report.\n\n"
    "Rules, strictly enforced by an automated check after you respond:\n"
    "1. You may ONLY state a number, percentage, or dollar figure that comes directly "
    "from one of the findings you were given. Never estimate, round differently, or "
    "invent a number that isn't one of those exact values.\n"
    "2. Every sentence containing such a number must end with a footnote marker "
    "referencing the finding it came from, like [F3]. Use the exact finding id given.\n"
    "3. Do not cite a finding id that wasn't given to you.\n"
    "4. Findings you don't use in the narrative are fine to leave out -- do not pad "
    "the report with claims just to use every id.\n\n"
    "Respond with JSON only: "
    '{"executive_summary": "<2-4 sentence overview, footnoted>", '
    '"sections": [{"heading": "<section title>", "body": "<prose, footnoted>"}, ...]}\n'
    "Write 3-6 sections. Prose only in body -- no markdown headers inside it."
)

_FOOTNOTE_PATTERN = re.compile(r"\[F(\d+)\]")
_METRIC_PATTERN = re.compile(r"\$[\d,]+(?:\.\d+)?|\b\d{1,3}(?:,\d{3})+(?:\.\d+)?\b|\b\d+(?:\.\d+)?%")
_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+")


class WriterError(Exception):
    pass


def _footnote_ids_in(text: str) -> set[str]:
    return {f"F{n}" for n in _FOOTNOTE_PATTERN.findall(text)}


def _unfootnoted_metric_sentences(text: str) -> list[str]:
    violations = []
    for sentence in _SENTENCE_SPLIT.split(text):
        if _METRIC_PATTERN.search(sentence) and not _FOOTNOTE_PATTERN.search(sentence):
            violations.append(sentence.strip())
    return violations


def _validate_draft(data: dict, valid_ids: set[str]) -> list[str]:
    issues = []
    texts = [data.get("executive_summary", "")] + [s.get("body", "") for s in data.get("sections", [])]
    for text in texts:
        unknown = _footnote_ids_in(text) - valid_ids
        if unknown:
            issues.append(f"cites unknown finding id(s) not in the provided findings: {sorted(unknown)}")
        for sentence in _unfootnoted_metric_sentences(text):
            issues.append(f'sentence has a number with no footnote marker: "{sentence}"')
    return issues


def run_writer(artifact: AnalystArtifact, provider: Provider, max_attempts: int = 2) -> Draft:
    valid_ids = {f.id for f in artifact.findings}
    findings_summary = [
        {"id": f.id, "question": f.question, "value": f.value, "unit": f.unit} for f in artifact.findings
    ]
    base_prompt = (
        f"Findings you may cite (cite ONLY these ids, never state a number that isn't "
        f"one of these exact values):\n{findings_summary}"
    )

    feedback = ""
    for _ in range(max_attempts):
        prompt = base_prompt + (f"\n\nYour previous draft had issues -- fix them:\n{feedback}" if feedback else "")
        data = complete_json(provider, SYSTEM_PROMPT, prompt)
        issues = _validate_draft(data, valid_ids)
        if not issues:
            return Draft(
                executive_summary=data["executive_summary"],
                sections=[ReportSection(**s) for s in data["sections"]],
            )
        feedback = "\n".join(issues)

    raise WriterError(f"writer could not produce a footnote-clean draft after {max_attempts} attempts: {feedback}")
