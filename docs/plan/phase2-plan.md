# PHOENIX Phase 2 — Advanced Orchestration: Architecture & Implementation Plan

> [!IMPORTANT]
> **Status:** AWAITING PLAN REVIEW (PLANNING ONLY). Zero implementation code generated.
> **Target Branch:** `phase/2-orchestration` (branched from `v0.2.0` on `main`).
> **Prerequisites:** Phase 1 merged via PR #2 (`8ca008c`), tagged `v0.2.0`, CI 4/4 green across Python 3.10–3.13.

---

## 1. Design Questions (Q1–Q7) & Architectural Solutions

### Q1 — Single Source of Truth: State Persistence & LangGraph Checkpointer
**Problem:** Risk of dual persistence split-brain if LangGraph checkpointers and the custom atomic `state.json` write to separate locations or drift in schema.
**Solution:**
- **Single Source of Truth:** `sandbox/runs/<run_id>/state.json` remains the authoritative serialization ledger.
- **LangGraph Checkpointer Adapter:** Rather than introducing an opaque SQLite or memory checkpointer, implement a custom LangGraph `BaseCheckpointSaver` adapter (`PhoenixFileSaver`) that directly serializes and deserializes `AgentState` to/from `state.json` using the verified Phase 1 atomic replacement (`state.json.tmp.<uuid>` -> `state.json`).
- **Schema Migration Policy:**
  - `schema_version` is stored at the root of `state.json` (currently `1`, bumping to `2` for Phase 2).
  - On `--resume <run_id>`: if `stored_version == CURRENT_SCHEMA_VERSION`, load state directly. If `stored_version < CURRENT_SCHEMA_VERSION`, execute an explicit forward migration function (`migrate_v1_to_v2(state_dict)`) with validation.
  - If `stored_version > CURRENT_SCHEMA_VERSION` or unrecognizable, fail fast by raising `ConfigError` / `ConfigurationError`. Never permit silent unvalidated resume.

---

### Q2 — MCP Tool Integration & Sandbox Guardrails
**Problem:** Standard Model Context Protocol (MCP) filesystem or shell servers execute arbitrary host operations, which could bypass F1 (path traversal), F2 (run_pytest escape), F3 (env leakage), F4/F12 (role-scoped write policies), and NT-short-name mitigations.
**Solution:**
- **Strict In-Process Guard Interceptor:** All MCP tools exposed to agents must be registered through an adapter proxy (`GuardedMCPClient`).
- **Policy Enforcement:**
  - File operations requested through MCP protocol messages are routed directly through `_resolve_safe_path(filepath)` and checked against the active agent's `WritePolicy` (`CODER_POLICY` vs `TESTER_POLICY`).
  - Absolute paths, traversal sequences (`../`), and NTFS short-name aliases (`TESTS~1`) are intercepted and rejected at the proxy layer with a structured `ToolError` before any IPC dispatch occurs.
  - Subprocess execution requested via MCP is executed strictly within `_make_sandbox_env(workspace)` with timeout and process-group isolation identical to `execute_python`.

---

### Q3 — Researcher Agent & Graceful Offline Degradation
**Problem:** The repository is titled "Multi-Agent-Researcher-and-Coder", but no researcher agent exists. Integrating real research capabilities while preserving deterministic offline unit tests and CI network guards requires a robust offline degradation strategy.
**Solution:**
- **Role & Capabilities:**
  - Add `ResearcherAgent` to `src/agents/researcher.py` inheriting from `BaseAgent`.
  - Operates ahead of `SupervisorAgent` (or invoked by `SupervisorAgent`) to analyze existing codebase context, external API schemas, documentation, and error traces.
  - Output schema: `ResearchBrief` (Pydantic model containing `problem_statement`, `constraints`, `relevant_files`, `recommended_libraries`, and `key_findings`).
- **Offline Degradation Mechanism:**
  - Researcher tools: `local_code_search`, `read_docs`, `web_search` (lazy-imported / optional).
  - When outbound network access is unavailable (e.g. unit tests under the N2 socket guard or disconnected environments), `web_search` detects network prohibition, logs a structured warning (`researcher_offline_degradation`), and falls back to local workspace inspection and existing contextual files without failing the run.
  - The resulting `ResearchBrief` sets `is_offline_degraded = True` and documents that web retrieval was skipped.

---

### Q4 — Self-Healing Memory & Non-Degrading Auto-Revert
**Problem:** Naive while-loop healing can introduce regressions, overwrite working code with worse attempts, or allow Coder/Tester role boundaries to blur.
**Solution:**
- **Per-Run Git Checkpoints (`run_dir/.git`):**
  - Graph initializes an isolated git repository within `run_dir` (completely independent of the host repository).
  - Every healing cycle creates a commit: `cycle-<N>-attempt` with author `CoderAgent <coder@phoenix>`.
- **Apply-Patch Tool:**
  - Instead of re-writing entire multi-thousand-line files, provide an `apply_patch` unified diff tool restricted by `WritePolicy`.
- **Auto-Revert on Failing-Test Regression:**
  - Graph records test failure count before and after each healing turn ($F_{pre}$ and $F_{post}$).
  - If $F_{post} > F_{pre}$ (new tests broke or regressions introduced), the graph executes `git reset --hard HEAD~1`, restoring the previous state, records the failed diff in `AgentState.healing_history`, and feeds the regression trace back to the Coder with an explicit warning.
