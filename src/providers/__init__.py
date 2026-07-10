from src.config import SETTINGS
from src.providers.base import Provider
from src.providers.mock_provider import MockProvider


def get_provider(provider_name: str = None, mock_plan: list[dict] = None, mock_completions: list[str] = None) -> Provider:
    name = provider_name or SETTINGS.llm_provider

    if name == "mock":
        return MockProvider(plan=mock_plan, completions=mock_completions)

    if name == "anthropic":
        from src.providers.anthropic_provider import AnthropicProvider
        if not SETTINGS.anthropic_api_key:
            raise RuntimeError("ANTHROPIC_API_KEY is not set")
        return AnthropicProvider(api_key=SETTINGS.anthropic_api_key, model=SETTINGS.anthropic_model)

    if name == "openai":
        from src.providers.openai_provider import OpenAIProvider
        if not SETTINGS.openai_api_key:
            raise RuntimeError("OPENAI_API_KEY is not set")
        return OpenAIProvider(
            api_key=SETTINGS.openai_api_key,
            model=SETTINGS.openai_model,
            base_url=SETTINGS.openai_base_url,
            api_version=SETTINGS.openai_api_version,
        )

    raise ValueError(f"unknown LLM_PROVIDER: {name}")
