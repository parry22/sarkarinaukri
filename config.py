from __future__ import annotations
from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    # Supabase
    supabase_url: str = ""
    supabase_key: str = ""
    supabase_service_key: str = ""

    # WhatsApp provider: "meta" or "greenapi"
    whatsapp_provider: str = "greenapi"

    # Option A — Meta WhatsApp Cloud API
    whatsapp_phone_number_id: str = ""
    whatsapp_access_token: str = ""
    whatsapp_api_version: str = "v20.0"

    # Option B — Green API (QR-based, no Facebook Business account needed)
    # Sign up free at green-api.com, scan QR, get these two values
    green_api_instance_id: str = ""
    green_api_token: str = ""

    # Shared
    whatsapp_verify_token: str = "sarkarinaukri-verify"

    # Groq (open-source LLM via Groq - free tier)
    groq_api_key: str = ""
    groq_model: str = "llama-3.1-8b-instant"  # free, fast; upgrade to llama-3.3-70b for accuracy

    # App
    app_env: str = "development"
    app_port: int = 8000
    base_url: str = "http://localhost:8000"

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


@lru_cache
def get_settings() -> Settings:
    return Settings()
