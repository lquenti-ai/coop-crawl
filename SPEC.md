# CoopCrawl — Specification

## 1. Purpose

A single-user local daemon that polls a fixed set of URLs on a schedule, diffs the rendered content of a configured subtree against the previous version, asks an LLM whether the change is interesting, and sends batched Telegram notifications. Fills the "this site should have an RSS feed but doesn't" gap.

## 2. Non-Goals

- Bot-detection / anti-scraping evasion. Assume targets are cooperative.
- Crawling or link discovery. Only the exact URLs listed in config are fetched.
- Persistence. State lives in memory; on restart the first poll of every entry re-baselines silently and fires no notification.
- Hot reload. Config changes require a restart.
- Multi-user / multi-tenant deployment. Runs as your own user, on your own machine.

## 3. Tech Stack

| Area | Choice |
|---|---|
| Language | Python ≥ 3.12 |
| Build / env | `uv` + `pyproject.toml` |
| Lint / format | `ruff` |
| Type check | Both `mypy --strict` **and** `ty` — CI fails on any diagnostic from either |
| Test | `pytest` |
| Browser | Selenium + Firefox (headless), with uBlock Origin loaded as a temporary add-on |
| LLM | Any OpenAI-compatible endpoint (vLLM / GLM / Qwen / …) via the `openai` async client; model name configurable; stateless calls only |
| Telegram | `python-telegram-bot` (async) |

## 4. Project Layout

```
coopcrawl/
├── pyproject.toml
├── config.py                # user-editable, imported at startup
├── coopcrawl/
│   ├── __init__.py
│   ├── __main__.py          # `python -m coopcrawl`
│   ├── env.py               # reads + asserts env vars; exports immutable constants
│   ├── entry.py             # Entry / LLMState / NotificationLevel
│   ├── fetch.py             # Selenium wrapper, xpath extraction, adblock loading
│   ├── diff.py              # unified-diff helper + truncation
│   ├── llm.py               # evaluate(system_prompt, diff) -> (reason, level)
│   ├── notify.py            # Telegram client + batching queue
│   ├── errors.py            # HTTP-status classification + Selenium-timeout mapping
│   └── runtime.py           # async main, per-entry task, shared resources
└── tests/
```

`config.py` lives at the repo root (not inside the package) to make it obvious it's user data. It's loaded via `importlib.util.spec_from_file_location` from `./config.py` by default; overridable with `--config PATH`.

## 5. Configuration

### 5.1 `config.py` (plain Python literal)

```python
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
        # poll_interval_secs=5 * 60,   # default
        # timeout_secs=20,             # default
    ),
]

# --- LLM transport ---
LLM_BASE_URL = "http://localhost:8000/v1"
LLM_MODEL = "Qwen/Qwen2.5-72B-Instruct"
LLM_TEMPERATURE = 0.0

# --- Notification ---
TELEGRAM_GROUP_CHAT_ID = -1001234567890        # group to post into
TELEGRAM_MENTION_USER_ID = 12345678            # @-mentioned on MENTION_PING
NOTIFICATION_BATCH_WINDOW_SECS = 30            # see §12

# --- Browser ---
ADBLOCK_XPI_PATH: str | None = "./vendor/ublock_origin.xpi"   # None disables
FIREFOX_BINARY_PATH: str | None = None          # None = system default
```

### 5.2 Environment variables

Read once in `env.py` at startup, `assert`-non-empty, then re-exported as typed module constants. No other module calls `os.getenv`.

| Variable | Purpose |
|---|---|
| `COOPCRAWL_LLM_API_KEY` | Bearer token for the OpenAI-compatible LLM endpoint |
| `COOPCRAWL_TELEGRAM_BOT_TOKEN` | Bot API token |

No `.env` loader is bundled; export via shell or the tool of your choice.

## 6. Data Model

```python
class NotificationLevel(enum.Enum):
    NO_PING = "NO_PING"
    NORMAL_PING = "NORMAL_PING"
    MENTION_PING = "MENTION_PING"

@dataclass(frozen=True, slots=True)
class LLMState:
    system_prompt: str

@dataclass(frozen=True, slots=True)
class Entry:
    url: str
    llm_state: LLMState
    xpath: str = "/"                      # default = whole document, discouraged
    timeout_secs: int = 20
    poll_interval_secs: int = 5 * 60
    name: str | None = None               # human label for logs/messages
```

`frozen=True` enforces the "no mutable global state" rule at the config level. The only runtime-mutable per-entry state (`last_content`, `error_notified`) lives inside the closure of that entry's async task.

## 7. Runtime Architecture

Single asyncio event loop. Startup:

1. `env.py` reads + asserts env vars.
2. `config.py` is imported.
3. Construct shared singletons: `AsyncOpenAI` client, `telegram.Bot`, one `webdriver.Firefox` (adblock add-on loaded if configured), and an `asyncio.Lock` guarding the browser.
4. Start the notifier task (§12).
5. Spawn one task per `Entry` in `ALL_ENTRIES`.
6. `asyncio.gather(...)` forever. On `SIGINT`/`SIGTERM`: cancel tasks, drain pending notifications, `driver.quit()`, exit.

