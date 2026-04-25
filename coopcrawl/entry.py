from __future__ import annotations

import enum
from dataclasses import dataclass


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
    xpath: str = "/"
    timeout_secs: int = 20
    poll_interval_secs: int = 5 * 60
    name: str | None = None

    @property
    def label(self) -> str:
        return self.name or self.url
