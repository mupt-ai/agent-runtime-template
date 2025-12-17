"""MCP Connection Manager for managing MCP server connections."""

from typing import Any, Optional, Dict, List
from contextlib import asynccontextmanager
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


class MCPConnectionManager:
    """Manages connection to an MCP server via stdio."""

    def __init__(
        self,
        command: str,
        args: Optional[List[str]] = None,
        env: Optional[Dict[str, str]] = None,
    ):
        """Initialize the connection manager.

        Args:
            command: The command to run the MCP server
            args: Optional arguments for the command
            env: Optional environment variables
        """
        self.command = command
        self.args = args or []
        self.env = env
        self._session: Optional[ClientSession] = None
        self._exit_stack = None

    async def connect(self):
        """Connect to the MCP server."""
        if self._session is not None:
            return  # Already connected

        from contextlib import AsyncExitStack

        self._exit_stack = AsyncExitStack()
        await self._exit_stack.__aenter__()

        server_params = StdioServerParameters(
            command=self.command,
            args=self.args,
            env=self.env,
        )

        # Create the stdio client
        stdio_transport = await self._exit_stack.enter_async_context(
            stdio_client(server_params)
        )

        # Get read and write streams
        read_stream, write_stream = stdio_transport

        # Initialize the session
        self._session = await self._exit_stack.enter_async_context(
            ClientSession(read_stream, write_stream)
        )

        # Initialize the session
        await self._session.initialize()

    async def disconnect(self):
        """Disconnect from the MCP server."""
        if self._exit_stack is not None:
            await self._exit_stack.__aexit__(None, None, None)
            self._exit_stack = None
            self._session = None

    async def get_session(self) -> ClientSession:
        """Get the current session, connecting if necessary.

        Returns:
            The active ClientSession

        Raises:
            RuntimeError: If not connected
        """
        if self._session is None:
            raise RuntimeError(
                "Not connected to MCP server. Call connect() first."
            )
        return self._session

    async def __aenter__(self):
        """Async context manager entry."""
        await self.connect()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self.disconnect()
        return False