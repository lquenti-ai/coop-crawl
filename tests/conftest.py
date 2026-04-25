import os

# env.py asserts these at import; populate before any coopcrawl import.
os.environ.setdefault("COOPCRAWL_LLM_API_KEY", "test-key")
os.environ.setdefault("COOPCRAWL_TELEGRAM_BOT_TOKEN", "test-token")
