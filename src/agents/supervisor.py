"""Supervisor Agent responsible for decomposing specifications into architectural plans."""

from __future__ import annotations

import json
from typing import Any

import pydantic

from src.agents.base import BaseAgent
from src.errors import ProviderError
from src.llm.protocol import LLMProvider
from src.logging_config import get_logger
from src.schema import PlanStep, TaskPlan

logger = get_logger(__name__)

SUPERVISOR_SYSTEM_PROMPT = """You are the Lead Software Architect and Supervisor Agent.
Your job is to analyze the user requirement and generate a clean, modular implementation plan.

You MUST respond strictly with a valid JSON object matching this schema:
{
  "goal": "Brief summary of what to build",
  "architecture_notes": "Key design decisions, patterns, edge cases to handle",
  "steps": [
    {
      "step_number": 1,
      "description": "What to do in this step",
      "target_file": "relative/path/to/file.py",
      "completed": false
    }
  ]
}

Rules:
- Keep the plan concise and practical (typically 2 to 4 steps).
- Always include an implementation file and a corresponding test file under tests/
  (e.g. solution.py and tests/test_solution.py).
- Do not output any markdown formatting or extra text outside the JSON object.
"""


class SupervisorAgent(BaseAgent):
    """Supervisor Agent that drafts structured plans for the team."""

    def __init__(
        self,
        provider: LLMProvider | None = None,
        sleep_func: Any = None,
    ) -> None:
        super().__init__(
            name="Supervisor",
            role_prompt=SUPERVISOR_SYSTEM_PROMPT,
            temperature=0.1,
            provider=provider,
            sleep_func=sleep_func,
        )

    def plan_task(self, user_prompt: str) -> tuple[TaskPlan, bool]:
        """Generates a TaskPlan object from the user prompt.

        Returns:
            tuple[TaskPlan, bool]: The plan and a boolean flag `plan_degraded`
            indicating whether the degraded fallback path was activated.
        """
        # Attempt structured output if provider supports it (T1.3, N5)
        if self.provider.capabilities.supports_json_schema:
            try:
                messages = [
                    {"role": "system", "content": self.role_prompt},
                    {"role": "user", "content": user_prompt},
                ]
                resp = self._call_provider_with_retry(
                    messages=messages,
                    response_format=TaskPlan,
                )
                self.budget_tracker.record_usage(resp)
                if resp.content:
                    parsed = TaskPlan.model_validate_json(resp.content)
                    return parsed, False
            except (pydantic.ValidationError, ProviderError) as exc:
                logger.warning("structured_output_parse_failed_retrying", error=str(exc))

        # Standard ReAct / unstructured path with repair retry
        response_text = self.run(user_instruction=user_prompt)

        # Attempt to parse
        cleaned = response_text.strip()
        cleaned = cleaned.removeprefix("```json").removeprefix("```").removesuffix("```").strip()

        try:
            data = json.loads(cleaned)
            return TaskPlan.model_validate(data), False
        except (json.JSONDecodeError, pydantic.ValidationError) as exc:
            logger.warning(
                "plan_parsing_failed_attempting_repair",
                error=str(exc),
                response_snippet=cleaned[:100],
            )
            # One repair retry with explicit error context
            repair_prompt = (
                f"Your previous response failed schema validation: {exc!s}\n"
                f"Please correct the JSON and return ONLY valid JSON matching TaskPlan."
            )
            try:
                repair_text = self.run(user_instruction=repair_prompt, context=cleaned)
                cleaned_repair = (
                    repair_text.strip()
                    .removeprefix("```json")
                    .removeprefix("```")
                    .removesuffix("```")
                    .strip()
                )
                data = json.loads(cleaned_repair)
                return TaskPlan.model_validate(data), False
            except (json.JSONDecodeError, pydantic.ValidationError):
                # Degraded path: activate deterministic fallback plan and mark degraded
                logger.warning("supervisor_plan_degraded_path_activated")
                degraded_plan = TaskPlan(
                    goal=user_prompt,
                    architecture_notes="Direct implementation with unit testing (degraded plan).",
                    steps=[
                        PlanStep(
                            step_number=1,
                            description="Implement core logic and algorithms",
                            target_file="solution.py",
                        ),
                        PlanStep(
                            step_number=2,
                            description="Write comprehensive pytest test suite",
                            target_file="tests/test_solution.py",
                        ),
                    ],
                )
                return degraded_plan, True
