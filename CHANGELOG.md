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

### Added
- `src/errors.py`: Custom exception hierarchy (`ConfigError`).
- `src/tools/scoped_tools.py`: Role-scoped write policy enforcement.
- `docs/SECURITY_FIXES.md`: Detailed security audit report with PoCs and verification steps.
- Comprehensive security regression test suite (41 tests, up from 5).
- Ruff configuration in `pyproject.toml` with strict import and formatting rules.
