# Phase 0 Security Hotfix — Red → Green Verification Evidence

**Date:** 2026-11-13  
**Auditor:** PHOENIX Agent  
**Baseline Commit:** `34edb31` (origin/main)  
**Remediation Branch:** `phase/0-security-hotfix`  

---

## 1. Executive Summary

This report establishes empirical Proof-of-Concept (PoC) evidence demonstrating the vulnerability status on the baseline commit (`34edb31`) versus the hardened status on the Phase 0 remediation branch (`phase/0-security-hotfix`).

All five findings (F1–F5) were verified in a dedicated temporary git worktree at `34edb31` demonstrating exploitable (RED) failures, and subsequently re-evaluated on `phase/0-security-hotfix` confirming 100% remediation (GREEN).

---

## 2. Red → Green Evidence Matrix

| Finding | Vulnerability Description | Baseline Commit `34edb31` (RED) | Fixed Branch `phase/0-security-hotfix` (GREEN) |
|---|---|---|---|
| **F1** | Path prefix collision bypass (`startswith`) | **EXPLOITED**: Path traversal permitted escape to `../sandbox_evil/payload.txt` | **BLOCKED**: `PermissionError` raised via `Path.is_relative_to` check |
| **F2** | Unguarded `run_pytest` absolute path escape | **EXPLOITED**: Ran pytest on `/outside_tests/test_leak.py` returning exit 0 | **BLOCKED**: Rejected with `Access denied: Absolute path ... is not allowed` |
| **F3** | Subprocess environment secret inheritance | **EXPLOITED**: Child subprocess stdout leaked `OPENAI_API_KEY` | **BLOCKED**: Environment scrubbed to allowlist; `CHILD_ENV_KEY=None` |
| **F4** | CoderAgent unauthorized write to `tests/` | **EXPLOITED**: CoderAgent wrote into `tests/test_solution.py` with `success=True` | **BLOCKED**: `Permission denied: role policy forbids writing to 'tests/test_solution.py'` |
| **F5** | Provider misconfiguration silent fallback | **EXPLOITED**: Initialized client with dummy key `sk-dummy-for-testing` | **BLOCKED**: Failed fast at startup with explicit `ConfigError` |

---

## 3. Raw Execution Outputs

### Baseline (`34edb31`) Output [RED]
```text
F1 [RED - VULNERABLE]: _resolve_safe_path permitted escape -> <temp_dir>/baseline_f1/sandbox_evil/payload.txt
F2 [RED - VULNERABLE]: run_pytest executed test outside sandbox -> exit 0
F3 [RED - VULNERABLE]: Child subprocess received secret -> CHILD_ENV_KEY=sk-SUPER-SECRET-API-KEY-12345
F4 [RED - VULNERABLE]: CoderAgent wrote into tests/ without restriction -> success=True
F5 [RED - VULNERABLE]: BaseAgent silently initialized with dummy key -> client.api_key=sk-dummy-for-testing
```

### Remediation Branch (`phase/0-security-hotfix`) Output [GREEN]
```text
F1 [GREEN - BLOCKED]: PermissionError correctly raised -> Access denied: Path '../sandbox_evil/payload.txt' resolves to '<temp_dir>/check_f1/sandbox_evil/payload.txt' which escapes sandbox '<temp_dir>/check_f1/sandbox'.
F2 [GREEN - BLOCKED]: run_pytest blocked escape -> error: Access denied: Access denied: Absolute path '<temp_dir>/check_f2/outside_tests/test_leak.py' is not allowed. Use relative paths within sandbox '<temp_dir>/check_f2/sandbox'.
F3 [GREEN - BLOCKED]: Child subprocess scrubbed secret -> CHILD_ENV_KEY=None
F4 [GREEN - BLOCKED]: CoderAgent write to tests/ blocked -> Permission denied: role policy forbids writing to 'tests/test_solution.py'. This file is outside your allowed write scope.
F5 [GREEN - BLOCKED]: BaseAgent failed fast with ConfigError -> LLM_PROVIDER 'anthropic' is not yet implemented. Use 'openai' or 'ollama' instead. See https://github.com/tahadeab-ai/Multi-Agent-Researcher-and-Coder/issues for updates on Anthropic support.
```

---

## 4. Grandchild-Sleeper Process Termination Evidence (Windows Hybrid Kill Path)

Command executed on host Windows system:
```powershell
pytest -v tests/test_shell_security.py -k test_grandchild_sleeper_terminated_on_timeout
```

Output:
```text
============================= test session starts =============================
platform win32 -- Python 3.13.5, pytest-9.2.0, pluggy-1.7.0
rootdir: <workspace>
configfile: pyproject.toml
plugins: anyio-4.16.0, cov-7.1.0
collected 9 items / 8 deselected / 1 selected

tests/test_shell_security.py::TestProcessTermination::test_grandchild_sleeper_terminated_on_timeout PASSED [100%]

======================= 1 passed, 8 deselected in 3.25s =======================
```

**Sequence verified:**
1. Parent process spawns child process, which spawns background grandchild sleeper (`time.sleep(60)`).
2. Subprocess timeout fires after 2 seconds.
3. Windows hybrid termination sequence executes:
   - `psutil.Process(parent_pid).suspend()` stops spawning.
   - Recursive descendant collection collects child and grandchild PIDs.
   - `child.kill()` terminates child and grandchild.
   - `parent.kill()` terminates parent.
   - `psutil.wait_procs()` cleans up all processes.
4. Test confirms grandchild PID is no longer running (neither running nor orphan).
