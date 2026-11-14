"""Tests for T1.7: Async Agent Execution Loop and Concurrent Read-Only Tool Execution."""

from __future__ import annotations

import time

import pytest

from src.agents.base import BaseAgent
from src.llm.protocol import ToolCall
from tests.mocks.mock_provider import MockProvider


@pytest.mark.asyncio
async def test_parallel_readonly_tools_run_concurrently() -> None:
    """Read-only tools (read_file, list_directory) must be gathered concurrently."""
    delay = 0.2

    def slow_read_file(filepath: str) -> str:
        time.sleep(delay)
        return f"content of {filepath}"

    mock = MockProvider()
    mock.enqueue_response(
        tool_calls=[
            ToolCall(id="tc1", name="read_file", arguments='{"filepath":"a.py"}'),
            ToolCall(id="tc2", name="read_file", arguments='{"filepath":"b.py"}'),
        ]
    )
    mock.enqueue_response(content="Finished reading both files.")

    agent = BaseAgent(
        name="AsyncReader",
        role_prompt="reader",
        tools=[{"name": "read_file"}],
        tool_functions={"read_file": slow_read_file},
        provider=mock,
    )

    start = time.perf_counter()
    res = await agent.run_async("read files")
    elapsed = time.perf_counter() - start

    assert res == "Finished reading both files."
    # If run sequentially, would take >= 0.4s. If concurrent, ~0.2s.
    assert elapsed < (delay * 1.8)


@pytest.mark.asyncio
async def test_write_tools_serialized() -> None:
    """Non-readonly tools must execute sequentially."""
    order: list[str] = []

    def write_a(content: str) -> str:
        order.append("start_a")
        time.sleep(0.05)
        order.append("end_a")
        return "wrote a"

    def write_b(content: str) -> str:
        order.append("start_b")
        time.sleep(0.05)
        order.append("end_b")
        return "wrote b"

    mock = MockProvider()
    mock.enqueue_response(
        tool_calls=[
            ToolCall(id="tc1", name="write_a", arguments='{"content":"1"}'),
            ToolCall(id="tc2", name="write_b", arguments='{"content":"2"}'),
        ]
    )
    mock.enqueue_response(content="Done.")

    agent = BaseAgent(
        name="AsyncWriter",
        role_prompt="writer",
        tools=[{"name": "write_a"}, {"name": "write_b"}],
        tool_functions={"write_a": write_a, "write_b": write_b},
        provider=mock,
    )

    await agent.run_async("write files")
    assert order == ["start_a", "end_a", "start_b", "end_b"]
