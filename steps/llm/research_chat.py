import logging
import os
from typing import Any, Dict

from openai import AsyncOpenAI

from ..base import BaseStep

logger = logging.getLogger(__name__)

_DEFAULT_MODEL = "deepseek-chat"


class ResearchChatStep(BaseStep):
    async def execute(self, config: Dict[str, Any], context: Any) -> Dict[str, Any]:
        prompt = str(config.get("prompt", ""))
        if not prompt:
            raise ValueError("research_chat requires a non-empty prompt")

        model = config.get("model") or os.getenv("REACT_MODEL", _DEFAULT_MODEL)

        client = AsyncOpenAI(
            api_key=os.getenv("OPENAI_API_KEY"),
            base_url=os.getenv("OPENAI_BASE_URL"),
        )

        try:
            completion = await client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.3,
            )
        except Exception as exc:
            raise RuntimeError(
                "research_chat API call failed: {0}".format(exc)
            ) from exc

        content = completion.choices[0].message.content or ""
        used_model = completion.model or model

        return {"content": content, "model": used_model}
