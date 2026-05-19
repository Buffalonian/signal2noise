from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict

LlmProviderSetting = Literal["auto", "openai", "ollama", "demo"]
PennyScreenerProviderSetting = Literal["auto", "yahoo", "alpha_vantage"]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env.local",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    openai_api_key: str = ""
    openai_model: str = "gpt-4.1-mini"
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "qwen3:8b"
    llm_provider: LlmProviderSetting = "auto"
    sec_user_agent: str = "SignalPathIntel/0.1 contact@example.com"
    sec_base_url: str = "https://data.sec.gov"
    claim_support_threshold: float = 0.75
    demo_mode: bool = False
    sessions_enabled: bool = True
    sessions_dir: str = "data/sessions"
    sec_cache_enabled: bool = True
    sec_cache_dir: str = "data/sec_cache"
    sec_cache_ttl_hours: int = 24
    company_tickers_cache_path: str = "data/company_tickers.json"
    company_tickers_ttl_hours: int = 168
    penny_screener_cache_ttl_minutes: int = 5
    penny_screener_provider: PennyScreenerProviderSetting = "auto"
    alpha_vantage_api_key: str = ""


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
