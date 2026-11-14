# PHOENIX Phase 1 — Evidence Pack (E1–E8)

Date: 2026-11-14  
Branch: `phase/1-reliability`  
Target PR: [#2: Phase 1: Core Reliability (T1.1–T1.9)](https://github.com/tahadeab-ai/Multi-Agent-Researcher-and-Coder/pull/2)  
CI Run: [43572533111](https://github.com/tahadeab-ai/Multi-Agent-Researcher-and-Coder/actions/runs/43572533111) (push) and [43572538878](https://github.com/tahadeab-ai/Multi-Agent-Researcher-and-Coder/actions/runs/43572538878) (PR #2) — **4/4 Matrix Jobs Green**

---

## E1 — Scoped-Tools Matcher & Policy Hardening (N8)

### Explicit Status
**Deviation Logged & Phase 0 Matcher Retained**:  
The scoped-tools write policy matcher was **not** switched to bare `fnmatch.fnmatchcase`. Switching to `fnmatchcase` would alter the exact directory prefix semantics required for recursive glob patterns (`tests/**` vs `tests/*`) and NTFS alias bypass defenses established in Phase 0. The Phase 0 matcher implementation in `src/tools/scoped_tools.py` was retained intact with its pinned semantics.

### Pinned Implementation (`src/tools/scoped_tools.py`)
```python
class WritePolicy:
    def is_allowed(self, filepath: str) -> bool:
        normalized = os.path.normcase(filepath).replace("\\", "/")
        path = PurePosixPath(normalized)

        if self.deny_patterns:
            for pattern in self.deny_patterns:
                p_norm = os.path.normcase(pattern).replace("\\", "/")
                if path.match(p_norm) or self._match_prefix(normalized, p_norm):
                    return False

        if self.allow_patterns:
            return any(
                path.match(os.path.normcase(p).replace("\\", "/"))
                or self._match_prefix(normalized, os.path.normcase(p).replace("\\", "/"))
                for p in self.allow_patterns
            )

        return True

    @staticmethod
    def _match_prefix(filepath: str, pattern: str) -> bool:
        if "**" in pattern:
            prefix = pattern.split("**")[0]
            return filepath.startswith(prefix)
        if "*" in pattern:
            prefix = pattern.rsplit("/", 1)[0] + "/" if "/" in pattern else ""
            return bool(prefix) and filepath.startswith(prefix)
        return False
```

### Passing Tests on Python 3.10–3.13 Matrix
All 12 scoped-tools security tests pass in `tests/test_scoped_tools.py`:
1. `test_coder_cannot_write_to_tests`
2. `test_tester_cannot_write_outside_tests`
3. `test_prefix_collision_safety` (e.g., `tests_evil/test.py` is allowed for Coder, denied for Tester)
4. `test_coder_policy_blocks_ntfs_alias_casing` (`Tests/test_solution.py`)
5. `test_coder_policy_blocks_ntfs_alias_trailing_dot` (`tests ./test_solution.py`)
6. `test_coder_policy_blocks_ntfs_alias_short_name` (`TESTS~1/test_solution.py`)
7. `test_coder_policy_blocks_traversal_normalization` (`src/../tests/test_solution.py`)
8. `test_scoped_write_blocks_windows_alias_before_creation`
9. `test_nested_subdirectories_outside_tests_allowed_for_coder`
10. `test_nested_subdirectories_inside_tests_blocked_for_coder`
11. `test_empty_policy_allows_all`
12. `test_tester_denied_root_file`

---

## E2 — Retry Reality & SDK Exception Translation

### Adapter-Boundary Exception Translation
In `src/llm/retry.py`, `is_retryable_exception` directly intercepts SDK-specific exceptions at the adapter/runtime boundary and maps them to retry decisions under the A1 taxonomy:
- `openai.RateLimitError` / `anthropic.RateLimitError` (HTTP 429) -> Retry
- `openai.APITimeoutError` / `anthropic.APITimeoutError` -> Retry
- `openai.APIConnectionError` / `anthropic.APIConnectionError` -> Retry
- `openai.InternalServerError` / `anthropic.InternalServerError` -> Retry
- `openai.APIStatusError` / `anthropic.APIStatusError` with `status_code >= 500` -> Retry
- `4xx` (400, 401, 403, 404) -> Fail fast (Never retry)

### Real `openai.RateLimitError` Test
Test: `tests/test_resilience.py::test_real_openai_rate_limit_error_with_retry_after`
```python
def test_real_openai_rate_limit_error_with_retry_after() -> None:
    """E2: Injected real openai.RateLimitError with Retry-After header is honored by custom wait."""
    from unittest.mock import MagicMock
    import openai

    mock_response = MagicMock()
    mock_response.headers = {"retry-after": "7.5"}
    mock_response.status_code = 429

    real_rate_limit_err = openai.RateLimitError(
        message="Rate limit exceeded",
        response=mock_response,
        body={"error": {"message": "Rate limit exceeded"}},
    )

    sleeps: list[float] = []
    mock = MockProvider()
    mock.enqueue_error(real_rate_limit_err)
    mock.enqueue_response(content="Recovered after real openai RateLimitError!")

    agent = BaseAgent(
        name="TestAgent",
        role_prompt="test",
        provider=mock,
        sleep_func=lambda s: sleeps.append(s),
    )

    result = agent.run("test openai retry-after")
    assert result == "Recovered after real openai RateLimitError!"
    assert len(sleeps) == 1
    assert sleeps[0] == pytest.approx(7.5)
```

---

## E3 — N1 Boundary: ToolError Wrapping & ReAct Loop Recovery

### Dispatch Boundary (`src/agents/base.py`)
```python
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
```

### Observation Conversion in ReAct Loop
When `ToolError` is raised, `_execute_single_tool` intercepts it and returns a JSON error string, which is appended to the message history with `role="tool"`:
```python
except ToolError as tool_err:
    return tc.id, fn_name, json.dumps({"error": str(tool_err)})
```

### Test: Tool Raises `ValueError` and Run Completes
Test: `tests/test_resilience.py::test_tool_value_error_wrapped_and_run_completes`
```python
def test_tool_value_error_wrapped_and_run_completes() -> None:
    """E3: Tool raising ValueError is wrapped into ToolError, converted to observation,
    and run completes.
    """
    def value_error_tool() -> str:
        raise ValueError("Invalid parameter value encountered")

    mock = MockProvider()
    mock.enqueue_response(tool_calls=[ToolCall(id="tc_val", name="val_tool", arguments="{}")])
    mock.enqueue_response(content="Corrected after ValueError observation.")

    agent = BaseAgent(
        name="TestAgent",
        role_prompt="test",
        tools=[{"name": "val_tool"}],
        tool_functions={"val_tool": value_error_tool},
        provider=mock,
    )

    output = agent.run("execute val_tool")
    assert output == "Corrected after ValueError observation."

    call2_messages = mock.calls[1].messages
    tool_msg = next((m for m in call2_messages if m.get("role") == "tool"), None)
    assert tool_msg is not None
    assert "Tool 'val_tool' failed: Invalid parameter value encountered" in tool_msg["content"]
```

---

## E4 — Coverage Gate CI Step

The CI workflow `.github/workflows/ci.yml` strictly enforces `--cov-fail-under=75`:
```yaml
      - name: Run Test Suite with Coverage Gate (DoD 15)
        run: |
          source .venv/bin/activate
          pytest -v tests/ --cov=src/llm --cov-report=term-missing --cov-fail-under=75
```
Actual coverage on `src/llm/`: **79.73%** (exceeds the 75% threshold).

---

## E5 — Complete DoD Matrix & Test Suite Verification

### Full DoD Status Table

| Gate | Requirement | Status | Evidence |
|:---|:---|:---:|:---|
| **DoD 10** | `LLMProvider` Protocol & adapters (OpenAI, Anthropic, Ollama, Mock) | ✅ PASS | `tests/test_llm_provider.py` (20 passed) |
| **DoD 11** | Resilience: retries with jitter & `Retry-After`, `ToolError` in-turn recovery, `BLE001` eliminated | ✅ PASS | `tests/test_resilience.py` (11 passed) |
| **DoD 12** | Structured outputs via `parse` + degraded plan fallback | ✅ PASS | `tests/test_structured_and_budget.py` (2 passed) |
| **DoD 13** | Budget enforcement & tool output truncation | ✅ PASS | `tests/test_structured_and_budget.py` (3 passed) |
| **DoD 14** | Atomic persistence, `schema_version` guard & mid-run resume | ✅ PASS | `tests/test_resume_and_authority.py` (4 passed) |
| **DoD 15** | Code coverage on `src/llm/` ≥ 75% | ✅ PASS | **79.73%** (`--cov-fail-under=75`) |
| **DoD 16** | All 4 CI matrix jobs (Python 3.10, 3.11, 3.12, 3.13) green | ✅ PASS | CI Runs 43572533111 & 43572538878 |
| **DoD-Offline** | Offline guard self-test (`test_offline_guard_blocks_network`, `test_async_loop_works_under_guard`) | ✅ PASS | `tests/test_offline_guard.py` (2 passed) |
| **DoD-Async** | Async agent loop concurrency and serialization | ✅ PASS | `tests/test_async_tools.py` (2 passed) |
| **DoD-Rename** | Finding collision resolved (NTFS bypass renamed to F12) | ✅ PASS | `docs/SECURITY_FIXES.md`, `CHANGELOG.md` |
| **DoD-Sync** | `.env.example` & `README.md` accuracy | ✅ PASS | Reviewed and synchronized |

### Total Test Count
- **Total Tests:** **98 passed** across 12 test files:
  - `tests/test_agent_state.py`: 2
  - `tests/test_async_tools.py`: 2
  - `tests/test_config_validation.py`: 11
  - `tests/test_file_tools.py`: 12
  - `tests/test_llm_coverage.py`: 7
  - `tests/test_llm_provider.py`: 20
  - `tests/test_offline_guard.py`: 2
  - `tests/test_resilience.py`: 11
  - `tests/test_resume_and_authority.py`: 4
  - `tests/test_scoped_tools.py`: 12
  - `tests/test_shell_security.py`: 10
  - `tests/test_structured_and_budget.py`: 5

### Phase 0 Security Suite Verification
- `tests/test_file_tools.py`: 12 tests passed, **0 lines modified** from Phase 0.
- `tests/test_shell_security.py`: 10 tests passed, **0 lines modified** from Phase 0.
- `tests/test_scoped_tools.py`: 12 tests passed, **0 lines modified** from Phase 0.
- `tests/test_agent_state.py`: 2 tests passed. Minor type annotation added (`-> None`) and `assert state.plan is not None` guard for strict mypy compliance (G1 justified).

---

## E6 — Consistency & Architecture Verification

### ConfigError vs ConfigurationError
Reconciled in `src/errors.py`:
```python
class ConfigError(PhoenixError):
    """Raised when application configuration is invalid or incomplete."""

# Canonical alias for ConfigError per ADR & design documentation
ConfigurationError = ConfigError
```
Both `ConfigError` and `ConfigurationError` resolve to the same canonical type, ensuring callers and resume handlers succeed regardless of import name.

### Pytest Serialization
Pytest is executed by the graph deterministically after code generation (`graph._execute_pytest`). `run_pytest` is marked in `READ_ONLY_TOOLS = frozenset({"read_file", "list_directory"})` as **excluded**, meaning any agent tool calls to execute shell commands are strictly serialized, never concurrent.

### Sync `generate()` Bridge
In `src/llm/openai.py`, synchronous `generate()` uses the native synchronous OpenAI client (`self._sync_client.chat.completions.create` / `.parse`), avoiding nested `asyncio.run()` or event loop corruption.

---

## E7 — Honesty & Fact Verification

### LiteLLM Footprint Measurement
Measured live via `pip install --dry-run litellm` on Python 3.11:
- **Date:** 2026-11-14
- **Transitive Dependency Count:** **55 packages** (including `tokenizers`, `huggingface-hub`, `multidict`, `yarl`, `aiohttp`, `rpds-py`, `referencing`, `jsonschema-specifications`, `jinja2`, `fastuuid`).
- ADR statement updated: The footprint assertion is an empirical fact: LiteLLM resolves 55 packages versus our zero required runtime dependencies beyond `openai`.

### Anthropic Qualification
- **Status:** Implemented + mock-tested via `tests/test_llm_provider.py` and `tests/test_llm_coverage.py`.
- **Live Smoke Test:** Pending live user-provided API credentials.

---

## E8 — Housekeeping

- Remote branch `phase/0-security-hotfix`: Deleted from origin (merge commit `a7655d1` preserved on `main`).
- PR #2 body: Updated with exact test numbers (98 passed, 79.73% coverage, 4/4 matrix jobs green).
- DoD numbering: Reconciled with `docs/plan/phase1-plan.md` (DoD 10–16).
