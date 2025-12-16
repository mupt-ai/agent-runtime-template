"""Agent runtime manager.

This module provides the AgentManager class which manages the agent runtime
and execution, including shared MCP connections.
"""

import logging
from typing import Any, Optional

from .connections import (
    MCPConnectionPool,
    MCPServerConfig,
    get_global_pool,
    set_global_pool,
)
from .servers import MCPServerRegistry, MCPServerWrapper

logger = logging.getLogger(__name__)


class AgentManager:
    """Manages agent runtime and execution with shared MCP connections.

    The AgentManager provides a centralized way to manage MCP server connections,
    ensuring that multiple code generators or agents share connections instead
    of each creating their own.

    Example:
        ```python
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
            args=["-y", "@modelcontextprotocol/server-github"]
        ))

        # Start the runtime
        async with manager:
            # Get tools from all servers
            tools = await manager.get_all_tools()

            # Call a specific tool
            result = await manager.call_tool(
                "filesystem",
                "read_file",
                {"path": "/tmp/test.txt"}
            )

            # Get a session for direct access
            async with manager.get_session("filesystem") as session:
                # Use session directly
                pass
        ```
    """

    def __init__(
        self,
        pool: Optional[MCPConnectionPool] = None,
        use_global_pool: bool = True,
    ):
        """Initialize the agent manager.

        Args:
            pool: Optional connection pool to use. If None and use_global_pool
                is True, the global pool will be used.
            use_global_pool: If True and no pool is provided, use/create the
                global connection pool.
        """
        if pool is not None:
            self._pool = pool
        elif use_global_pool:
            self._pool = get_global_pool()
        else:
            self._pool = MCPConnectionPool()

        self._registry = MCPServerRegistry(pool=self._pool)
        self._running = False

        # Set as global pool if we created a new one
        if pool is None and use_global_pool:
            set_global_pool(self._pool)

    @property
    def pool(self) -> MCPConnectionPool:
        """Get the connection pool."""
        return self._pool

    @property
    def registry(self) -> MCPServerRegistry:
        """Get the server registry."""
        return self._registry

    @property
    def is_running(self) -> bool:
        """Check if the manager is running."""
        return self._running

    @property
    def server_names(self) -> list[str]:
        """Get list of configured server names."""
        return self._registry.server_names

    def add_server(self, config: MCPServerConfig) -> MCPServerWrapper:
        """Add an MCP server configuration.

        Args:
            config: Server configuration to add.

        Returns:
            The created server wrapper.
        """
        return self._registry.add(config)

    def remove_server(self, name: str) -> None:
        """Remove an MCP server.

        Args:
            name: Name of the server to remove.
        """
        self._registry.remove(name)

    def get_server(self, name: str) -> MCPServerWrapper:
        """Get a server wrapper by name.

        Args:
            name: Server name.

        Returns:
            The server wrapper.
        """
        return self._registry.get(name)

    def get_session(self, name: str):
        """Get a session context manager for a server.

        Args:
            name: Server name.

        Returns:
            Async context manager yielding a ClientSession.
        """
        return self._pool.get_session(name)

    async def get_all_tools(self) -> dict[str, list[Any]]:
        """Get all tools from all configured servers.

        Returns:
            Dictionary mapping server names to their tools.
        """
        return await self._registry.get_all_tools()

    async def call_tool(
        self, server_name: str, tool_name: str, arguments: dict[str, Any]
    ) -> Any:
        """Call a tool on a specific server.

        Args:
            server_name: Name of the server.
            tool_name: Name of the tool to call.
            arguments: Arguments to pass to the tool.

        Returns:
            The tool result.
        """
        return await self._pool.call_tool(server_name, tool_name, arguments)

    async def start(self) -> None:
        """Start the agent runtime."""
        if self._running:
            return
        await self._registry.start()
        self._running = True
        logger.info("Agent manager started")

    async def stop(self) -> None:
        """Stop the agent runtime."""
        if not self._running:
            return
        await self._registry.stop()
        self._running = False
        logger.info("Agent manager stopped")

    async def __aenter__(self) -> "AgentManager":
        """Async context manager entry."""
        await self.start()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """Async context manager exit."""
        await self.stop()


__all__ = ["AgentManager"]
