"""Chat model factory. Uses OpenRouter through its OpenAI-compatible API."""

from langchain_openai import ChatOpenAI

from app.config.settings import get_settings


def get_llm(temperature: float = 0.0) -> ChatOpenAI:
    settings = get_settings()
    if not settings.openrouter_api_key:
        raise RuntimeError("OPENROUTER_API_KEY is not set. Copy .env.example to .env and fill it in.")
    return ChatOpenAI(
        model=settings.openrouter_model,
        api_key=settings.openrouter_api_key,
        base_url=settings.openrouter_base_url,
        temperature=temperature,
        # Fail fast: triage falls back to rules, so long waits only delay the customer.
        max_retries=1,
        timeout=15,
    )
