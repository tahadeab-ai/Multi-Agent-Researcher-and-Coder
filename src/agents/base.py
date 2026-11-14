"""Base Agent class implementing tool calling execution loop with resilience and budgeting."""

from __future__ import annotations

import asyncio
import json
from collections.abc import Callable
from typing import Any

from tenacity import retry, stop_after_attempt

from src.config import settings
from src.errors import MaxStepsExceededError, ToolError
from src.llm.budget import BudgetTracker, truncate_tool_output
from src.llm.factory import build_provider
from src.llm.protocol import LLMProvider, LLMResponse
from src.llm.retry import WaitRetryAfterOrExponential, retry_if_phoenix_retryable
from src.logging_config import get_logger

logger = get_logger(__name__)


class BaseAgent:
    """Foundational agent equipped with LLM provider, retry resilience, and tool dispatch."""

    def __init__(
        self,
        name: str,
        role_prompt: str,
        tools: list[dict[str, Any]] | None = None,
        tool_functions: dict[str, Callable[..., Any]] | None = None,
        temperature: float = 0.2,
        provider: LLMProvider | None = None,
        budget_tracker: BudgetTracker | None = None,
        sleep_func: Callable[[float], Any] | None = None,
    ) -> None:
        self.name = name
        self.role_prompt = role_prompt
        self.tools = tools or []
        self.tool_functions = tool_functions or {}
        self.temperature = temperature
        self.budget_tracker = budget_tracker or BudgetTracker()
        self.sleep_func = sleep_func

        # Provider initialization
        if provider is not None:
            self.provider = provider
        else:
            settings.validate_provider()
            self.provider = build_provider(settings)  # type: ignore[assignment]

    def _call_provider_with_retry(
        self,
        messages: list[dict[str, Any]],
        response_format: type | None = None,
    ) -> LLMResponse:
        """Call provider with tenacity retry on 429/timeout/500 errors."""
        retry_decorator = retry(
            retry=retry_if_phoenix_retryable(),
            wait=WaitRetryAfterOrExponential(),
            stop=stop_after_attempt(5),
            sleep=self.sleep_func if self.sleep_func is not None else None,  # type: ignore[arg-type]
            reraise=True,
        )

        def _do_call() -> LLMResponse:
            return self.provider.generate(
                messages=messages,
                tools=self.tools if self.tools else None,
                temperature=self.temperature,
                response_format=response_format,
            )

        wrapped = retry_decorator(_do_call)
        return wrapped()

    async def _acall_provider_with_retry(
        self,
        messages: list[dict[str, Any]],
        response_format: type | None = None,
    ) -> LLMResponse:
        """Call provider asynchronously with tenacity retry."""

        async def _async_sleep(seconds: float) -> None:
            if self.sleep_func is not None:
                res = self.sleep_func(seconds)
                if asyncio.iscoroutine(res):
                    await res
            else:
                await asyncio.sleep(seconds)

        retry_decorator = retry(
            retry=retry_if_phoenix_retryable(),
            wait=WaitRetryAfterOrExponential(),
            stop=stop_after_attempt(5),
            sleep=_async_sleep,  # type: ignore[arg-type]
            reraise=True,
        )

        async def _do_call() -> LLMResponse:
            return await self.provider.agenerate(
                messages=messages,
                tools=self.tools if self.tools else None,
                temperature=self.temperature,
                response_format=response_format,
            )

        wrapped = retry_decorator(_do_call)
        return await wrapped()

    def _dispatch_tool(self, fn_name: str, fn_args: dict[str, Any]) -> str:
        """Execute a tool function at the dispatch trust boundary."""
        if fn_name not in self.tool_functions:
            return json.dumps({"error": f"Tool '{fn_name}' not recognized."})

        tool_func = self.tool_functions[fn_name]
        try:
            raw_output = tool_func(**fn_args)
            return str(raw_output)
        except Exception as exc:  # noqa: BLE001 — boundary converts to structured ToolError
            logger.exception("tool_dispatch_error", tool=fn_name, exc=exc)
            raise ToolError(tool=fn_name, cause=exc) from exc

    def run(self, user_instruction: str, context: str | None = None) -> str:
        """Runs the ReAct loop until final text response or max_steps reached."""
        return asyncio.run(self.run_async(user_instruction, context))

    async def run_async(self, user_instruction: str, context: str | None = None) -> str:
        """Runs the asynchronous ReAct loop until final text response or max_steps reached."""
        messages: list[dict[str, Any]] = [
            {"role": "system", "content": self.role_prompt},
        ]

        if context:
            messages.append({"role": "system", "content": f"Context:\n{context}"})

        messages.append({"role": "user", "content": user_instruction})

        step = 0
        while step < settings.max_agent_steps:
            step += 1

            response = await self._acall_provider_with_retry(messages=messages)
            self.budget_tracker.record_usage(response)

            # Check if model responded directly with text (Finished turn)
            if not response.tool_calls:
                return response.content or ""

            # Append assistant message with tool calls to conversation history
            assistant_msg: dict[str, Any] = {
                "role": "assistant",
                "content": response.content,
                "tool_calls": [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {"name": tc.name, "arguments": tc.arguments},
                    }
                    for tc in response.tool_calls
                ],
            }
            messages.append(assistant_msg)

            # Execute tool calls
            for tc in response.tool_calls:
                fn_name = tc.name
                try:
                    fn_args = json.loads(tc.arguments) if tc.arguments else {}
                except json.JSONDecodeError as json_err:
                    fn_args = {}
                    tool_output = json.dumps({"error": f"Invalid JSON in tool args: {json_err!s}"})
                else:
                    try:
                        # Synchronous tool dispatch in thread pool
                        raw_output = await asyncio.to_thread(self._dispatch_tool, fn_name, fn_args)
                        tool_output = truncate_tool_output(raw_output)
                    except ToolError as tool_err:
                        # N1: ReAct loop catches ToolError and appends tool observation
                        tool_output = json.dumps({"error": str(tool_err)})

                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tc.id,
                        "name": fn_name,
                        "content": tool_output,
                    }
                )

        raise MaxStepsExceededError(agent=self.name, steps=settings.max_agent_steps)
