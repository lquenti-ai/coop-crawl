from __future__ import annotations

import argparse
import asyncio
import contextlib
import importlib.util
import logging
import signal
import sys
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType

from openai import AsyncOpenAI
from selenium import webdriver
from telegram import Bot
from telegram.request import HTTPXRequest

from coopcrawl import env
from coopcrawl.diff import make_diff
from coopcrawl.entry import Entry, NotificationLevel
from coopcrawl.errors import FiveXXError, FourXXError
from coopcrawl.fetch import build_driver, fetch_via_selenium, head_check
from coopcrawl.llm import LLM
from coopcrawl.notify import Change, Notifier

log = logging.getLogger("coopcrawl")

_SUPERVISOR_BACKOFF_SECS = 5.0


@dataclass(frozen=True)
class SharedCtx:
    driver: webdriver.Firefox
    browser_lock: asyncio.Lock
    llm: LLM
    notifier: Notifier
    diff_max_bytes: int


def load_config(path: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location("coopcrawl_user_config", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Failed to load config from {path}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


async def _poll_once(entry: Entry, ctx: SharedCtx, last: str | None) -> tuple[str | None, bool]:
    """Run one poll iteration. Returns (new_last, raised_4xx_flag)."""
    await asyncio.to_thread(head_check, entry.url, entry.timeout_secs)
    async with ctx.browser_lock:
        current = await asyncio.to_thread(fetch_via_selenium, ctx.driver, entry)

    if last is None:
        log.info("Baseline set for %s (%d chars)", entry.label, len(current))
        return current, False

    if current == last:
        log.info("No change for %s", entry.label)
        return last, False

    diff = make_diff(last, current)
    log.info("Diff for %s:\n%s", entry.label, diff)

    if len(diff.encode("utf-8")) > ctx.diff_max_bytes:
        reason = (
            f"Diff exceeds {ctx.diff_max_bytes} bytes — auto-classified without LLM evaluation."
        )
        level = NotificationLevel.NORMAL_PING
    else:
        reason, level = await ctx.llm.evaluate(entry.llm_state, entry.label, diff)

    if level is not NotificationLevel.NO_PING:
        await ctx.notifier.queue.put(Change(entry=entry, diff=diff, reason=reason, level=level))
    return current, False


async def run_entry(entry: Entry, ctx: SharedCtx) -> None:
    last: str | None = None
    error_notified = False
    while True:
        try:
            last, _ = await _poll_once(entry, ctx, last)
            error_notified = False
        except FourXXError as e:
            log.warning("4xx on %s: %s", entry.url, e)
            if not error_notified:
                await ctx.notifier.notify_error(entry, e.status)
                error_notified = True
        except FiveXXError as e:
            log.warning("5xx on %s: %s", entry.url, e)

        await asyncio.sleep(entry.poll_interval_secs)


async def run_entry_once(entry: Entry, ctx: SharedCtx) -> None:
    """Single-poll variant for --once mode. Always silent (baseline only)."""
    try:
        await _poll_once(entry, ctx, None)
    except (FourXXError, FiveXXError) as e:
        log.warning("Error during --once poll of %s: %s", entry.url, e)


async def supervised(entry: Entry, ctx: SharedCtx) -> None:
    while True:
        try:
            await run_entry(entry, ctx)
        except asyncio.CancelledError:
            raise
        except Exception:
            log.error("Per-entry task crashed for %s; restarting", entry.label, exc_info=True)
            await asyncio.sleep(_SUPERVISOR_BACKOFF_SECS)


def _configure_logging(verbose: bool) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    fmt = "%(asctime)s %(levelname)s %(name)s %(message)s"
    formatter = logging.Formatter(fmt)

    out = logging.StreamHandler(sys.stdout)
    out.setLevel(level)
    out.setFormatter(formatter)
    out.addFilter(lambda r: r.levelno < logging.WARNING)

    err = logging.StreamHandler(sys.stderr)
    err.setLevel(logging.WARNING)
    err.setFormatter(formatter)

    root = logging.getLogger()
    root.setLevel(level)
    root.handlers.clear()
    root.addHandler(out)
    root.addHandler(err)


async def _async_main(cfg: ModuleType, run_once: bool) -> None:
    openai_client = AsyncOpenAI(base_url=cfg.LLM_BASE_URL, api_key=env.LLM_API_KEY)
    llm = LLM(client=openai_client, model=cfg.LLM_MODEL, temperature=cfg.LLM_TEMPERATURE)

    bot = Bot(token=env.TELEGRAM_BOT_TOKEN, request=HTTPXRequest())
    notifier = Notifier(
        bot=bot,
        chat_id=cfg.TELEGRAM_GROUP_CHAT_ID,
        mention_user_id=cfg.TELEGRAM_MENTION_USER_ID,
        batch_window_secs=cfg.NOTIFICATION_BATCH_WINDOW_SECS,
    )

    driver = await asyncio.to_thread(
        build_driver,
        cfg.ADBLOCK_XPI_PATH,
        cfg.ADBLOCK_XPI_URL,
        cfg.FIREFOX_BINARY_PATH,
    )

    ctx = SharedCtx(
        driver=driver,
        browser_lock=asyncio.Lock(),
        llm=llm,
        notifier=notifier,
        diff_max_bytes=cfg.LLM_DIFF_MAX_BYTES,
    )

    entries: list[Entry] = list(cfg.ALL_ENTRIES)

    try:
        if run_once:
            await asyncio.gather(*(run_entry_once(e, ctx) for e in entries))
            return

        notifier_task = asyncio.create_task(notifier.run(), name="notifier")
        entry_tasks = [
            asyncio.create_task(supervised(e, ctx), name=f"entry:{e.label}") for e in entries
        ]

        stop = asyncio.Event()
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            with contextlib.suppress(NotImplementedError):
                loop.add_signal_handler(sig, stop.set)

        await stop.wait()
        log.info("Shutdown signal received; cancelling tasks")
        for t in (*entry_tasks, notifier_task):
            t.cancel()
        for t in (*entry_tasks, notifier_task):
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await t
        await notifier.drain_and_send()
    finally:
        await asyncio.to_thread(driver.quit)


def main() -> None:
    parser = argparse.ArgumentParser(prog="coopcrawl")
    parser.add_argument("--config", type=Path, default=Path("config.py"))
    parser.add_argument("--once", action="store_true", help="poll each entry once and exit")
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args()

    _configure_logging(args.verbose)
    cfg = load_config(args.config)
    asyncio.run(_async_main(cfg, run_once=args.once))


if __name__ == "__main__":
    main()
