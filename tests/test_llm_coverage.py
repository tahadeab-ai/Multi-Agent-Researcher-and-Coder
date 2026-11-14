"""Additional tests to reach >=75% coverage across src/llm (DoD #15)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from src.llm.ollama import OllamaProvider
from src.llm.openai import OpenAIProvider, _build_capabilities, _normalize_response
from src.llm.tracing import get_tracer


def test_tracing_hook() -> None:
    tracer = get_tracer()
    with tracer.span("test_span") as span:
        span.set_attribute("key", "val")
        assert span.name == "test_span"
        assert span.attributes["key"] == "val"


def test_openai_capabilities_flags() -> None:
    caps_o1 = _build_capabilities("o1")
    assert not caps_o1.supports_temperature
    assert caps_o1.supports_json_schema

    caps_mini = _build_capabilities("gpt-4o-mini")
    assert caps_mini.supports_temperature
    assert caps_mini.supports_json_schema


def test_openai_normalize_response() -> None:
    mock_resp = MagicMock()
    fn_mock = MagicMock()
    fn_mock.name = "fn"
    fn_mock.arguments = '{"x": 1}'
    tc_mock = MagicMock(id="call_1", function=fn_mock)
    mock_resp.choices = [
        MagicMock(
            message=MagicMock(
                content="test content",
                tool_calls=[tc_mock],
            )
        )
    ]
    mock_resp.usage = MagicMock(prompt_tokens=10, completion_tokens=20, total_tokens=30)

    norm = _normalize_response(mock_resp, "gpt-4o-mini")
    assert norm.content == "test content"
    assert len(norm.tool_calls) == 1
    assert norm.tool_calls[0].name == "fn"
    assert norm.usage.total_tokens == 30
    assert norm.cost_estimate_usd is not None


def test_openai_provider_generate(monkeypatch: pytest.MonkeyPatch) -> None:
    provider = OpenAIProvider(model="gpt-4o-mini", api_key="sk-fake")
    mock_create = MagicMock()
    mock_create.return_value = MagicMock(
        choices=[MagicMock(message=MagicMock(content="hello", tool_calls=None))],
        usage=MagicMock(prompt_tokens=5, completion_tokens=5, total_tokens=10),
    )
    monkeypatch.setattr(provider._sync_client.chat.completions, "create", mock_create)

    res = provider.generate(messages=[{"role": "user", "content": "hi"}], temperature=0.7)
    assert res.content == "hello"
    mock_create.assert_called_once()


@pytest.mark.asyncio
async def test_openai_provider_agenerate(monkeypatch: pytest.MonkeyPatch) -> None:
    provider = OpenAIProvider(model="gpt-4o-mini", api_key="sk-fake")
    mock_acreate = AsyncMock()
    mock_acreate.return_value = MagicMock(
        choices=[MagicMock(message=MagicMock(content="hello async", tool_calls=None))],
        usage=MagicMock(prompt_tokens=5, completion_tokens=5, total_tokens=10),
    )
    monkeypatch.setattr(provider._async_client.chat.completions, "create", mock_acreate)

    res = await provider.agenerate(messages=[{"role": "user", "content": "hi"}])
    assert res.content == "hello async"
    mock_acreate.assert_called_once()


def test_ollama_provider_generate_agenerate(monkeypatch: pytest.MonkeyPatch) -> None:
    ollama = OllamaProvider(model="llama3", _json_schema_capable=True)
    monkeypatch.setattr(
        ollama._inner,
        "generate",
        lambda *args, **kwargs: MagicMock(content="ollama sync"),
    )
    monkeypatch.setattr(
        ollama._inner,
        "agenerate",
        AsyncMock(return_value=MagicMock(content="ollama async")),
    )

    res = ollama.generate(messages=[{"role": "user", "content": "hi"}])
    assert res.content == "ollama sync"


def test_anthropic_conversion_and_normalization(monkeypatch: pytest.MonkeyPatch) -> None:
    from src.llm import anthropic as ant_mod

    # Mock anthropic module
    mock_anthropic = MagicMock()
    monkeypatch.setattr(ant_mod, "_require_anthropic", lambda: mock_anthropic)

    provider = ant_mod.AnthropicProvider(model="claude-3-5-sonnet-20241022", api_key="sk-ant")

    # Test message conversion
    sys_prompt, turns = ant_mod._convert_messages_to_anthropic(
        [
            {"role": "system", "content": "system prompt"},
            {"role": "user", "content": "user query"},
            {"role": "tool", "tool_call_id": "tid", "content": "tool output"},
        ]
    )
    assert sys_prompt == "system prompt"
    assert len(turns) == 2
    assert turns[0]["role"] == "user"
    assert turns[1]["content"][0]["type"] == "tool_result"

    # Test tools conversion
    tools = provider._convert_tools(
        [
            {
                "type": "function",
                "function": {
                    "name": "calc",
                    "description": "calc desc",
                    "parameters": {"type": "object"},
                },
            }
        ]
    )
    assert len(tools) == 1
    assert tools[0]["name"] == "calc"

    # Test response normalization
    mock_resp = MagicMock()
    block_tool = MagicMock(type="tool_use", id="tuid", input={"expr": "1+1"})
    block_tool.name = "calc"
    mock_resp.content = [
        MagicMock(type="text", text="response text"),
        block_tool,
    ]
    mock_resp.usage = MagicMock(input_tokens=100, output_tokens=50)

    norm = provider._normalize(mock_resp)
    assert norm.content == "response text"
    assert len(norm.tool_calls) == 1
    assert norm.tool_calls[0].name == "calc"
    assert norm.usage.total_tokens == 150
