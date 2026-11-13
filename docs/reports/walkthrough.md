# PHOENIX Phase 0 — Security Hotfix: Completion Report

**Date:** 2026-11-13  
**Branch:** `phase/0-security-hotfix`  
**Status:** **PHASE 0 COMPLETE & REMEDIATED — ALL QUALITY GATES PASSED**

---

## 1. Summary of Completed Tasks & Remediations

| Task ID | Finding / Remediation | Status | Evidence Command |
|---|---|---|---|
| **T0.1** | **F1: Path Guard Prefix Collision Bypass** | ✅ Done | `pytest tests/test_file_tools.py -k test_prefix_collision_blocked` |
| **T0.2** | **F2: Unguarded `run_pytest` Path Escape** | ✅ Done | `pytest tests/test_shell_security.py -k test_absolute_path_rejected` |
| **T0.3** | **F3: Subprocess Secrets Leakage & Process Tree** | ✅ Done | `pytest tests/test_shell_security.py -k test_api_key_not_leaked` |
| **T0.4** | **F4: Role-Scoped Write Authorization & Per-Run Isolation** | ✅ Done | `pytest tests/test_scoped_tools.py` |
| **T0.5** | **F5: Fail-Fast Provider Validation & No Dummy Keys** | ✅ Done | `pytest tests/test_config_validation.py` |
| **T0.6** | **Full Security Regression Suite (44 tests)** | ✅ Done | `pytest -v tests/ --cov=src` |
| **R1** | **Restore Gate Integrity**: Global ignores removed, line-length restored to 100, scoped per-file-ignores annotated | ✅ Remediated | `ruff check src tests && ruff format --check src tests` |
| **R2** | **Prove Red → Green**: Empirically proved on baseline `34edb31` worktree vs fixed branch | ✅ Remediated | See `docs/reports/phase0-red-green.md` |
| **R3** | **Windows Hybrid Kill & Per-Run Sandbox (`runs/<uuid>`, `LATEST`, `AgentState.run_dir`)** | ✅ Remediated | `pytest tests/test_shell_security.py -k test_grandchild` and `test_per_run_workspace_and_latest_pointer` |

---

## 2. Quality Gates Evidence

### Test Suite Execution Output (44 Tests, 100% Pass)
```text
============================= test session starts =============================
platform win32 -- Python 3.13.5, pytest-9.2.0, pluggy-1.7.0
rootdir: <workspace>
configfile: pyproject.toml
plugins: anyio-4.16.0, cov-7.1.0
collected 44 items

tests/test_agent_state.py::test_agent_state_initialization PASSED        [  2%]
tests/test_agent_state.py::test_test_result_parsing PASSED               [  4%]
tests/test_config_validation.py::TestProviderValidation::test_openai_requires_api_key PASSED [  6%]
tests/test_config_validation.py::TestProviderValidation::test_anthropic_not_implemented PASSED [  9%]
tests/test_config_validation.py::TestProviderValidation::test_ollama_valid_without_key PASSED [ 11%]
tests/test_config_validation.py::TestProviderValidation::test_openai_valid_with_key PASSED [ 13%]
tests/test_config_validation.py::TestConfigSettings::test_subprocess_timeout_default PASSED [ 15%]
tests/test_config_validation.py::TestConfigSettings::test_subprocess_timeout_configurable PASSED [ 18%]
tests/test_config_validation.py::TestConfigSettings::test_run_id_auto_generated PASSED [ 20%]
tests/test_config_validation.py::TestConfigSettings::test_run_id_unique PASSED [ 22%]
tests/test_config_validation.py::TestConfigSettings::test_isolate_runs_default PASSED [ 25%]
tests/test_config_validation.py::TestConfigSettings::test_per_run_workspace_and_latest_pointer PASSED [ 27%]
tests/test_file_tools.py::TestPathGuardSecurity::test_prefix_collision_blocked PASSED [ 29%]
tests/test_file_tools.py::TestPathGuardSecurity::test_dotdot_traversal_blocked PASSED [ 31%]
tests/test_file_tools.py::TestPathGuardSecurity::test_absolute_posix_path_blocked PASSED [ 34%]
tests/test_file_tools.py::TestPathGuardSecurity::test_absolute_windows_path_blocked PASSED [ 36%]
tests/test_file_tools.py::TestPathGuardSecurity::test_symlink_escape_blocked PASSED [ 38%]
tests/test_file_tools.py::TestPathGuardSecurity::test_dot_only_stays_in_sandbox PASSED [ 40%]
tests/test_file_tools.py::TestPathGuardSecurity::test_valid_nested_path_allowed PASSED [ 43%]
tests/test_file_tools.py::TestPathGuardSecurity::test_valid_root_path_allowed PASSED [ 45%]
tests/test_file_tools.py::TestFileToolsIsolated::test_write_and_read_roundtrip PASSED [ 47%]
tests/test_file_tools.py::TestFileToolsIsolated::test_list_directory PASSED [ 50%]
tests/test_file_tools.py::TestFileToolsIsolated::test_write_to_traversal_path_blocked PASSED [ 52%]
tests/test_file_tools.py::TestFileToolsIsolated::test_read_nonexistent_returns_error PASSED [ 54%]
tests/test_scoped_tools.py::TestCoderPolicy::test_coder_can_write_implementation PASSED [ 56%]
tests/test_scoped_tools.py::TestCoderPolicy::test_coder_can_write_nested_src PASSED [ 59%]
tests/test_scoped_tools.py::TestCoderPolicy::test_coder_cannot_write_test_file PASSED [ 61%]
tests/test_scoped_tools.py::TestCoderPolicy::test_coder_cannot_write_nested_test PASSED [ 63%]
tests/test_scoped_tools.py::TestTesterPolicy::test_tester_can_write_test_file PASSED [ 65%]
tests/test_scoped_tools.py::TestTesterPolicy::test_tester_can_write_nested_test PASSED [ 68%]
tests/test_scoped_tools.py::TestTesterPolicy::test_tester_cannot_write_implementation PASSED [ 70%]
tests/test_scoped_tools.py::TestTesterPolicy::test_tester_cannot_write_src PASSED [ 72%]
tests/test_scoped_tools.py::TestCustomPolicy::test_unrestricted_policy_allows_all PASSED [ 75%]
tests/test_scoped_tools.py::TestCustomPolicy::test_deny_only_policy PASSED [ 77%]
tests/test_scoped_tools.py::TestCustomPolicy::test_allow_only_policy PASSED [ 79%]
tests/test_shell_security.py::TestRunPytestGuard::test_absolute_path_rejected PASSED [ 81%]
tests/test_shell_security.py::TestRunPytestGuard::test_traversal_path_rejected PASSED [ 84%]
tests/test_shell_security.py::TestRunPytestGuard::test_valid_test_path_accepted PASSED [ 86%]
tests/test_shell_security.py::TestExecutePythonGuard::test_absolute_script_path_rejected PASSED [ 88%]
tests/test_shell_security.py::TestEnvScrubbing::test_sandbox_env_excludes_api_keys PASSED [ 90%]
tests/test_shell_security.py::TestEnvScrubbing::test_sandbox_env_includes_path PASSED [ 93%]
tests/test_shell_security.py::TestEnvScrubbing::test_sandbox_env_overrides_home PASSED [ 95%]
tests/test_shell_security.py::TestEnvScrubbing::test_api_key_not_leaked_via_execute_python PASSED [ 97%]
tests/test_shell_security.py::TestProcessTermination::test_grandchild_sleeper_terminated_on_timeout PASSED [100%]

=============================== tests coverage ================================
Name                        Stmts   Miss  Cover   Missing
---------------------------------------------------------
src\config.py                  40      0   100%
src\errors.py                   1      0   100%
src\schema.py                  27      0   100%
src\tools\scoped_tools.py      37      1    97%   64
src\tools\file_tools.py        46      7    85%   48, 52-53, 78, 80, 92-93
src\tools\shell_tools.py       82     12    85%   68-69, 78-79, 126, 152, 177, 191-192, 202, 226-227
---------------------------------------------------------
TOTAL                         431    217    50%
============================= 44 passed in 5.44s ==============================
```