- **Strict Role Boundaries:**
  - `TesterAgent` is forbidden from touching implementation code.
  - `CoderAgent` is forbidden from touching tests or altering `pytest` configs.

---

### Q5 — Multi-Tier Verification Gates on Generated Code
**Problem:** Relying solely on `pytest` allows syntactically invalid, badly formatted, or untyped code to be accepted as working.
**Solution:**
- **Graph-Owned Multi-Tier Gate:**
  Before declaring a healing cycle or run successful, the graph runs a deterministic three-stage verification pipeline:
  1. **Syntax & Lint Gate (`ruff check <workspace>`):** Confirms no syntax errors or undeclared identifiers.
  2. **Type Check Gate (`mypy <workspace>`):** Spot-checks generated implementation files against basic typing sanity.
  3. **Deterministic Test Execution (`run_pytest`):** Graph invokes `run_pytest` once; parses stdout, stderr, and exit codes (mapping code 5 to FAIL per T1.6).
- If any gate fails, the failure details are structured into the healing context for the next cycle.

---

### Q6 — Human-In-The-Loop (HITL) Interrupt Point
**Problem:** Fully autonomous planning may diverge on ambiguous prompts or violate safety assumptions before expensive or destructive code generation begins.
**Solution:**
- **Plan Review Interrupt:**
  - After `SupervisorAgent` generates `TaskPlan` (and optional `ResearchBrief`), the graph checks `settings.hitl_plan_approval`.
  - In CLI interactive mode, the plan is rendered in a Rich table showing each planned step, target files, and architecture notes.
  - The user can select `[A] Approve`, `[M] Modify prompt`, or `[R] Reject`.
  - If approved, graph execution continues. If rejected or terminated, state is saved atomically with `status="awaiting_approval"`, allowing resumption later via `--resume <run_id>`.
- **Process Concurrency Architecture:**
  - Single-run-per-process remains the validated baseline. A clear `RunContext` dependency-injection model is designed for `MultiAgentGraph` to allow future thread-safe concurrent execution without global `settings.workspace_dir` pollution.

---

### Q7 — Evals Baseline Hook for Phase 4
**Problem:** Need a clean interface to benchmark agent performance (Pass@k, token efficiency, healing rate) without coupling live benchmark suites into core orchestration.
**Solution:**
- Add `src/evals/` interface:
  - `EvalMetric`: dataclass capturing `task_id`, `tokens_used`, `cost_usd`, `healing_cycles_used`, `tests_passed`, `wall_clock_seconds`, `status`.
  - Graph exposes `get_run_metrics() -> EvalMetric` for automated collection.
  - Offline eval runner harness prepared to execute against standard offline programming benchmarks (e.g., HumanEval subset) in Phase 4.

---

## 2. Phase 2 Task Breakdown & Verification Gates

| Task | Title | Deliverables | Verification Gate |
|:---|:---|:---|:---|
| **T2.1** | LangGraph Integration & File Checkpointer | `src/graph.py` refactored to LangGraph state machine; `PhoenixFileSaver` checkpointer adapter; `schema_version = 2` | `test_langgraph_checkpoint_roundtrip`, `test_state_schema_migration_v1_to_v2` |
| **T2.2** | Researcher Agent (`src/agents/researcher.py`) | `ResearchBrief` schema; offline search fallback; contextual file indexing | `test_researcher_offline_fallback`, `test_research_brief_generation` |
| **T2.3** | Self-Healing Memory & Auto-Revert | Sandbox git tracking; `apply_patch` tool; regression detection & revert | `test_auto_revert_on_regression`, `test_healing_history_tracking` |
| **T2.4** | Multi-Tier Verification Pipeline | Graph executes ruff + mypy + pytest on generated code | `test_lint_failure_triggers_healing`, `test_pytest_authority_preserved` |
| **T2.5** | HITL Plan Approval & CLI Interface | Interactive plan review interrupt; resume from approval state | `test_hitl_approval_flow`, `test_hitl_rejection_halts_cleanly` |
| **T2.6** | Guarded MCP Adapter | MCP protocol client wrapper with `WritePolicy` & sandbox traversal protection | `test_mcp_traversal_blocked`, `test_mcp_role_policy_enforced` |
| **T2.7** | Evals Baseline Hook | `EvalMetric` schema and graph metric extraction hook | `test_eval_metrics_capture` |
| **T2.8** | Full Matrix CI & DoD Validation | All 4 matrix jobs green on Python 3.10–3.13; docs updated | CI matrix run green, coverage maintained ≥ 75% |

---

## 3. Definition of Done (DoD) Criteria for Phase 2
1. LangGraph State Machine orchestrates Researcher → Supervisor → Coder → Tester with non-branching deterministic paths.
2. Single source of truth preserved in `sandbox/runs/<run_id>/state.json` via `PhoenixFileSaver`.
3. Researcher agent gracefully degrades in offline mode with zero network calls under N2 guard.
4. Auto-revert proven to restore previous code state whenever a healing cycle increases failing test count.
5. All MCP file operations verified through `_resolve_safe_path` and `WritePolicy`.
6. Zero regression on all 98 existing Phase 0 & Phase 1 tests.
7. CI matrix (Python 3.10, 3.11, 3.12, 3.13) 4/4 green with strict mypy and ruff gates.
