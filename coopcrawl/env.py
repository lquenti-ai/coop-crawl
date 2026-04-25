from __future__ import annotations

import os

_LLM_API_KEY = os.environ.get("COOPCRAWL_LLM_API_KEY", "")
_TELEGRAM_BOT_TOKEN = os.environ.get("COOPCRAWL_TELEGRAM_BOT_TOKEN", "")

assert _LLM_API_KEY, "COOPCRAWL_LLM_API_KEY must be set"
assert _TELEGRAM_BOT_TOKEN, "COOPCRAWL_TELEGRAM_BOT_TOKEN must be set"

LLM_API_KEY: str = _LLM_API_KEY
TELEGRAM_BOT_TOKEN: str = _TELEGRAM_BOT_TOKEN
