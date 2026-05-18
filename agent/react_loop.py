import json
import logging
import os
from typing import Any, Dict, List, Optional

from openai import AsyncOpenAI

from ..engine.core.builder import PipelineBuilder
from .tools import bind_builder, execute_tool, get_tool_specs

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You operate a draft builder for quant research plans.

Available actions:
- add_step
- update_step
- connect_steps
- get_catalog
- get_details
- get_pipeline

Operating rules:
- Build the plan through tool calls, not plain-text answers.
- `add_step` and `update_step` evaluate a step immediately and return either output or an error.
- Use catalog inspection before guessing a config shape.
- If a tool reports an error, repair the affected step instead of abandoning the draft.
- Only call `get_pipeline` after the draft contains a coherent ordered path.

For a simple momentum-ranking request, a sensible draft usually includes:
trigger.manual -> data.market_bars -> factor.momentum -> factor.rank -> research_chat
"""

# Maximum consecutive turns where the model produces no tool calls before
_MAX_IDLE_TURNS = 3


class ReactLoopAgent:
    def __init__(self, builder: Optional[PipelineBuilder] = None):
        self.builder = builder or PipelineBuilder()
        bind_builder(self.builder)
        self.client = AsyncOpenAI(
            api_key=os.getenv("OPENAI_API_KEY"),
            base_url=os.getenv("OPENAI_BASE_URL"),
        )
        self.model = os.getenv("REACT_MODEL", "gpt-4o-mini")
        self.max_iters = 12

    async def run(self, prompt: str) -> Dict[str, Any]:
        coordinator = _LoopCoordinator(
            client=self.client,
            model=self.model,
            prompt=prompt,
            iteration_limit=self.max_iters,
        )
        transcript, stop_reason = await coordinator.run()
        logger.info("Agent loop finished: %s", stop_reason)
        return {
            "pipeline": self.builder.get_pipeline(),
            "messages": transcript,
            "stop_reason": stop_reason,
        }


class _LoopCoordinator:
    def __init__(
        self,
        client: AsyncOpenAI,
        model: str,
        prompt: str,
        iteration_limit: int,
    ) -> None:
        self.client = client
        self.model = model
        self.iteration_limit = iteration_limit
        self.messages: List[Dict[str, Any]] = self._starting_transcript(prompt)
        self._tool_specs = get_tool_specs()

    async def run(self) -> tuple[List[Dict[str, Any]], str]:
        idle_turns = 0

        for turn in range(self.iteration_limit):
            reply = await self._next_model_message()
            self.messages.append(self._format_assistant_turn(reply))

            if not reply.tool_calls:
                idle_turns += 1
                if idle_turns >= _MAX_IDLE_TURNS:
                    logger.warning(
                        "Agent produced no tool calls for %d consecutive turns; aborting.",
                        idle_turns,
                    )
                    return self.messages, "stalled"
                self.messages.append(self._nudge_message())
                continue

            idle_turns = 0
            finished, had_errors = await self._apply_requested_actions(reply.tool_calls)

            if finished:
                return self.messages, "success"

            if had_errors:
                self.messages.append(self._repair_prompt())

        return self.messages, "iteration_limit_reached"

    async def _next_model_message(self) -> Any:
        completion = await self.client.chat.completions.create(
            model=self.model,
            messages=self.messages,
            tools=self._tool_specs,
            tool_choice="auto",
            temperature=0,
        )
        return completion.choices[0].message

    async def _apply_requested_actions(
        self, tool_calls: List[Any]
    ) -> tuple[bool, bool]:
        should_finish = False
        had_errors = False

        for tool_call in tool_calls:
            tool_message, result = await self._run_one_tool(tool_call)
            self.messages.append(tool_message)

            if not result.get("success", True):
                had_errors = True
                logger.debug(
                    "Tool %s reported failure: %s",
                    tool_call.function.name,
                    result.get("error"),
                )

            if tool_call.function.name == "get_pipeline":
                should_finish = bool(result.get("success"))

        return should_finish, had_errors

    async def _run_one_tool(self, tool_call: Any) -> tuple[Dict[str, Any], Dict[str, Any]]:
        raw_arguments = tool_call.function.arguments or "{}"
        try:
            parsed_arguments = json.loads(raw_arguments)
        except json.JSONDecodeError as exc:
            result = {"success": False, "error": "Invalid JSON arguments: {0}".format(exc)}
        else:
            result = await execute_tool(tool_call.function.name, parsed_arguments)

        tool_message = {
            "role": "tool",
            "tool_call_id": tool_call.id,
            "name": tool_call.function.name,
            "content": json.dumps(result, ensure_ascii=True),
        }
        return tool_message, result

    def _starting_transcript(self, prompt: str) -> List[Dict[str, Any]]:
        return [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ]

    def _format_assistant_turn(self, message: Any) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "role": "assistant",
            "content": message.content or "",
        }
        if message.tool_calls:
            payload["tool_calls"] = [
                self._encode_tool_call(tc) for tc in message.tool_calls
            ]
        return payload

    def _encode_tool_call(self, tool_call: Any) -> Dict[str, Any]:
        return {
            "id": tool_call.id,
            "type": "function",
            "function": {
                "name": tool_call.function.name,
                "arguments": tool_call.function.arguments,
            },
        }

    def _nudge_message(self) -> Dict[str, str]:
        return {
            "role": "user",
            "content": (
                "Continue through tool use. Inspect, repair, or extend the draft, "
                "and only finish after exporting it with get_pipeline."
            ),
        }

    def _repair_prompt(self) -> Dict[str, str]:
        return {
            "role": "user",
            "content": (
                "One or more tool calls returned an error. "
                "Read the error message, fix the affected step with update_step or "
                "replace it with add_step, then continue building the pipeline."
            ),
        }