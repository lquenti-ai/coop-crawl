from __future__ import annotations

import asyncio
import contextlib
from typing import Any
from unittest.mock import AsyncMock

import pytest
from telegram.constants import ParseMode

from coopcrawl.entry import Entry, LLMState, NotificationLevel
from coopcrawl.notify import Change, Notifier, compose


def _entry(name: str, url: str = "https://x.example/p") -> Entry:
    return Entry(
        url=url,
        llm_state=LLMState(system_prompt="sp"),
        name=name,
    )


def test_compose_normal_only_no_markdown() -> None:
    changes = [
        Change(_entry("A"), diff="d1", reason="r1", level=NotificationLevel.NORMAL_PING),
        Change(_entry("B"), diff="d2", reason="r2", level=NotificationLevel.NORMAL_PING),
    ]
    text, mode = compose(changes, mention_user_id=42)
    assert mode is None
    assert "2 changes" in text
    assert "A" in text and "B" in text
    assert "r1" in text and "r2" in text


def test_compose_mention_uses_markdownv2_and_mention() -> None:
    changes = [
        Change(_entry("A"), diff="d", reason="r", level=NotificationLevel.MENTION_PING),
    ]
    text, mode = compose(changes, mention_user_id=99)
    assert mode is ParseMode.MARKDOWN_V2
    assert "tg://user?id=99" in text


def test_compose_singular_header() -> None:
    changes = [
        Change(_entry("A"), diff="d", reason="r", level=NotificationLevel.NORMAL_PING),
    ]
    text, _ = compose(changes, mention_user_id=1)
    assert "1 change" in text and "1 changes" not in text


@pytest.mark.asyncio
async def test_notifier_coalesces_within_window() -> None:
    bot = AsyncMock()
    notif = Notifier(bot=bot, chat_id=-1, mention_user_id=1, batch_window_secs=0.05)
    task = asyncio.create_task(notif.run())

    await notif.queue.put(Change(_entry("A"), "d", "r1", NotificationLevel.NORMAL_PING))
    await notif.queue.put(Change(_entry("B"), "d", "r2", NotificationLevel.NORMAL_PING))

    await asyncio.sleep(0.2)
    task.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await task

    assert bot.send_message.await_count == 1
    kwargs: dict[str, Any] = bot.send_message.await_args.kwargs
    assert "2 changes" in kwargs["text"]


@pytest.mark.asyncio
async def test_notifier_separates_across_windows() -> None:
    bot = AsyncMock()
    notif = Notifier(bot=bot, chat_id=-1, mention_user_id=1, batch_window_secs=0.05)
    task = asyncio.create_task(notif.run())

    await notif.queue.put(Change(_entry("A"), "d", "r1", NotificationLevel.NORMAL_PING))
    await asyncio.sleep(0.2)
    await notif.queue.put(Change(_entry("B"), "d", "r2", NotificationLevel.NORMAL_PING))
    await asyncio.sleep(0.2)

    task.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await task

    assert bot.send_message.await_count == 2
