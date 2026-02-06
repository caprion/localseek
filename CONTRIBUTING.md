# Contributing to localseek

Thanks for your interest in contributing!

## Development Setup

```bash
# Clone the repo
git clone https://github.com/caprion/localseek.git
cd localseek

# Create virtual environment (optional but recommended)
python -m venv .venv
.venv\Scripts\activate  # Windows
# source .venv/bin/activate  # Linux/Mac

# Install in development mode with all dependencies
pip install -e ".[all]"

# Run tests
pytest
```

## Code Style

- Use type hints
- Keep functions small and focused
- Document public APIs with docstrings
- No external dependencies for core functionality

## Making Changes

1. Fork the repository
2. Create a feature branch: `git checkout -b feature/my-feature`
3. Make your changes
4. Run tests: `pytest`
5. Commit with a descriptive message
6. Push and open a Pull Request

## Architecture

See [ARCHITECTURE.md](ARCHITECTURE.md) for design decisions and system overview.

## Areas for Contribution

- **Tests** — We need more test coverage
- **Documentation** — Improve README, add examples
- **Performance** — Profile and optimize hot paths
- **Features** — Check TODO.md for open items

## Questions?

Open an issue for discussion before starting major work.
