"""Provider picker.

`make_provider(d)` returns a fresh `LLMProvider` instance configured per
the given DisplaySettings. The MainWindow constructs one of these on each
"Send" so changing the provider at runtime works.
"""
from .base import LLMProvider
from .anthropic_provider import AnthropicProvider, DEFAULT_MODEL as ANTHROPIC_MODEL
from .ollama_provider import OllamaProvider, DEFAULT_MODEL as OLLAMA_MODEL
from .openai_provider import OpenAIProvider, DEFAULT_MODEL as OPENAI_MODEL


PROVIDERS = ("anthropic", "openai", "ollama")


def make_provider(d) -> LLMProvider:
    name = (getattr(d, "llm_provider", "anthropic") or "anthropic").lower()
    if name == "ollama":
        return OllamaProvider(base_url=getattr(d, "llm_ollama_url", "http://localhost:11434"))
    if name == "openai":
        return OpenAIProvider(base_url=getattr(d, "llm_openai_base_url", "https://api.openai.com/v1"))
    return AnthropicProvider()


def model_for(d) -> str:
    name = (getattr(d, "llm_provider", "anthropic") or "anthropic").lower()
    if name == "ollama":
        return getattr(d, "llm_model_ollama", OLLAMA_MODEL)
    if name == "openai":
        return getattr(d, "llm_model_openai", OPENAI_MODEL)
    return getattr(d, "llm_model_anthropic", ANTHROPIC_MODEL)


def is_available(d) -> tuple[bool, str]:
    return make_provider(d).is_available()
