# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.1] - 2026-11-13

### Security
- **F1**: Fixed path traversal prefix collision vulnerability in `_resolve_safe_path` using `Path.is_relative_to` and upfront rejection of absolute paths.
- **F2**: Hardened `run_pytest` to route test paths through `_resolve_safe_path`, preventing sandbox escape via absolute paths.
- **F3**: Isolated subprocess execution in `shell_tools.py` with an explicit environment allowlist (preventing leak of API keys such as `OPENAI_API_KEY`), dedicated process groups, and configurable timeouts.
- **F4**: Implemented tool-layer role-based write authorization (`WritePolicy`, `make_scoped_write_file`). The Coder Agent cannot modify files in `tests/`, and the Tester Agent cannot modify files outside `tests/`.
- **F5**: Added fail-fast configuration validation (`ConfigError`) on startup for providers, removing vulnerable dummy API keys and rejecting unsupported providers with helpful diagnostics.
- **F12**: Fixed Windows NTFS `WritePolicy` alias bypass (residual F4) by enforcing policy against canonical resolved paths with `os.path.normcase` case-folding, 8.3 alias pattern denial, and redirecting `TEMP`/`TMP` to `workspace/.tmp`. *(Note: Originally numbered F6 in v0.1.1 release tag, subsequently renamed F12 per finding numbering rules to avoid collision with baseline F6 duplicate test run).*

### Added
- `src/errors.py`: Custom exception hierarchy (`ConfigError`).
- `src/tools/scoped_tools.py`: Role-scoped write policy enforcement.
- `docs/SECURITY_FIXES.md`: Detailed security audit report with PoCs and verification steps.
- `docs/reports/phase0-red-green.md`: Red-to-green empirical regression report on baseline `34edb31`.
- Comprehensive security regression test suite (44 tests, up from 5).
- Cross-platform process tree termination using `psutil` (Windows hybrid kill path).
- Per-run isolated workspace directory under `sandbox/runs/<uuid>/` with `sandbox/LATEST` pointer.
- `AgentState.run_dir` persistence and CLI execution summary table display.

### Fixed
- Restored quality gate integrity (R1): removed global lint ignores, restored line-length 100, and scoped per-file-ignores strictly to pre-existing modules with TODO annotations.