Per-entry task shape:

```python
async def run_entry(entry: Entry, ctx: SharedCtx) -> None:
    last: str | None = None     # baseline lives in this closure
    error_notified = False      # so 4xx only pings once per outage streak
    while True:
        try:
            async with ctx.browser_lock:
                current = await asyncio.to_thread(fetch_via_selenium, entry, ctx)
        except FourXXError as e:
            if not error_notified:
                await ctx.notify_error(entry, e)
                error_notified = True
            await asyncio.sleep(entry.poll_interval_secs)
            continue
        except FiveXXError as e:
            log.warning("5xx on %s: %s", entry.url, e)
            await asyncio.sleep(entry.poll_interval_secs)
            continue

        error_notified = False
        if last is None:
            last = current                      # silent baseline
        elif current != last:
            diff = make_diff(last, current)
            reason, level = await ctx.llm.evaluate(entry.llm_state, diff)
            last = current
            if level is not NotificationLevel.NO_PING:
                await ctx.notify_queue.put(Change(entry, diff, reason, level))

        await asyncio.sleep(entry.poll_interval_secs)
```

Selenium is synchronous; every fetch is wrapped in `asyncio.to_thread` and serialized with `browser_lock` so only one entry drives the shared browser at a time. For ~tens of entries this is simpler and more robust than a pool.

Each entry task is wrapped in a supervisor that catches unexpected exceptions, logs them at `ERROR`, and restarts the task after a short backoff so one broken entry can't take the daemon down.

## 8. Page Fetching

- Firefox, headless, strict tracking protection on.
- If `ADBLOCK_XPI_PATH` is set, `driver.install_addon(path, temporary=True)` at startup. Primary motivation: drop ad traffic, prevent spinning-forever loads, and reduce noise diffs.
- `driver.set_page_load_timeout(entry.timeout_secs)`. On `TimeoutException` we do **not** raise; we proceed to xpath extraction against whatever DOM is present.
- Extraction: `driver.find_element(By.XPATH, entry.xpath).get_attribute("innerText")`. `innerText` respects visibility and CSS, so hidden boilerplate is excluded; no further normalization happens in-process — all noise judgement is deferred to the LLM.
- No JS wait strategy beyond the page-load timeout. If a target needs something smarter, it can be added per-entry later (not in scope for v1).

## 9. HTTP Status Handling

Selenium doesn't cleanly expose response codes, so before driving the browser each poll we do a `requests.head(url, allow_redirects=True, timeout=entry.timeout_secs)` to classify the status. Only on 2xx do we hand off to Selenium. Cost: one extra HEAD per poll. Cross-browser, no CDP dependency.

| Status | Behavior |
|---|---|
| 2xx | Proceed with Selenium fetch. |
| 3xx | Followed automatically by `requests` (and by Selenium). Log final URL at DEBUG. |
| 4xx | One Telegram error message on the first occurrence in an outage streak; keep polling at the normal interval; reset the flag silently when 2xx returns. |
| 408, `TimeoutException` from Selenium | Treated as 4xx. |
| 429 | Treated as 4xx (notify once, keep polling). No special backoff. |
| 5xx | WARNING log to stderr; keep polling at normal interval; no Telegram. |

## 10. Diffing

```python
difflib.unified_diff(
    last.splitlines(keepends=True),
    current.splitlines(keepends=True),
    n=3,
)
```

Joined into a single string, then truncated to a hard ceiling (16 KB). Truncation keeps a head slice + tail slice with a `...[N lines omitted]...` marker in the middle, so the LLM sees both ends of a large change.

## 11. LLM Evaluation

Single stateless call per change:

```python
await client.chat.completions.create(
    model=LLM_MODEL,
    temperature=LLM_TEMPERATURE,
    messages=[
        {"role": "system", "content": entry.llm_state.system_prompt},
        {"role": "user",   "content": f"Page: {entry.name or entry.url}\n\nDiff:\n{diff}"},
    ],
    response_format={"type": "json_object"},
)
```

Response schema (validated in code with pydantic):

```json
{ "reason": "<short sentence>", "level": "NO_PING | NORMAL_PING | MENTION_PING" }
```

`reason` is placed before `level` so the model spends tokens on its rationale before committing to a decision.

Parse failure, schema violation, or unknown enum value → WARNING log (raw response included) → treated as `NO_PING`. No Telegram notification on LLM misbehavior.

## 12. Notifications

### 12.1 Batching

A single long-running notifier task owns an `asyncio.Queue[Change]`. Loop:

1. `await queue.get()` (blocks until first change).
2. Drain any further items arriving within `NOTIFICATION_BATCH_WINDOW_SECS` (default 30 s).
3. Compose one message grouping all drained changes. If any item has level `MENTION_PING`, the `@user` mention is included and `parse_mode="MarkdownV2"` is used.
4. `bot.send_message(chat_id=TELEGRAM_GROUP_CHAT_ID, ...)`.
5. Repeat.

