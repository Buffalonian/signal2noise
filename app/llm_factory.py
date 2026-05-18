from __future__ import annotations

from typing import Literal

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_ollama import ChatOllama
from langchain_openai import ChatOpenAI

from app.config import settings

LlmProvider = Literal["openai", "ollama", "demo"]


def has_openai_key() -> bool:
    key = settings.openai_api_key.strip().lower()
    return key not in ("", "your_key_here", "sk-your-key-here", "changeme")


def resolved_llm_provider() -> LlmProvider:
    if settings.demo_mode or settings.llm_provider == "demo":
        return "demo"
    if settings.llm_provider == "openai":
        return "openai" if has_openai_key() else "ollama"
    if settings.llm_provider == "ollama":
        return "ollama"
    # auto: prefer OpenAI when keyed, otherwise local Ollama
    return "openai" if has_openai_key() else "ollama"


def use_demo_llm() -> bool:
    return resolved_llm_provider() == "demo"


def create_chat_model() -> BaseChatModel:
    provider = resolved_llm_provider()
    if provider == "openai":
        return ChatOpenAI(
            api_key=settings.openai_api_key,
            model=settings.openai_model,
            temperature=0,
        )
    if provider == "ollama":
        return ChatOllama(
            base_url=settings.ollama_base_url,
            model=settings.ollama_model,
            temperature=0,
        )
    raise RuntimeError("Cannot create chat model in demo mode.")
