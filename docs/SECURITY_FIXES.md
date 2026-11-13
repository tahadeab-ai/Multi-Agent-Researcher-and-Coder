# Security Hardening & Vulnerability Remediation Report

**Date:** 2026-11-13  
**Auditor:** PHOENIX Agent  
**Scope:** Phase 0 Security Hotfix  
**Status:** ALL FINDINGS RESOLVED (F1–F5)

---

## Executive Summary

A comprehensive security audit of the Multi-Agent Researcher and Coder prototype revealed **3 Critical** and **2 High** severity vulnerabilities enabling arbitrary code execution, complete sandbox escape, environment secrets leakage, and reward hacking.

All 5 findings were reproduced via live Proof-of-Concepts (PoCs), addressed via defense-in-depth remediations, and validated with 41 automated regression tests with 0 failures.

---

## Detailed Vulnerability Analysis & Proof of Concepts

### Finding F1 [CRITICAL] — Path Guard Prefix Collision Bypass

- **CWE:** CWE-22 (Improper Limitation of a Pathname to a Restricted Directory)
- **Location:** `src/tools/file_tools.py:_resolve_safe_path`
- **Root Cause:** Path containment was checked using `str(resolved).startswith(str(workspace))`. An attacker creating a path such as `../sandbox_evil/x` against a workspace at `/path/to/sandbox` resulted in `/path/to/sandbox_evil/x`, whose string representation started with `/path/to/sandbox`, bypassing the guard completely.

#### Before Remediation (PoC Execution)
```python
workspace = Path("C:/app/sandbox").resolve()
candidate = (workspace / "../sandbox_evil/payload.txt").resolve()
# Output:
# workspace: C:\app\sandbox
# resolved:  C:\app\sandbox_evil\payload.txt
# str(resolved).startswith(str(workspace)): True  <-- VULNERABLE
```

#### Remediation Applied
1. Immediate rejection of absolute path strings before joining.
2. Canonical resolution (`.resolve()`) to resolve all symlinks and `..` segments.
3. Strict containment verification using `Path.is_relative_to(workspace)`:
```python
if not resolved.is_relative_to(workspace):
    raise PermissionError(f"Access denied: Path '{filepath}' escapes sandbox.")
```

#### After Remediation (Verified)
```python
candidate.is_relative_to(workspace) # False -> PermissionError raised
```

---

### Finding F2 [CRITICAL] — Unguarded Shell Tool Path Escape

- **CWE:** CWE-73 (External Control of File Name or Path)
- **Location:** `src/tools/shell_tools.py:run_pytest`
- **Root Cause:** `run_pytest` computed `(workspace / test_path).resolve()` without calling `_resolve_safe_path`. An absolute `test_path` (e.g., `C:\Windows` or `/etc`) escaped the workspace entirely and allowed executing tests against arbitrary host directories.

#### Before Remediation (PoC Execution)
```python
workspace = Path("C:/app/sandbox").resolve()
target = (workspace / "/etc/passwd").resolve()
# Output: C:\etc\passwd (Completely outside sandbox, no guard invoked)
```

#### Remediation Applied
`run_pytest` now explicitly routes `test_path` through `_resolve_safe_path(test_path)` before any existence check or subprocess invocation.

---

### Finding F3 [CRITICAL] — Subprocess Secrets Leakage & Process Group Orphanage

- **CWE:** CWE-214 (Invocation of Process Using Visible Sensitive Information) / CWE-400 (Uncontrolled Resource Consumption)
- **Location:** `src/tools/shell_tools.py` (`run_pytest`, `execute_python`)
- **Root Cause:** Subprocesses executed via `subprocess.run` inherited the complete parent environment, exposing production API keys (`OPENAI_API_KEY`, `ANTHROPIC_API_KEY`) to untrusted generated code. Furthermore, timeouts terminated only the direct child process, leaving orphan grandchild processes running.

#### Before Remediation (PoC Execution)
```python
os.environ['OPENAI_API_KEY'] = 'sk-live-secret-key'
# Script inside sandbox executes:
# os.environ.get('OPENAI_API_KEY') -> 'sk-live-secret-key' (LEAKED)
```

#### Remediation Applied
1. **Environment Allowlist**: Subprocess environments are stripped down strictly to essential system variables (`PATH`, `PYTHONHASHSEED`, `LANG`, `SYSTEMROOT`, `TEMP`, `TMP`, `COMSPEC`). All API keys and secrets are scrubbed.
2. **Directory Isolation**: `HOME` and `USERPROFILE` are redirected to the workspace directory.
3. **Process-Group Termination**: Subprocesses are spawned in dedicated process groups (`CREATE_NEW_PROCESS_GROUP` on Windows, `start_new_session=True` on POSIX). On timeout, the entire process hierarchy is terminated.
4. **Configurable Timeouts**: Managed via `Settings.subprocess_timeout`.

---

### Finding F4 [HIGH] — Lack of Role Separation & Reward Hacking

- **CWE:** CWE-285 (Improper Authorization)
- **Location:** `src/agents/coder.py`, `src/agents/tester.py`
- **Root Cause:** Both Coder and Tester had unrestricted write access across the entire sandbox. A Coder failing tests could rewrite or delete test files to force a false "PASS" (reward hacking). Furthermore, runs shared a flat directory without isolation.

#### Remediation Applied
1. **Tool-Layer Policy Enforcement**: Introduced `src/tools/scoped_tools.py` with `WritePolicy`:
   - `CODER_POLICY`: Denies writes to `tests/*` and `tests/**`.
   - `TESTER_POLICY`: Allows writes exclusively to `tests/*` and `tests/**`.
2. **Per-Run Directory Support**: Added `Settings.run_id` and `Settings.get_run_workspace()` to isolate runs under `sandbox/runs/<uuid>/`.

---

### Finding F5 [HIGH] — Silent Provider Misconfiguration & Dummy Credential Masking

- **CWE:** CWE-392 (Missing Report of Error Condition)
- **Location:** `src/config.py`, `src/agents/base.py`
- **Root Cause:** Setting `llm_provider="anthropic"` was silently routed to the OpenAI client. Missing OpenAI keys fell back to a dummy string `"sk-dummy-for-testing"`, delaying failure until live API calls.

#### Remediation Applied
1. Introduced `src/errors.py:ConfigError`.
2. Added `Settings.validate_provider()` which enforces fail-fast checks at startup:
   - `provider="openai"` without key raises `ConfigError`.
   - `provider="anthropic"` raises explicit `ConfigError` ("not yet implemented").
3. Removed all dummy key fallbacks.

---

## Verification & Test Results

```
============================= test session starts =============================
platform win32 -- Python 3.13.5, pytest-9.2.0, pluggy-1.7.0
plugins: anyio-4.16.0, cov-7.1.0
collected 41 items

tests/test_agent_state.py (2 tests)                      PASSED
tests/test_config_validation.py (8 tests)               PASSED
tests/test_file_tools.py (12 tests)                     PASSED
tests/test_scoped_tools.py (11 tests)                   PASSED
tests/test_shell_security.py (8 tests)                  PASSED

============================== 41 passed in 3.06s =============================
```

- **Ruff Linter:** 0 errors
- **Ruff Formatter:** 0 errors
- **Security-Critical Test Coverage:**
  - `src/tools/scoped_tools.py`: 97%
  - `src/config.py`: 88%
  - `src/tools/file_tools.py`: 85%
  - `src/tools/shell_tools.py`: 74%
