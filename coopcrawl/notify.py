from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass

from telegram import Bot
from telegram.constants import ParseMode

from coopcrawl.entry import Entry, NotificationLevel

log = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class Change:
    entry: Entry
    diff: str
    reason: str
    level: NotificationLevel


_MD2_ESCAPE = r"_*[]()~`>#+-=|{}.!\\"


def _md2_escape(text: str) -> str:
    return "".join("\\" + c if c in _MD2_ESCAPE else c for c in text)


def compose(
    changes: list[Change],
    mention_user_id: int,
) -> tuple[str, ParseMode | None]:
    """Build the Telegram message body and parse-mode for a batch."""
    has_mention = any(c.level is NotificationLevel.MENTION_PING for c in changes)
    n = len(changes)
    header = f"🔔 CoopCrawl — {n} change{'' if n == 1 else 's'}"

    if has_mention:
        lines: list[str] = [_md2_escape(header)]
        for c in changes:
            tag = "MENTION" if c.level is NotificationLevel.MENTION_PING else "NORMAL"
            mention_suffix = (
                f"  [⁠](tg://user?id={mention_user_id})"
                if c.level is NotificationLevel.MENTION_PING
                else ""
            )
            lines.append("")
            lines.append(f"• {_md2_escape(c.entry.label)}  \\({tag}\\){mention_suffix}")
            if c.reason:
                lines.append(f"  {_md2_escape(c.reason)}")
            lines.append(f"  {_md2_escape(c.entry.url)}")
        return "\n".join(lines), ParseMode.MARKDOWN_V2

    lines = [header]
    for c in changes:
        lines.append("")
        lines.append(f"• {c.entry.label}  (NORMAL)")
        if c.reason:
            lines.append(f"  {c.reason}")
        lines.append(f"  {c.entry.url}")
    return "\n".join(lines), None


class Notifier:
    def __init__(
        self,
        bot: Bot,
        chat_id: int,
        mention_user_id: int,
        batch_window_secs: float,
    ) -> None:
        self._bot = bot
        self._chat_id = chat_id
        self._mention_user_id = mention_user_id
        self._batch_window = batch_window_secs
        self.queue: asyncio.Queue[Change] = asyncio.Queue()

    async def run(self) -> None:
        while True:
            first = await self.queue.get()
            batch: list[Change] = [first]
            deadline = asyncio.get_running_loop().time() + self._batch_window
            while True:
                remaining = deadline - asyncio.get_running_loop().time()
                if remaining <= 0:
                    break
                try:
                    nxt = await asyncio.wait_for(self.queue.get(), timeout=remaining)
                except TimeoutError:
                    break
                batch.append(nxt)
            await self._send_batch(batch)

    async def _send_batch(self, batch: list[Change]) -> None:
        text, parse_mode = compose(batch, self._mention_user_id)
        try:
            await self._bot.send_message(
                chat_id=self._chat_id,
                text=text,
                parse_mode=parse_mode,
                disable_web_page_preview=True,
            )
            log.info("Sent batch of %d change(s)", len(batch))
        except Exception:
            log.error("Telegram send failed", exc_info=True)

    async def drain_and_send(self) -> None:
        """Flush whatever is currently queued as a single message (used at shutdown)."""
        batch: list[Change] = []
        while not self.queue.empty():
            batch.append(self.queue.get_nowait())
        if batch:
            await self._send_batch(batch)

    async def notify_error(self, entry: Entry, status: int) -> None:
        text = f"⚠️ CoopCrawl — {entry.url} returned {status}. Will keep polling."
        try:
            await self._bot.send_message(
                chat_id=self._chat_id,
                text=text,
                disable_web_page_preview=True,
            )
        except Exception:
            log.error("Telegram error-notify failed", exc_info=True)
