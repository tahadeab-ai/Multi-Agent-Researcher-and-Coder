"""Base Agent class implementing tool calling execution loop."""

import json
from typing import List, Dict, Any, Callable, Optional
from openai import OpenAI
from src.config import settings


class BaseAgent:
    """Foundational agent equipped with LLM client and tool dispatching loop."""

    def __init__(
        self,
        name: str,
        role_prompt: str,
        tools: Optional[List[Dict[str, Any]]] = None,
        tool_functions: Optional[Dict[str, Callable]] = None,
        temperature: float = 0.2,
    ):
        self.name = name
        self.role_prompt = role_prompt
        self.tools = tools or []
        self.tool_functions = tool_functions or {}
        self.temperature = temperature

        # Initialize OpenAI or Ollama client
        if settings.llm_provider == "ollama":
            self.client = OpenAI(
                base_url=settings.ollama_base_url,
                api_key="ollama",
            )
        else:
            self.client = OpenAI(
                api_key=settings.openai_api_key or "sk-dummy-for-testing",
            )

    def run(self, user_instruction: str, context: Optional[str] = None) -> str:
        """Runs the ReAct loop until final text response or max_steps reached."""
        messages: List[Dict[str, Any]] = [
            {"role": "system", "content": self.role_prompt},
        ]

        if context:
            messages.append({"role": "system", "content": f"Context:\n{context}"})

        messages.append({"role": "user", "content": user_instruction})

        step = 0
        while step < settings.max_agent_steps:
            step += 1

            # Prepare API arguments
            kwargs: Dict[str, Any] = {
                "model": settings.llm_model,
                "messages": messages,
                "temperature": self.temperature,
            }
            if self.tools:
                kwargs["tools"] = self.tools

            response = self.client.chat.completions.create(**kwargs)
            message = response.choices[0].message

            # Check if model responded directly with text (Finished turn)
            if not message.tool_calls:
                return message.content or ""

            # Append assistant message with tool calls to conversation history
            messages.append(message.model_dump())

            # Execute tool calls
            for tool_call in message.tool_calls:
                fn_name = tool_call.function.name
                fn_args_raw = tool_call.function.arguments

                try:
                    fn_args = json.loads(fn_args_raw)
                except Exception as json_err:
                    fn_args = {}
                    tool_output = json.dumps({"error": f"Invalid JSON in tool args: {str(json_err)}"})
                else:
                    if fn_name in self.tool_functions:
                        try:
                            tool_func = self.tool_functions[fn_name]
                            tool_output = str(tool_func(**fn_args))
                        except Exception as exec_err:
                            tool_output = json.dumps({"error": f"Tool execution failed: {str(exec_err)}"})
                    else:
                        tool_output = json.dumps({"error": f"Tool '{fn_name}' not recognized."})

                # Append tool observation back to messages
                messages.append({
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "name": fn_name,
                    "content": tool_output,
                })

        return "Warning: Agent reached maximum steps before generating final response."
