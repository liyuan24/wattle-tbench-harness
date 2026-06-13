from __future__ import annotations

from dataclasses import dataclass

PROVIDER_ALIASES = {
    "anthropic": "anthropic",
    "codex": "openai_codex",
    "deepseek": "deepseek",
    "kimi": "kimi",
    "minimax": "minimax",
    "openai": "openai_codex",
    "openai_codex": "openai_codex",
    "openai_completions": "openai_completions",
    "openai_responses": "openai_responses",
}

DEFAULT_MODELS = {
    "deepseek": "deepseek-v4-pro",
    "kimi": "kimi-k2.6",
    "minimax": "minimax-m2.7",
    "openai_codex": "gpt-5.5",
}


@dataclass(frozen=True)
class ParsedModel:
    raw: str
    provider: str
    model: str


def parse_provider_model(model_name: str | None, *, provider: str | None = None) -> ParsedModel:
    if model_name and "/" in model_name:
        provider_raw, model = model_name.split("/", 1)
        raw = model_name
    else:
        provider_raw = provider or "deepseek"
        parsed_provider = PROVIDER_ALIASES.get(provider_raw)
        if parsed_provider is None:
            choices = ", ".join(sorted(PROVIDER_ALIASES))
            raise ValueError(f"Unsupported Wattle provider '{provider_raw}'. Supported: {choices}")
        model = model_name or DEFAULT_MODELS.get(parsed_provider) or ""
        raw = f"{provider_raw}/{model}"

    parsed_provider = PROVIDER_ALIASES.get(provider_raw)
    if parsed_provider is None:
        choices = ", ".join(sorted(PROVIDER_ALIASES))
        raise ValueError(f"Unsupported Wattle provider '{provider_raw}'. Supported: {choices}")
    if not model:
        raise ValueError(f"Model name is empty in Harbor -m value '{raw}'")
    return ParsedModel(raw=raw, provider=parsed_provider, model=model)

