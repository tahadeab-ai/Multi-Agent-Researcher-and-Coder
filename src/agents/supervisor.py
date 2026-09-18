"""Supervisor Agent responsible for decomposing specifications into architectural plans."""

import json
from src.agents.base import BaseAgent
from src.schema import TaskPlan, PlanStep


SUPERVISOR_SYSTEM_PROMPT = """You are the Lead Software Architect and Supervisor Agent.
Your job is to analyze the user's coding requirement and generate a clean, modular, step-by-step implementation plan.

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
- Always include an implementation file and a corresponding test file under tests/ (e.g. solution.py and tests/test_solution.py).
- Do not output any markdown formatting or extra text outside the JSON object.
"""


class SupervisorAgent(BaseAgent):
    """Supervisor Agent that drafts structured plans for the team."""

    def __init__(self):
        super().__init__(
            name="Supervisor",
            role_prompt=SUPERVISOR_SYSTEM_PROMPT,
            temperature=0.1,
        )

    def plan_task(self, user_prompt: str) -> TaskPlan:
        """Generates a TaskPlan Pydantic object from the user prompt."""
        response_text = self.run(user_instruction=user_prompt)

        # Clean potential markdown fences
        cleaned = response_text.strip()
        if cleaned.startswith("```json"):
            cleaned = cleaned[7:]
        if cleaned.startswith("```"):
            cleaned = cleaned[3:]
        if cleaned.endswith("```"):
            cleaned = cleaned[:-3]
        cleaned = cleaned.strip()

        try:
            data = json.loads(cleaned)
            return TaskPlan.model_validate(data)
        except Exception:
            # Fallback plan if JSON parsing encounters issues
            return TaskPlan(
                goal=user_prompt,
                architecture_notes="Direct implementation with unit testing.",
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
