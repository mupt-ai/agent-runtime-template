"""Shared MCP connection pool management.

This module provides a centralized connection pool for managing MCP server
connections, allowing multiple agents/code generators to share connections
instead of each creating their own.
"""

import asyncio
import logging
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, AsyncIterator, Callable, Optional

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class TransportType(str, Enum):
    """Supported MCP transport types."""

    STDIO = "stdio"
    SSE = "sse"
    STREAMABLE_HTTP = "streamable_http"


class MCPServerConfig(BaseModel):
    """Configuration for an MCP server connection."""

    name: str = Field(..., description="Unique identifier for the server")
    command: str = Field(..., description="Command to start the server (for stdio)")
    args: list[str] = Field(default_factory=list, description="Command arguments")
    env: dict[str, str] = Field(default_factory=dict, description="Environment variables")
    transport: TransportType = Field(default=TransportType.STDIO, description="Transport type")
    url: Optional[str] = Field(default=None, description="URL for HTTP-based transports")


@dataclass
class SharedConnection:
    """A shared MCP connection with reference counting."""

    config: MCPServerConfig
    session: Optional[ClientSession] = None
    _ref_count: int = 0
    _lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    _cleanup_callback: Optional[Callable[[], Any]] = None
    _connected: bool = False

    @property
    def ref_count(self) -> int:
        """Get the current reference count."""
        return self._ref_count

    @property
    def is_connected(self) -> bool:
        """Check if the connection is active."""
        return self._connected and self.session is not None

    async def acquire(self) -> ClientSession:
        """Acquire a reference to this connection."""
        async with self._lock:
            self._ref_count += 1
            if self.session is None:
                raise RuntimeError(f"Connection to {self.config.name} is not initialized")
            return self.session

    async def release(self) -> int:
        """Release a reference to this connection."""
        async with self._lock:
            self._ref_count = max(0, self._ref_count - 1)
            return self._ref_count


