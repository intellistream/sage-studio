# Contributing to SAGE Studio

Thank you for your interest in contributing to SAGE Studio!

## Development Setup

SAGE Studio is part of the SAGE ecosystem. For development:

1. **Clone the repository**:
```bash
git clone https://github.com/intellistream/sage-studio.git
cd sage-studio
```

2. **Install dependencies**:
```bash
pip install -e .
```

3. **Install SAGE core dependencies** (if needed):
```bash
pip install isage-common isagellm
```

## Architecture

SAGE Studio is built on top of SAGE's inference framework and follows the SAGE architecture:

- **Frontend**: React + TypeScript + Vite
- **Backend**: FastAPI (integrated with sage-llm-gateway)
- **Backend**: FastAPI (Studio backend + Gateway integration)
- **Integration**: Uses SAGE Control Plane for LLM orchestration

## Docs Consistency Checklist

When a PR changes startup chain, API routes, or runtime behavior, update docs in the same PR:

- [ ] `README.md` startup/port/dependency instructions are still correct
- [ ] `CONTRIBUTING.md` setup and testing commands match current implementation
- [ ] New or removed CLI options are documented

## Code Standards

- Follow SAGE's coding standards (see main SAGE repository)
- Use Ruff for linting and formatting
- Add tests for new features
- Update documentation

## Testing

```bash
# Run all tests
pytest tests/

# Run specific test suite
pytest tests/unit/
pytest tests/integration/
```

## Pull Request Process

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'feat: add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

## Commit Convention

We follow Conventional Commits:

- `feat:` - New feature
- `fix:` - Bug fix
- `docs:` - Documentation changes
- `refactor:` - Code refactoring
- `test:` - Test updates
- `chore:` - Maintenance tasks

## Community

- Main SAGE Repository: https://github.com/intellistream/SAGE
- Documentation: https://intellistream.github.io/sage-docs/
- Issues: https://github.com/intellistream/sage-studio/issues

## License

By contributing, you agree that your contributions will be licensed under the MIT License.
