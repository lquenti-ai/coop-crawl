# TODO for next session

V1 is implemented and CI-green (ruff, mypy --strict, ty, pytest 32/32).
Things still to do or verify before this can be called done-done.

## Must do

- **Real end-to-end smoke run.** Never executed `uv run python -m coopcrawl --once -v`.
  Need a real Firefox + geckodriver, a reachable LLM endpoint, and Telegram
  creds. Verify: driver builds, uBlock loads, HEAD check fires, baseline is set
  silently, no notification on first poll, daemon exits cleanly.
- **uBlock install path.** `fetch.build_driver` downloads the XPI on demand and
  retries once on `install_addon` failure, but the retry path has never run.
  Force a failure (corrupt the cached file) and confirm it heals itself, and
  that a second failure aborts startup with `driver.quit()` actually called.
- **PTB Bot lifecycle.** `python-telegram-bot` 22.x may require
  `await bot.initialize()` / `await bot.shutdown()` around the run. Currently we
  just construct `Bot(token, request=HTTPXRequest())` and call `send_message`.
  Confirm against the installed version; wire init/shutdown into `_async_main`
  if needed.

## Spec gaps to close

- **Test: 4xx-once-per-streak** (spec §15). `tests/test_errors.py` only covers
  `classify_status`. Add a runtime-level test that drives `run_entry` against a
  fake `head_check` returning 404 → 404 → 200 → 404 and asserts
  `notifier.notify_error` was awaited exactly twice (once per streak).
- **Test: 5xx never notifies** (spec §15). Same shape — fake `head_check` raises
  `FiveXXError`, assert `notify_error` is never awaited.
- **Test: Selenium `TimeoutException` handling.** Spec §9 says treat as 4xx;
  spec §8 says don't raise, extract whatever loaded. Current code follows §8.
  Either add a test pinning that behavior, or escalate to `FourXXError` when
  extraction yields empty text — decide which reading of the spec wins and
  commit to it. (My read: §8 wins because it's the more specific rule about
  the Selenium step; §9's row is about HEAD-level 408. Document this in a
  comment in `fetch.py` once decided.)
- **Message format vs. spec §12.2.** Spec example shows `@lars` literally; the
  config only has `TELEGRAM_MENTION_USER_ID` (int), so I used a zero-width
  `[⁠](tg://user?id=…)` trick to trigger a real notification. Decide:
  (a) keep the invisible-link trick, (b) add `TELEGRAM_MENTION_USERNAME` to
  `config.py` and inline `@username`, or (c) both. Update spec §12.2 example to
  match whichever wins so README and code don't drift.
- **MarkdownV2 escaping audit.** `_md2_escape` covers the documented set, but
  the spec example uses parenthesized `(NORMAL)` / `(MENTION)` — I escape those
  parens. Render a real test message in a Telegram chat and confirm it looks
  right; tweak if any character slips through.
- **`--once` semantics.** Currently runs each entry's first poll and exits, so
  it's silent by construction (baseline only). If we ever want `--once` to also
  detect changes against a persisted baseline, we'd need state on disk — but
  spec §2 explicitly forbids persistence, so this is fine. Just leaving the
  note so a future me doesn't "fix" it.

## Nice-to-have / hardening

- **Logging diff body at INFO** — spec §13 says diff body goes to INFO; I do
  this in `runtime._poll_once` via `log.info("Diff for %s:\n%s", ...)`. Confirm
  that lands on stdout and isn't accidentally swallowed by the stderr handler
  filter.
- **Backoff jitter** in `supervised()` — currently a flat 5 s. If many entries
  crash simultaneously we'll thunder. Add small jitter once we see it happen.
- **Per-entry HEAD timeout vs. page-load timeout** — both use
  `entry.timeout_secs`. Consider splitting if a target has a cheap HEAD but a
  slow render, but only after a real entry needs it.
- **`response_format={"type": "json_object"}`** — some OpenAI-compatible
  servers (older vLLM, some GLM builds) reject this. If we hit one, fall back
  to plain prompting + tolerant parsing. Don't pre-engineer it.

## Verification checklist for next session

```bash
uv run ruff check
uv run ruff format --check
uv run mypy --strict coopcrawl
uv run ty check coopcrawl
uv run pytest
# then, with real env vars + Firefox:
uv run python -m coopcrawl --once -v
```
