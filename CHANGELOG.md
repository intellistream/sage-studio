# Changelog

All notable changes to SAGE Studio will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- CI/CD workflow for automated testing (`.github/workflows/ci-test.yml`)
  - Unit tests on Python 3.10 and 3.11
  - Integration tests with CPU backend
  - E2E tests for LLM integration
  - Code quality checks (Ruff, Mypy)
- Integration test for Studio LLM startup (`tests/integration/test_studio_llm_integration.py`)
  - Tests sageLLM CPU backend engine script generation
  - Validates script content and configuration
  - Checks Gateway detection logic
  - Supports environment variable configuration for CI
- Workflow documentation (`.github/workflows/README.md`)

### Changed
- Updated integration tests to use pytest markers (`@pytest.mark.integration`)
- Improved test organization and CI compatibility

### Fixed
- Test file path organization (moved to `tests/integration/`)

## [Previous Unreleased]

### Added
- Initial independent repository setup
- Extracted from main SAGE monorepo with full git history

### Changed
- Restructured as standalone package
- Updated dependencies to use published SAGE packages (isage-common, isage-llm-core, etc.)

### Documentation
- Added CONTRIBUTING.md
- Added LICENSE (MIT)
- Updated README.md for standalone usage

## [0.2.0] - 2026-01-08

### Repository Independence
- Separated from SAGE monorepo
- Maintains dependency on SAGE core packages via PyPI
- Full git history preserved from packages/sage-studio

---

For earlier changes, see the [SAGE main repository](https://github.com/intellistream/SAGE).
