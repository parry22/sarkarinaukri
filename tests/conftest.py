"""
conftest.py - Pre-mock external dependencies so tests run without
Supabase, WhatsApp API, Anthropic, httpx, etc.

This file is loaded by pytest before any test module imports happen.
"""

import sys
from types import ModuleType
from unittest.mock import MagicMock

# ---------------------------------------------------------------------------
# Create fake modules for all heavy / external dependencies that are imported
# transitively by the code under test.  This prevents ImportError when the
# real packages are not installed in the test environment.
# ---------------------------------------------------------------------------

_FAKE_MODULES = [
    "supabase",
    "httpx",
    "anthropic",
    "pydantic_settings",
]

for mod_name in _FAKE_MODULES:
    if mod_name not in sys.modules:
        fake = ModuleType(mod_name)
        # Give the fake module some commonly accessed names
        fake.__dict__.setdefault("__all__", [])
        sys.modules[mod_name] = fake

# supabase needs create_client and Client
sys.modules["supabase"].create_client = MagicMock()
sys.modules["supabase"].Client = MagicMock

# pydantic_settings needs BaseSettings
from pydantic import BaseModel  # pydantic is installed

class _FakeBaseSettings(BaseModel):
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"

sys.modules["pydantic_settings"].BaseSettings = _FakeBaseSettings

# httpx needs AsyncClient
sys.modules["httpx"].AsyncClient = MagicMock

# ---------------------------------------------------------------------------
# Now pre-load config so it doesn't fail on missing env vars.
# We replace get_settings with one that returns a mock.
# ---------------------------------------------------------------------------

# Ensure database.connection returns a mock client
import database.connection as _db_conn
_db_conn.get_supabase = MagicMock()

# Ensure bot.whatsapp_client.send_text_message is an async mock
import bot.whatsapp_client as _wa
from unittest.mock import AsyncMock
_wa.send_text_message = AsyncMock()
