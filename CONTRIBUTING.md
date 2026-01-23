# Contributing to Speed Bump

Thank you for your interest in Speed Bump!

## Project Status

Speed Bump is a research tool for analysing Python performance in AI/ML workloads. Development is driven by practical benchmarking needs.

## How to Contribute

### Reporting Bugs

If you find a bug, please open an issue with:
- A clear, descriptive title
- Steps to reproduce the behaviour
- Expected vs actual behaviour
- Python version, OS, and architecture

### Suggesting Features

Feature requests are welcome! Please open an issue describing:
- The use case or problem you're trying to solve
- How the feature would work
- Any implementation considerations

### Pull Requests

Pull requests are welcome, especially for:
- Bug fixes
- Documentation improvements
- Test coverage
- Platform support (new architectures, Python versions)

Before submitting a large PR, consider opening an issue first to discuss the approach.

**PR Guidelines:**
- All tests must pass (`pytest`)
- Add tests for new functionality
- Run `ruff check src/ tests/` and `ruff format src/ tests/`
- Update documentation as needed
- Follow existing code style

## Development Setup

```bash
# Clone the repository
git clone https://github.com/alexturner/speed-bump.git
cd speed-bump

# Create a virtual environment (optional but recommended)
python3 -m venv .venv
source .venv/bin/activate

# Install in development mode with test dependencies
pip install -e .[dev]

# Run tests
pytest

# Run linter
ruff check src/ tests/
```

## Building Locally

```bash
# Build the C extension
pip install -e .

# Or build a wheel
pip install build
python -m build
```

## Questions?

Open an issue for questions about Speed Bump's design, implementation, or usage.

## Licence

By contributing, you agree that your contributions will be licensed under the same licence as the project (MIT).