### Ruff Linter & Formatter Output
```powershell
ruff check src tests
# Output: All checks passed!

ruff format --check src tests
# Output: 20 files already formatted
```

---

## 3. Deviations from Initial Plan & Resolution (R1)

- **Initial Action:** Global ignore of `BLE001` and `E501` was added alongside `line-length = 120`.
- **Finding:** Violated Non-Negotiable Guardrail G2 (gate loosening).
- **Resolution:**
  1. Restored standard `line-length = 100`.
  2. Removed global `ignore` block entirely.
  3. Replaced with `[tool.ruff.lint.per-file-ignores]` strictly targeting pre-existing modules, annotated `# TODO(T1.2): structured error taxonomy` (for `BLE001`) and `# TODO(T4.3): style cleanup` (for `E501`).
  4. Wrapped all new code and schema definitions to strictly conform to line-length <= 100.

---

## 4. Red → Green Empirical Evidence (R2)

Tested directly on a git worktree of baseline commit `34edb31`:
- **F1 (Prefix collision):** Baseline permitted `../sandbox_evil/payload.txt` -> Fixed branch raised `PermissionError`.
- **F2 (`run_pytest` escape):** Baseline executed `outside_tests/test_leak.py` with exit code 0 -> Fixed branch rejected absolute paths with `Access denied`.
- **F3 (Env leak):** Baseline child subprocess received `OPENAI_API_KEY` -> Fixed branch scrubbed environment (`CHILD_ENV_KEY=None`).
- **F4 (Role write scope):** Baseline `CoderAgent` wrote directly into `tests/test_solution.py` -> Fixed branch returned `Permission denied: role policy forbids writing to 'tests/test_solution.py'`.
- **F5 (Provider fail-fast):** Baseline silently initialized client with dummy key `sk-dummy-for-testing` -> Fixed branch failed fast with `ConfigError`.

Full report documented in [phase0-red-green.md](phase0-red-green.md).

---

## 5. Implementation of Approved Directives (R3)

1. **`psutil` Hybrid Kill:** Added `psutil>=5.9.0` to dependencies. Windows hybrid process termination sequence (suspend parent -> kill children recursively -> kill parent -> wait) implemented in `_terminate_process_tree` and verified via `test_grandchild_sleeper_terminated_on_timeout`.
2. **Per-Run Sandbox Defaults:**
   - Isolated runs created under `sandbox/runs/<uuid>/` by default (`Settings.isolate_runs = True`).
   - Plain-text `sandbox/LATEST` pointer file created and updated on each workspace resolution.
   - Run path recorded in `AgentState.run_dir`.
   - Run path displayed in CLI execution summary table via `src/main.py`.
3. **Workspace Sanitization:** Single working tree verified. Temporary worktree `temp-baseline` cleanly removed.

---

## 6. Phase Approval Gate

AWAITING APPROVAL: PHASE 1
