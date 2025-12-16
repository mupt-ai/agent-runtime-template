"""Agent runtime core modules.

This package provides tools for building agent runtimes with shared MCP
(Model Context Protocol) connections.

Key components:
- MCPConnectionPool: Manages shared connections to MCP servers
- MCPServerConfig: Configuration for MCP server connections
- MCPServerWrapper: High-level wrapper for interacting with MCP servers
- MCPServerRegistry: Registry for managing multiple servers
- AgentManager: Main entry point for agent runtime management

Example:
    ```python
    from src import AgentManager, MCPServerConfig

    manager = AgentManager()

    # Add MCP servers
    manager.add_server(MCPServerConfig(
        name="filesystem",
        command="npx",
        args=["-y", "@modelcontextprotocol/server-filesystem", "/tmp"]
    ))

    # Start and use
    async with manager:
        tools = await manager.get_all_tools()
        result = await manager.call_tool("filesystem", "read_file", {"path": "/tmp/test.txt"})
    ```
"""

__version__ = "0.1.0"

from .connections import (
    MCPConnectionPool,
    MCPServerConfig,
    SharedConnection,
    TransportType,
    get_global_pool,
    set_global_pool,
)
from .manager import AgentManager
from .servers import MCPServerRegistry, MCPServerWrapper

__all__ = [
    # Version
    "__version__",
    # Connection management
    "MCPConnectionPool",
    "MCPServerConfig",
    "SharedConnection",
    "TransportType",
    "get_global_pool",
    "set_global_pool",
    # Server wrappers
    "MCPServerWrapper",
    "MCPServerRegistry",
    # Manager
    "AgentManager",
]
