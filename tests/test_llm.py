from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pytest

from coopcrawl.entry import LLMState, NotificationLevel
from coopcrawl.llm import LLM


@dataclass
class _FakeMessage:
    content: str


@dataclass
class _FakeChoice:
    message: _FakeMessage


@dataclass
class _FakeCompletion:
    choices: list[_FakeChoice]


class _FakeCompletions:
    def __init__(self, payload: str) -> None:
        self._payload = payload
        self.calls: list[dict[str, Any]] = []

    async def create(self, **kwargs: Any) -> _FakeCompletion:
        self.calls.append(kwargs)
        return _FakeCompletion(choices=[_FakeChoice(message=_FakeMessage(content=self._payload))])


class _FakeChat:
    def __init__(self, payload: str) -> None:
        self.completions = _FakeCompletions(payload)


class _FakeClient:
    def __init__(self, payload: str) -> None:
        self.chat = _FakeChat(payload)


def _make(payload: str) -> LLM:
    fake = _FakeClient(payload)
    # The LLM class only touches `client.chat.completions.create`; structural typing is fine.
    return LLM(client=fake, model="m", temperature=0.0)  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_normal_ping_parses() -> None:
    llm = _make('{"reason": "new item", "level": "NORMAL_PING"}')
    reason, level = await llm.evaluate(LLMState(system_prompt="sp"), "label", "diff")
    assert reason == "new item"
    assert level is NotificationLevel.NORMAL_PING


@pytest.mark.asyncio
async def test_mention_ping_parses() -> None:
    llm = _make('{"reason": "deadline", "level": "MENTION_PING"}')
    _, level = await llm.evaluate(LLMState(system_prompt="sp"), "label", "diff")
    assert level is NotificationLevel.MENTION_PING


@pytest.mark.asyncio
async def test_malformed_json_fallback() -> None:
    llm = _make("not json at all")
    reason, level = await llm.evaluate(LLMState(system_prompt="sp"), "label", "diff")
    assert reason == ""
    assert level is NotificationLevel.NO_PING


@pytest.mark.asyncio
async def test_unknown_enum_fallback() -> None:
    llm = _make('{"reason": "x", "level": "MAYBE"}')
    _, level = await llm.evaluate(LLMState(system_prompt="sp"), "label", "diff")
    assert level is NotificationLevel.NO_PING