class MCPConnectionPool:
    """Pool for managing shared MCP connections.

    This class provides a centralized way to manage MCP server connections,
    allowing multiple consumers to share the same connection instead of
    each creating their own.

    Example:
        ```python
        pool = MCPConnectionPool()

        # Add server configurations
        pool.add_server(MCPServerConfig(
            name="filesystem",
            command="npx",
            args=["-y", "@modelcontextprotocol/server-filesystem", "/tmp"]
        ))

        # Start the pool
        async with pool:
            # Get a shared session
            async with pool.get_session("filesystem") as session:
                # Use the session
                tools = await session.list_tools()
        ```
    """

    def __init__(self, max_idle_time: float = 300.0):
        """Initialize the connection pool.

        Args:
            max_idle_time: Maximum time (seconds) to keep idle connections alive.
        """
        self._connections: dict[str, SharedConnection] = {}
        self._configs: dict[str, MCPServerConfig] = {}
        self._lock = asyncio.Lock()
        self._max_idle_time = max_idle_time
        self._running = False
        self._cleanup_tasks: dict[str, asyncio.Task] = {}
        self._context_managers: dict[str, Any] = {}

    @property
    def server_names(self) -> list[str]:
        """Get list of configured server names."""
        return list(self._configs.keys())

    @property
    def active_connections(self) -> int:
        """Get count of active connections."""
        return sum(1 for conn in self._connections.values() if conn.is_connected)

    def add_server(self, config: MCPServerConfig) -> None:
        """Add a server configuration to the pool.

        Args:
            config: Server configuration to add.

        Raises:
            ValueError: If a server with the same name already exists.
        """
        if config.name in self._configs:
            raise ValueError(f"Server '{config.name}' already configured")
        self._configs[config.name] = config
        logger.info(f"Added server configuration: {config.name}")

    def remove_server(self, name: str) -> None:
        """Remove a server configuration from the pool.

        Args:
            name: Name of the server to remove.

        Raises:
            ValueError: If server doesn't exist or has active connections.
        """
        if name not in self._configs:
            raise ValueError(f"Server '{name}' not found")
        if name in self._connections and self._connections[name].ref_count > 0:
            raise ValueError(f"Server '{name}' has active connections")
        self._configs.pop(name, None)
        self._connections.pop(name, None)
        logger.info(f"Removed server configuration: {name}")

    async def _create_connection(self, name: str) -> SharedConnection:
        """Create a new connection for a server.

        Args:
            name: Name of the server to connect to.

        Returns:
            The created SharedConnection.
        """
        config = self._configs[name]
        connection = SharedConnection(config=config)

        if config.transport == TransportType.STDIO:
            server_params = StdioServerParameters(
                command=config.command,
                args=config.args,
                env=config.env if config.env else None,
            )

            # Create and store the context manager
            cm = stdio_client(server_params)
            read_stream, write_stream = await cm.__aenter__()
            self._context_managers[name] = cm

            # Create the session
            session_cm = ClientSession(read_stream, write_stream)
            session = await session_cm.__aenter__()
            self._context_managers[f"{name}_session"] = session_cm

            # Initialize the session
            await session.initialize()

            connection.session = session
            connection._connected = True
            logger.info(f"Created stdio connection to {name}")

        else:
            raise NotImplementedError(f"Transport {config.transport} not yet implemented")

        return connection

    async def _close_connection(self, name: str) -> None:
        """Close a connection and clean up resources.

        Args:
            name: Name of the server connection to close.
        """
        if name not in self._connections:
            return

        connection = self._connections[name]
        connection._connected = False

        # Clean up session context manager
        session_key = f"{name}_session"
        if session_key in self._context_managers:
            try:
                await self._context_managers[session_key].__aexit__(None, None, None)
            except Exception as e:
                logger.warning(f"Error closing session for {name}: {e}")
            del self._context_managers[session_key]

        # Clean up transport context manager
        if name in self._context_managers:
            try:
                await self._context_managers[name].__aexit__(None, None, None)
            except Exception as e:
                logger.warning(f"Error closing transport for {name}: {e}")
            del self._context_managers[name]

        del self._connections[name]
        logger.info(f"Closed connection to {name}")

    @asynccontextmanager
    async def get_session(self, name: str) -> AsyncIterator[ClientSession]:
        """Get a shared session for a server.

        This context manager handles reference counting and connection
        lifecycle automatically.

        Args:
            name: Name of the server to connect to.

        Yields:
            The MCP ClientSession for the server.

        Raises:
            ValueError: If the server is not configured.
            RuntimeError: If the pool is not running.
        """
        if not self._running:
            raise RuntimeError("Connection pool is not running")

        if name not in self._configs:
            raise ValueError(f"Server '{name}' is not configured")

        async with self._lock:
            # Create connection if it doesn't exist
            if name not in self._connections or not self._connections[name].is_connected:
                self._connections[name] = await self._create_connection(name)

            connection = self._connections[name]

        # Acquire reference
        session = await connection.acquire()

        try:
            yield session
        finally:
            # Release reference
            remaining = await connection.release()
            logger.debug(f"Released reference to {name}, {remaining} remaining")

    async def get_all_tools(self) -> dict[str, list[Any]]:
        """Get all tools from all connected servers.

        Returns:
            Dictionary mapping server names to their available tools.
        """
        tools = {}
        for name in self._configs:
            try:
                async with self.get_session(name) as session:
                    result = await session.list_tools()
                    tools[name] = result.tools
            except Exception as e:
                logger.error(f"Failed to get tools from {name}: {e}")
                tools[name] = []
        return tools

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
        async with self.get_session(server_name) as session:
            result = await session.call_tool(tool_name, arguments)
            return result

    async def start(self) -> None:
        """Start the connection pool."""
        self._running = True
        logger.info("MCP connection pool started")

    async def stop(self) -> None:
        """Stop the connection pool and close all connections."""
        self._running = False

        # Cancel any cleanup tasks
        for task in self._cleanup_tasks.values():
            task.cancel()
        self._cleanup_tasks.clear()

        # Close all connections
        for name in list(self._connections.keys()):
            await self._close_connection(name)

        logger.info("MCP connection pool stopped")

    async def __aenter__(self) -> "MCPConnectionPool":
        """Async context manager entry."""
        await self.start()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """Async context manager exit."""
        await self.stop()


# Global connection pool instance for convenience
_global_pool: Optional[MCPConnectionPool] = None


def get_global_pool() -> MCPConnectionPool:
    """Get or create the global connection pool.

    Returns:
        The global MCPConnectionPool instance.
    """
    global _global_pool
    if _global_pool is None:
        _global_pool = MCPConnectionPool()
    return _global_pool


def set_global_pool(pool: MCPConnectionPool) -> None:
    """Set the global connection pool.

    Args:
        pool: The pool to use as the global instance.
    """
    global _global_pool
    _global_pool = pool
