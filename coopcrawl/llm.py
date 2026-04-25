from __future__ import annotations

import logging

from openai import AsyncOpenAI
from pydantic import BaseModel, ValidationError

from coopcrawl.entry import LLMState, NotificationLevel

log = logging.getLogger(__name__)


class LLMResponse(BaseModel):
    reason: str
    level: NotificationLevel


class LLM:
    def __init__(
        self,
        client: AsyncOpenAI,
        model: str,
        temperature: float,
    ) -> None:
        self._client = client
        self._model = model
        self._temperature = temperature

    async def evaluate(
        self,
        state: LLMState,
        entry_label: str,
        diff: str,
    ) -> tuple[str, NotificationLevel]:
        try:
            completion = await self._client.chat.completions.create(
                model=self._model,
                temperature=self._temperature,
                messages=[
                    {"role": "system", "content": state.system_prompt},
                    {"role": "user", "content": f"Page: {entry_label}\n\nDiff:\n{diff}"},
                ],
                response_format={"type": "json_object"},
            )
        except Exception:
            log.warning("LLM call failed", exc_info=True)
            return "", NotificationLevel.NO_PING

        raw = completion.choices[0].message.content or ""
        log.debug("LLM raw response: %s", raw)
        try:
            parsed = LLMResponse.model_validate_json(raw)
        except ValidationError:
            log.warning("LLM produced unparseable response: %r", raw)
            return "", NotificationLevel.NO_PING
        return parsed.reason, parsed.level
