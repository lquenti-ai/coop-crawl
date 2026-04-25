from coopcrawl.entry import Entry, LLMState

DEFAULT_SYSTEM_PROMPT = """
You are a change-classification assistant. You will be given a unified text
diff of a specific subsection of a web page. Decide whether a human watcher
would care about this change.

Ignore: timestamps, view counters, cookie banners, rotating ads, CSRF tokens,
layout-only reordering, whitespace, and any text whose only change is
numerical or purely cosmetic.

Notify (NORMAL_PING) on: new items added to a list the watcher cares about,
removed items, meaningful edits to titles, statuses, or descriptions.

Notify (MENTION_PING) on: changes that are time-sensitive or that the user's
per-entry instructions specifically flag (e.g. a deadline, an opening, a
new availability).

Output JSON matching this schema EXACTLY and nothing else:
  { "reason": "<one short sentence>", "level": "<NO_PING|NORMAL_PING|MENTION_PING>" }

Produce `reason` first and `level` last.
""".strip()

ALL_ENTRIES: list[Entry] = [
    Entry(
        name="Example prof — theses",
        url="https://example.edu/~prof/theses",
        xpath="/html/body/main/section[2]",
        llm_state=LLMState(system_prompt=DEFAULT_SYSTEM_PROMPT),
    ),
]

# --- LLM transport ---
LLM_BASE_URL = "http://localhost:8000/v1"
LLM_MODEL = "Qwen/Qwen2.5-72B-Instruct"
LLM_TEMPERATURE = 0.0
LLM_DIFF_MAX_BYTES = 8 * 1024

# --- Notification ---
TELEGRAM_GROUP_CHAT_ID = -1001234567890
TELEGRAM_MENTION_USER_ID = 12345678
NOTIFICATION_BATCH_WINDOW_SECS = 30

# --- Browser ---
ADBLOCK_XPI_PATH: str | None = "./vendor/ublock_origin.xpi"
ADBLOCK_XPI_URL = "https://addons.mozilla.org/firefox/downloads/latest/ublock-origin/latest.xpi"
FIREFOX_BINARY_PATH: str | None = None
