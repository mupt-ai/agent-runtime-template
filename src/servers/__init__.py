"""Base MCP server wrappers.

This module provides wrapper classes for managing MCP servers and their
tools/resources in a unified way.
"""

import logging
from typing import Any, Optional

from ..connections import MCPConnectionPool, MCPServerConfig, get_global_pool

logger = logging.getLogger(__name__)


class MCPServerWrapper:
    """Wrapper for interacting with an MCP server through a shared connection pool.

    This class provides a high-level interface for working with MCP servers,
    using shared connections from a connection pool instead of creating
    individual connections.

    Example:
        ```python
        # Using with global pool
        wrapper = MCPServerWrapper(
            config=MCPServerConfig(
                name="filesystem",
                command="npx",
                args=["-y", "@modelcontextprotocol/server-filesystem", "/tmp"]
            )
        )

        # Register with pool and use
        async with get_global_pool() as pool:
            await wrapper.register()
            tools = await wrapper.list_tools()
            result = await wrapper.call_tool("read_file", {"path": "/tmp/test.txt"})
        ```
    """

    def __init__(
        self,
        config: MCPServerConfig,
        pool: Optional[MCPConnectionPool] = None,
    ):
        """Initialize the server wrapper.

        Args:
            config: Configuration for the MCP server.
            pool: Connection pool to use. If None, uses the global pool.
        """
        self.config = config
        self._pool = pool
        self._registered = False

    @property
    def pool(self) -> MCPConnectionPool:
        """Get the connection pool being used."""
        return self._pool or get_global_pool()

    @property
    def name(self) -> str:
        """Get the server name."""
        return self.config.name

    @property
    def is_registered(self) -> bool:
        """Check if this server is registered with the pool."""
        return self._registered

    def register(self) -> None:
        """Register this server with the connection pool."""
        if self._registered:
            return
        self.pool.add_server(self.config)
        self._registered = True
        logger.info(f"Registered server: {self.name}")

    def unregister(self) -> None:
        """Unregister this server from the connection pool."""
        if not self._registered:
            return
        try:
            self.pool.remove_server(self.name)
        except ValueError:
            pass  # Already removed
        self._registered = False
        logger.info(f"Unregistered server: {self.name}")

    async def list_tools(self) -> list[Any]:
        """List all tools available from this server.

        Returns:
            List of available tools.
        """
        async with self.pool.get_session(self.name) as session:
            result = await session.list_tools()
            return result.tools

    async def list_resources(self) -> list[Any]:
        """List all resources available from this server.

        Returns:
            List of available resources.
        """
        async with self.pool.get_session(self.name) as session:
            result = await session.list_resources()
            return result.resources

    async def list_prompts(self) -> list[Any]:
        """List all prompts available from this server.

        Returns:
            List of available prompts.
        """
        async with self.pool.get_session(self.name) as session:
            result = await session.list_prompts()
            return result.prompts

    async def call_tool(self, tool_name: str, arguments: dict[str, Any]) -> Any:
        """Call a tool on this server.

        Args:
            tool_name: Name of the tool to call.
            arguments: Arguments to pass to the tool.

        Returns:
            The tool result.
        """
        async with self.pool.get_session(self.name) as session:
            result = await session.call_tool(tool_name, arguments)
            return result

    async def read_resource(self, uri: str) -> Any:
        """Read a resource from this server.

        Args:
            uri: URI of the resource to read.

        Returns:
            The resource contents.
        """
        async with self.pool.get_session(self.name) as session:
            result = await session.read_resource(uri)
            return result

    async def get_prompt(self, name: str, arguments: Optional[dict[str, str]] = None) -> Any:
        """Get a prompt from this server.

        Args:
            name: Name of the prompt.
            arguments: Optional arguments for the prompt.

        Returns:
            The prompt result.
        """
        async with self.pool.get_session(self.name) as session:
            result = await session.get_prompt(name, arguments)
            return result


class MCPServerRegistry:
    """Registry for managing multiple MCP server wrappers.

    This class provides a convenient way to manage multiple MCP servers
    and their shared connections.

    Example:
        ```python
        registry = MCPServerRegistry()

        # Add servers
        registry.add(MCPServerConfig(
            name="filesystem",
            command="npx",
            args=["-y", "@modelcontextprotocol/server-filesystem", "/tmp"]
        ))

        registry.add(MCPServerConfig(
            name="github",
            command="npx",
            args=["-y", "@modelcontextprotocol/server-github"]
        ))

        # Use the registry
        async with registry:
            fs_tools = await registry.get("filesystem").list_tools()
            all_tools = await registry.get_all_tools()
        ```
    """

    def __init__(self, pool: Optional[MCPConnectionPool] = None):
        """Initialize the registry.

        Args:
            pool: Connection pool to use. If None, uses the global pool.
        """
        self._pool = pool
        self._servers: dict[str, MCPServerWrapper] = {}

    @property
    def pool(self) -> MCPConnectionPool:
        """Get the connection pool being used."""
        return self._pool or get_global_pool()

    @property
    def server_names(self) -> list[str]:
        """Get list of registered server names."""
        return list(self._servers.keys())

    def add(self, config: MCPServerConfig) -> MCPServerWrapper:
        """Add a server to the registry.

        Args:
            config: Server configuration.

        Returns:
            The created server wrapper.
        """
        wrapper = MCPServerWrapper(config=config, pool=self._pool)
        wrapper.register()
        self._servers[config.name] = wrapper
        return wrapper

    def get(self, name: str) -> MCPServerWrapper:
        """Get a server wrapper by name.

        Args:
            name: Server name.

        Returns:
            The server wrapper.

        Raises:
            KeyError: If server not found.
        """
        if name not in self._servers:
            raise KeyError(f"Server '{name}' not found in registry")
        return self._servers[name]

    def remove(self, name: str) -> None:
        """Remove a server from the registry.

        Args:
            name: Server name to remove.
        """
        if name in self._servers:
            self._servers[name].unregister()
            del self._servers[name]

    async def get_all_tools(self) -> dict[str, list[Any]]:
        """Get all tools from all registered servers.

        Returns:
            Dictionary mapping server names to their tools.
        """
        return await self.pool.get_all_tools()

    async def start(self) -> None:
        """Start the registry and underlying connection pool."""
        await self.pool.start()

    async def stop(self) -> None:
        """Stop the registry and underlying connection pool."""
        await self.pool.stop()

    async def __aenter__(self) -> "MCPServerRegistry":
        """Async context manager entry."""
        await self.start()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """Async context manager exit."""
        await self.stop()


__all__ = ["MCPServerWrapper", "MCPServerRegistry"]
