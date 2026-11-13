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
| **T0.6** | **Full Security Regression Suite (46 tests)** | ✅ Done | `pytest -v tests/ --cov=src` |
| **P0.1** | **F6: Windows NTFS WritePolicy Alias Bypass Patch** | ✅ Done | `pytest tests/test_scoped_tools.py -k test_coder_alias_bypass_blocked` |
| **R1** | **Restore Gate Integrity**: Global ignores removed, line-length restored to 100, scoped per-file-ignores annotated | ✅ Remediated | `ruff check src tests && ruff format --check src tests` |
| **R2** | **Prove Red → Green**: Empirically proved on baseline `34edb31` worktree vs fixed branch | ✅ Remediated | See `docs/reports/phase0-red-green.md` |
| **R3** | **Windows Hybrid Kill & Per-Run Sandbox (`runs/<uuid>`, `LATEST`, `AgentState.run_dir`)** | ✅ Remediated | `pytest tests/test_shell_security.py -k test_grandchild` and `test_per_run_workspace_and_latest_pointer` |

---

## 2. Quality Gates Evidence

### Test Suite Execution Output (46 Tests, 100% Pass)
```text
============================= test session starts =============================
platform win32 -- Python 3.13.5, pytest-9.2.0, pluggy-1.7.0
rootdir: <workspace>
configfile: pyproject.toml
plugins: anyio-4.16.0, cov-7.1.0
collected 46 items

=============================== tests coverage ================================
Name                        Stmts   Miss  Cover   Missing
---------------------------------------------------------
src\config.py                  40      0   100%
src\errors.py                   1      0   100%
src\schema.py                  27      0   100%
src\tools\scoped_tools.py      54      7    87%   71, 92-93, 98, 103, 107-108
src\tools\file_tools.py        52      8    85%   22, 54, 58-59, 84, 86, 98-99
src\tools\shell_tools.py       91     15    84%   73-75, 79-80, 89-90, 137, 163, 188, 202-203, 213, 237-238
---------------------------------------------------------
TOTAL                         463    227    51%
============================= 46 passed in 6.10s ==============================
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
