# Agent Runtime Template

A template for creating agent runtimes with MCP (Model Context Protocol) server integration and **shared connections**.

## Features

- **Shared MCP Connections**: Multiple agents/code generators share connections instead of each creating their own
- **Connection Pooling**: Centralized `MCPConnectionPool` with reference counting
- **Server Registry**: Easy management of multiple MCP servers
- **Async Context Managers**: Clean resource management with `async with` support

## Structure

```
agent-runtime-template/
├── src/
│   ├── __init__.py           # Package exports
│   ├── connections.py        # MCPConnectionPool & MCPServerConfig
│   ├── servers/              # MCP server wrappers
│   │   └── __init__.py       # MCPServerWrapper & MCPServerRegistry
│   ├── skills/               # Agent skills and capabilities
│   │   └── __init__.py
│   └── manager.py            # AgentManager - main entry point
├── workspace/                # Agent workspace directory
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

### Basic Usage with AgentManager

```python
import asyncio
from src import AgentManager, MCPServerConfig

async def main():
    manager = AgentManager()

    # Add MCP servers
    manager.add_server(MCPServerConfig(
        name="filesystem",
        command="npx",
        args=["-y", "@modelcontextprotocol/server-filesystem", "/tmp"]
    ))

    manager.add_server(MCPServerConfig(
        name="github",
        command="npx",
        args=["-y", "@modelcontextprotocol/server-github"],
        env={"GITHUB_TOKEN": "your-token"}
    ))

    # Start the runtime - connections are shared!
    async with manager:
        # Get all available tools
        tools = await manager.get_all_tools()
        print(f"Available tools: {tools}")

        # Call a tool
        result = await manager.call_tool(
            "filesystem",
            "read_file",
            {"path": "/tmp/test.txt"}
        )

        # Get direct session access
        async with manager.get_session("filesystem") as session:
            resources = await session.list_resources()

asyncio.run(main())
```

### Using the Connection Pool Directly

```python
from src import MCPConnectionPool, MCPServerConfig

async def main():
    pool = MCPConnectionPool()

    # Add server configurations
    pool.add_server(MCPServerConfig(
        name="filesystem",
        command="npx",
        args=["-y", "@modelcontextprotocol/server-filesystem", "/tmp"]
    ))

    async with pool:
        # Multiple consumers can share the same connection
        async with pool.get_session("filesystem") as session1:
            async with pool.get_session("filesystem") as session2:
                # session1 and session2 share the same underlying connection
                tools1 = await session1.list_tools()
                tools2 = await session2.list_tools()
```

### Using the Global Pool

```python
from src import get_global_pool, MCPServerConfig

# Get the global pool singleton
pool = get_global_pool()
pool.add_server(MCPServerConfig(name="myserver", command="my-mcp-server"))

# Later, anywhere in your code:
pool = get_global_pool()
async with pool.get_session("myserver") as session:
    # Use the shared session
    pass
```

### Server Registry for Multiple Servers

```python
from src import MCPServerRegistry, MCPServerConfig

async def main():
    registry = MCPServerRegistry()

    # Add multiple servers
    registry.add(MCPServerConfig(
        name="filesystem",
        command="npx",
        args=["-y", "@modelcontextprotocol/server-filesystem", "/tmp"]
    ))

    registry.add(MCPServerConfig(
        name="memory",
        command="npx",
        args=["-y", "@modelcontextprotocol/server-memory"]
    ))

    async with registry:
        # Get a specific server wrapper
        fs = registry.get("filesystem")
        tools = await fs.list_tools()

        # Get all tools from all servers
        all_tools = await registry.get_all_tools()
```

## Key Components

### MCPServerConfig

Pydantic model for server configuration:

```python
MCPServerConfig(
    name="myserver",           # Unique identifier
    command="npx",             # Command to start the server
    args=["-y", "package"],    # Command arguments
    env={"KEY": "value"},      # Environment variables
    transport="stdio",         # Transport type (stdio, sse, streamable_http)
)
```

### MCPConnectionPool

Central pool for shared connections:

- `add_server(config)` - Add a server configuration
- `remove_server(name)` - Remove a server
- `get_session(name)` - Get a shared session (async context manager)
- `get_all_tools()` - Get tools from all servers
- `call_tool(server, tool, args)` - Call a tool
- Reference counting ensures connections stay open while in use

### AgentManager

High-level entry point combining pool and registry:

- `add_server(config)` - Add a server
- `get_server(name)` - Get server wrapper
- `get_session(name)` - Get shared session
- `get_all_tools()` - Get all tools
- `call_tool(server, tool, args)` - Call a tool

## License

See LICENSE file for details.
