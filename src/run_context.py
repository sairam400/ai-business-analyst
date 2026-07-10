"""One RunContext per report generation. Everything the tools touch --
the loaded dataset, the charts they produce, the sandbox they execute
in -- is scoped to a run directory so a run is fully inspectable
afterward and runs never collide with each other."""
import uuid
from dataclasses import dataclass
from pathlib import Path

from src.config import SETTINGS


@dataclass
class RunContext:
    run_id: str
    db_path: Path
    run_dir: Path
    charts_dir: Path
    sandbox_dir: Path


def create_run(db_path: Path = None) -> RunContext:
    run_id = uuid.uuid4().hex[:12]
    run_dir = SETTINGS.runs_dir / run_id
    charts_dir = run_dir / "charts"
    sandbox_dir = SETTINGS.sandbox_root / run_id
    charts_dir.mkdir(parents=True, exist_ok=True)
    sandbox_dir.mkdir(parents=True, exist_ok=True)
    return RunContext(
        run_id=run_id,
        db_path=db_path or SETTINGS.db_path,
        run_dir=run_dir,
        charts_dir=charts_dir,
        sandbox_dir=sandbox_dir,
    )
