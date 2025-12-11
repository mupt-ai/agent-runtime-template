# Agent Runtime Template

A template for creating agent runtimes with MCP (Model Context Protocol) server integration.

## Structure

```
agent-runtime-template/
├── src/
│   ├── __init__.py
│   ├── servers/           # Base MCP wrappers
│   │   └── __init__.py
│   ├── skills/            # Agent skills and capabilities
│   │   └── __init__.py
│   └── manager.py         # Agent runtime manager
├── workspace/             # Agent workspace directory
│   └── .gitkeep
├── .gitignore
├── pyproject.toml
├── README.md
└── LICENSE
```

## Installation

```bash
# Using uv (recommended)
uv sync

# Or using pip
pip install -e .
```

## Development

```bash
# Install with dev dependencies
uv sync --all-extras

# Run tests
pytest

# Format code
black src/
ruff check src/
```

## Usage

```python
from src.manager import AgentManager

manager = AgentManager()
manager.start()
```

## License

See LICENSE file for details.