Worst-case latency from change-detected to message-sent = `poll_interval + batch_window`.

### 12.2 Message format

```
🔔 CoopCrawl — 2 changes

• Example prof — theses  (NORMAL)
  New MSc topic "Foo" added to the list.
  https://example.edu/~prof/theses

• Example prof — jobs  (MENTION)  @lars
  Deadline 2026-05-01 announced for TA position.
  https://example.edu/~prof/jobs
```

The diff itself is **not** included in the Telegram message (keeps it short, avoids MarkdownV2 escape pain). Diffs are written to stdout at INFO for post-hoc inspection.

### 12.3 Error notifications

Sent outside the batch queue, immediately, once per outage streak:

```
⚠️ CoopCrawl — https://example.edu/~prof/jobs returned 404. Will keep polling.
```

## 13. Logging

- Stdlib `logging`, configured once at startup.
- Format: `%(asctime)s %(levelname)s %(name)s %(message)s`.
- INFO: poll start/end per entry, notification sent, baseline set, diff body.
- DEBUG: LLM request/response, browser events, HEAD status.
- WARNING: 5xx, Selenium timeouts that yielded no content, LLM parse failures.
- ERROR: uncaught exception in a per-entry task (task is then restarted after backoff).
- Two stream handlers: stdout (INFO+), stderr (WARNING+). No file logging.

## 14. Coding Rules

- **Ruff** for both formatting and linting. Default ruleset plus `E`, `F`, `I`, `B`, `UP`, `N`, `SIM`, `RUF`.
- **100 % typed.** `mypy --strict` **and** `ty` must both be clean; CI fails on any diagnostic from either. No `# type: ignore` without a paired comment explaining the reason.
- **No mutable global state.** Shared resources (browser, LLM client, Telegram bot, queue) are constructed in `runtime.main()` and passed explicitly via a `SharedCtx` dataclass. `config.py` is pure constants. All dataclasses are `frozen=True`. The only module-level singletons are the logger and the immutable env-var constants from `env.py`.
- **No bare `except`**. No `except Exception` without a reason either.
- **Docstrings** only where behavior is non-obvious.

## 15. Testing

- `tests/test_diff.py` — diff helper: empty, identical, insertion, deletion, truncation.
- `tests/test_llm.py` — parses canned JSON responses; maps to enum; asserts `NO_PING` fallback on malformed output. `AsyncOpenAI` is monkeypatched with a fake.
- `tests/test_notify.py` — batching window coalesces multiple changes; `MENTION_PING` triggers the `@` mention in the composed message. Telegram `bot.send_message` replaced with `AsyncMock`.
- `tests/test_errors.py` — 4xx notifies exactly once; 5xx never notifies; 408 + Selenium `TimeoutException` classified as 4xx.
- **No end-to-end Selenium test.** We don't spin up Firefox in CI. The Selenium wrapper stays thin enough to not warrant one in v1.

CI pipeline: `uv run ruff check` → `uv run ruff format --check` → `uv run mypy --strict coopcrawl` → `uv run ty check coopcrawl` → `uv run pytest`.

## 16. Build & Run

```bash
uv sync

# long-running daemon
uv run python -m coopcrawl

# with a specific config
uv run python -m coopcrawl --config ./my-config.py

# single poll of every entry, then exit (dev convenience)
uv run python -m coopcrawl --once
```

CLI flags: `--config PATH`, `--once`, `-v/--verbose` (sets DEBUG level).

## 17. Flagged Decisions — Please Confirm or Overrule

Defaults I picked that weren't explicit in our exchange:

1. **`COOPCRAWL_TELEGRAM_BOT_TOKEN` env var.** You said "no other secrets" but the Telegram bot API needs a token — it has to live somewhere, and per your rule env-vars-only. OK?
2. **HTTP status via `requests.head()` before Selenium.** Adds one HEAD per poll. Alternative is Chrome+CDP, which locks us to Chrome. OK with the HEAD approach?
3. **`NOTIFICATION_BATCH_WINDOW_SECS = 30`.** Reasonable, or do you want shorter/longer?
4. **Shared Firefox + `asyncio.Lock`.** Serializes all fetches on one browser; trivial and cheap at tens of URLs. If you want parallelism later we'd switch to a small pool.
5. **`innerText`** as the extraction, not `textContent` or `innerHTML`. OK?
6. **uBlock Origin `.xpi` is user-supplied** at `./vendor/ublock_origin.xpi`, off if absent. No auto-download (avoids a supply-chain surface). OK?
7. **LLM parse/schema failure = silent `NO_PING`**, log only, no Telegram. OK?
8. **First-diff-ignored state is per-task, in-memory.** A restart silently re-baselines every entry — any change that happened during downtime is lost. You confirmed this explicitly; noting here for completeness.
