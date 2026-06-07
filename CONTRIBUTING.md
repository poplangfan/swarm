# Contributing to Swarm

Thank you for your interest in contributing! This document outlines the process and guidelines.

## Development Setup

```bash
git clone https://github.com/your-org/swarm.git
cd swarm
python -m venv venv
source venv/bin/activate
pip install -e ".[dev]"
```

## Code Style

- Python 3.10+ with type hints
- Line length: 100 characters
- Follow existing patterns in the codebase
- Lint with ruff: `ruff check swarm/`

## Testing

```bash
# Run all tests
pytest tests/ -v

# With coverage
pytest tests/ -v --cov=swarm --cov-report=term

# Run specific test file
pytest tests/test_agent.py -v
```

Aim for 80%+ test coverage on new code.

## Commit Convention

We use conventional commits:

```
feat: add new feature
fix: fix bug description
docs: update documentation
test: add tests for X
refactor: restructure Y module
chore: update dependencies
```

## Pull Request Process

1. Fork the repository
2. Create a feature branch (`git checkout -b feat/amazing-feature`)
3. Write tests for your changes
4. Ensure all tests pass (`pytest tests/ -v`)
5. Lint your code (`ruff check swarm/`)
6. Commit with conventional commit messages
7. Push and create a Pull Request

## Project Structure

See the [Architecture Guide](docs/architecture.md) for a detailed walkthrough.

## Adding a New Tool

1. Create tool class in `swarm/tools/builtin/` or your plugin
2. Extend `ToolBase` with `name`, `description`, `parameters`
3. Implement `async def execute(self, args, ctx) -> str`
4. Register in `ToolRegistry`
5. Write tests

## Adding a New Skill

1. Create directory: `skills_builtin/skill-name/`
2. Create `SKILL.md` with YAML frontmatter
3. Write clear instructions and examples
4. Test by loading with `SkillsLoader`

## Code of Conduct

See [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md).

## Questions?

Open an issue or discussion on GitHub.
