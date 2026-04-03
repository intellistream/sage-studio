# Changelog

All notable changes to SAGE Studio will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## PyPI Verified Releases (`isage-studio`)

Source: `https://pypi.org/pypi/isage-studio/json` (checked on 2026-02-14, UTC).

- `0.2.1.1` — 2026-02-12T15:01:46Z
- `0.2.1.0` — 2026-02-11T05:43:59Z
- `0.2.0.7` — 2026-02-11T03:36:50Z
- `0.2.0.3` — 2026-02-10T09:35:10Z
- `0.2.0.2` — 2026-02-07T15:40:18Z
- `0.2.0.1` — 2026-01-07T16:58:48Z
- `0.2.0.0` — 2026-01-05T16:47:01Z
- `0.2.3` — 2026-01-03T16:57:43Z

## [Unreleased]

### Changed
- Cleaned documentation references to align with changelog-centric policy.

### Removed
- Removed deprecated `docs/project-structure.md` document.

### Added
- CI/CD workflow for automated testing (`.github/workflows/ci-test.yml`)
  <!-- - Unit tests on Python 3.10 and 3.11 -->
  - Unit tests on Python 3.11
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
