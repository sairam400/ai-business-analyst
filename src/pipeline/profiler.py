"""Inspects whatever tables got loaded and decides which analyses apply.

Schema/quality stats are computed deterministically via run_sql -- no LLM
judgment needed to count nulls. The one LLM call is reserved for the part
that actually requires judgment: given this specific schema, what analyses
make sense? That's what keeps this from hardcoding e-commerce assumptions
onto an arbitrary CSV.
"""
import re

from src.artifacts import ColumnProfile, DatasetProfile, TableProfile
from src.pipeline.llm_json import complete_json
from src.providers.base import Provider

_DATE_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}")
_ID_PATTERN = re.compile(r"(^id$|_id$)", re.IGNORECASE)
_HIGH_NULL_THRESHOLD = 0.05

SYSTEM_PROMPT = (
    "You are the profiling stage of a business analytics pipeline. Given a schema "
    "summary of an uploaded dataset (table names, columns, types, null rates, sample "
    "values, and detected relationships), decide what analyses actually make sense "
    "for THIS data. Do not assume it's e-commerce data unless the columns say so. "
    "Be concrete: 'monthly revenue trend' not 'analyze trends'. Only suggest an "
    "analysis if the columns needed for it actually exist.\n\n"
    "Respond with JSON only: "
    '{"suggested_analyses": ["...", ...], "data_quality_notes": ["...", ...]}\n'
    "suggested_analyses: 4-8 specific, computable analyses. "
    "data_quality_notes: anything notable beyond null/negative counts already given to you "
    "(e.g. a column that looks miscoded, an unexpected value distribution)."
)


def _infer_sql_type(sample_values: list) -> str:
    for v in sample_values:
        if v is None:
            continue
        if isinstance(v, bool):
            continue
        if isinstance(v, int):
            return "integer"
        if isinstance(v, float):
            return "float"
        if isinstance(v, str) and _DATE_PATTERN.match(v):
            return "date"
        return "text"
    return "text"


def _profile_table(table_name: str, tools: dict) -> TableProfile:
    preview = tools["run_sql"](query=f'SELECT * FROM "{table_name}" LIMIT 5')
    columns = preview["columns"]
    row_count = tools["run_sql"](query=f'SELECT COUNT(*) FROM "{table_name}"')["rows"][0][0]

    column_profiles = []
    for i, col in enumerate(columns):
        sample_values = [row[i] for row in preview["rows"]]
        stats = tools["run_sql"](
            query=(
                f'SELECT COUNT(*) - COUNT("{col}") AS nulls, '
                f'COUNT(DISTINCT "{col}") AS distinct_count '
                f'FROM "{table_name}"'
            )
        )
        nulls, distinct_count = stats["rows"][0]
        column_profiles.append(ColumnProfile(
            name=col,
            sql_type=_infer_sql_type(sample_values),
            null_count=nulls,
            null_pct=round(nulls / row_count, 4) if row_count else 0.0,
            distinct_count=distinct_count,
            sample_values=[v for v in sample_values if v is not None][:5],
            is_id_like=bool(_ID_PATTERN.search(col)),
        ))

    return TableProfile(name=table_name, row_count=row_count, columns=column_profiles)


def _pk_owner_candidates(col_name: str) -> set[str]:
    prefix = col_name[:-3] if col_name.endswith("_id") else col_name
    return {prefix, f"{prefix}s", f"{prefix}es"}


def _detect_relationships(tables: list[TableProfile]) -> list[str]:
    seen = set()
    relationships = []
    for table in tables:
        for col in table.columns:
            if not col.is_id_like:
                continue
            for other in tables:
                if other.name == table.name or not any(c.name == col.name for c in other.columns):
                    continue
                key = (frozenset({table.name, other.name}), col.name)
                if key in seen:
                    continue
                seen.add(key)

                candidates = _pk_owner_candidates(col.name)
                if other.name in candidates and table.name not in candidates:
                    relationships.append(f"{table.name}.{col.name} -> {other.name}.{col.name}")
                elif table.name in candidates and other.name not in candidates:
                    relationships.append(f"{other.name}.{col.name} -> {table.name}.{col.name}")
                elif table.row_count >= other.row_count:
                    relationships.append(f"{table.name}.{col.name} -> {other.name}.{col.name}")
                else:
                    relationships.append(f"{other.name}.{col.name} -> {table.name}.{col.name}")
    return sorted(relationships)


def _deterministic_quality_notes(tables: list[TableProfile], tools: dict) -> list[str]:
    notes = []
    for table in tables:
        for col in table.columns:
            if col.null_pct > _HIGH_NULL_THRESHOLD:
                notes.append(f"{table.name}.{col.name} is missing in {col.null_pct:.1%} of rows")
            if col.sql_type in ("integer", "float") and not col.is_id_like:
                result = tools["run_sql"](query=f'SELECT COUNT(*) FROM "{table.name}" WHERE "{col.name}" < 0')
                negative_count = result["rows"][0][0]
                if negative_count:
                    notes.append(f"{table.name}.{col.name} has {negative_count} negative value(s)")
    return notes


def profile_dataset(tools: dict, provider: Provider) -> DatasetProfile:
    table_names = [row[0] for row in tools["run_sql"](query="SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")["rows"]]
    tables = [_profile_table(name, tools) for name in table_names]
    relationships = _detect_relationships(tables)
    quality_notes = _deterministic_quality_notes(tables, tools)

    summary = {
        "tables": [
            {
                "name": t.name,
                "row_count": t.row_count,
                "columns": [
                    {"name": c.name, "type": c.sql_type, "null_pct": c.null_pct, "distinct_count": c.distinct_count, "sample_values": c.sample_values}
                    for c in t.columns
                ],
            }
            for t in tables
        ],
        "detected_relationships": relationships,
        "known_data_quality_notes": quality_notes,
    }

    response = complete_json(
        provider,
        SYSTEM_PROMPT,
        f"Schema summary:\n{summary}",
    )

    return DatasetProfile(
        tables=tables,
        detected_relationships=relationships,
        data_quality_notes=quality_notes + list(response.get("data_quality_notes", [])),
        suggested_analyses=list(response.get("suggested_analyses", [])),
    )
