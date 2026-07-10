"""Flat, hand-rolled settings. No pydantic here on purpose -- pydantic is
reserved for artifacts that cross an agent-stage boundary, not config."""
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _load_dotenv():
    env_path = ROOT / ".env"
    if not env_path.exists():
        return
    for line in env_path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        if key and key not in os.environ:
            os.environ[key] = value.strip()


_load_dotenv()


def _get_env(key: str, default: str = "") -> str:
    return os.environ.get(key, default)


class Settings:
    llm_provider = _get_env("LLM_PROVIDER", "anthropic")

    anthropic_api_key = _get_env("ANTHROPIC_API_KEY")
    anthropic_model = _get_env("ANTHROPIC_MODEL", "claude-sonnet-4-5")

    openai_api_key = _get_env("OPENAI_API_KEY")
    openai_model = _get_env("OPENAI_MODEL", "gpt-4o")
    openai_base_url = _get_env("OPENAI_BASE_URL")
    openai_api_version = _get_env("OPENAI_API_VERSION")

    db_path = ROOT / "data" / "workspace.db"
    sample_data_dir = ROOT / "data" / "sample"
    upload_dir = ROOT / "data" / "uploads"
    runs_dir = ROOT / "runs"
    sandbox_root = ROOT / "sandbox"
    report_templates_dir = ROOT / "src" / "report" / "templates"
    docs_dir = ROOT / "docs"

    run_python_timeout_seconds = int(_get_env("RUN_PYTHON_TIMEOUT_SECONDS", "10"))
    max_steps = int(_get_env("MAX_STEPS", "10"))
    max_consecutive_errors = int(_get_env("MAX_CONSECUTIVE_ERRORS", "3"))

    # relative tolerance used by the verifier when comparing a cited number
    # against the value its footnoted query actually produces
    verify_tolerance = float(_get_env("VERIFY_TOLERANCE", "0.01"))

    app_port = int(_get_env("APP_PORT", "8000"))

    max_upload_rows_per_table = int(_get_env("MAX_UPLOAD_ROWS_PER_TABLE", "200000"))


SETTINGS = Settings()

for _dir in (
    SETTINGS.db_path.parent,
    SETTINGS.upload_dir,
    SETTINGS.runs_dir,
    SETTINGS.sandbox_root,
):
    _dir.mkdir(parents=True, exist_ok=True)
