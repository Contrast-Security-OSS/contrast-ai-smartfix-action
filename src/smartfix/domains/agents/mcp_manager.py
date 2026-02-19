# -
# #%L
# Contrast AI SmartFix
# %%
# Copyright (C) 2025 Contrast Security, Inc.
# %%
# Contact: support@contrastsecurity.com
# License: Commercial
# NOTICE: This Software and the patented inventions embodied within may only be
# used as part of Contrast Security's commercial offerings. Even though it is
# made available through public repositories, use of this Software is subject to
# the applicable End User Licensing Agreement found at
# https://www.contrastsecurity.com/enduser-terms-0317a or as otherwise agreed
# between Contrast Security and the End User. The Software may not be reverse
# engineered, modified, repackaged, sold, redistributed or otherwise used in a
# way not consistent with the End User License Agreement.
# #L%
#

"""
MCP (Model Context Protocol) Manager Module

Handles connection to MCP servers, toolset creation, and platform-specific
configuration for filesystem access in agent operations.
"""

import asyncio
import logging
import platform
import warnings
from pathlib import Path
from typing import List, Optional

from src.utils import debug_log, log, error_exit
from src.smartfix.shared.failure_categories import FailureCategory

# Suppress Python warnings before importing libraries that might trigger them
warnings.filterwarnings('ignore', category=UserWarning)
# Suppress specific Pydantic field shadowing warning from ADK library
warnings.filterwarnings(
    'ignore',
    message='Field name "config_type" in "SequentialAgent" shadows an attribute in parent "BaseAgent"'
)

try:
    from google.adk.tools.mcp_tool.mcp_toolset import MCPToolset, StdioServerParameters, StdioConnectionParams
    MCP_AVAILABLE = True
except ImportError:
    MCP_AVAILABLE = False

# Configure library loggers to reduce noise from ADK authentication warnings
library_logger = logging.getLogger("google_adk.google.adk.tools.base_authenticated_tool")
library_logger.setLevel(logging.ERROR)


class MCPToolsetManager:
    """
    Manages MCP toolset creation, connection lifecycle, and platform-specific configuration.

    Encapsulates MCP server connection logic with retry handling, platform-specific
    timeouts, and npm cache management.
    """

    def __init__(self, platform_name: Optional[str] = None):
        """
        Initialize MCP toolset manager with platform-specific configuration.

        Args:
            platform_name: Platform name (defaults to current system platform)
        """
        self.platform = platform_name or platform.system()
        self.is_windows = self.platform == 'Windows'

        # Platform-specific timeouts
        self.connection_timeout = 180 if self.is_windows else 120
        self.tools_timeout = 120.0 if self.is_windows else 30.0

        # Retry configuration
        self.max_retries = 3
        self.retry_delay = 2  # seconds

        # NPM configuration
        self.npm_cache_path = '/tmp/.npm-cache'
        self.mcp_package = '@modelcontextprotocol/server-filesystem@2026.1.14'

    async def get_tools(self, target_folder: Path, remediation_id: str) -> MCPToolset:
        """
        Connect to MCP servers and return the toolset with retry logic.

        Main entry point for obtaining MCP tools. Handles connection retries,
        error logging, and failure categorization.

        Args:
            target_folder: Path to the folder to provide filesystem access to
            remediation_id: Remediation ID for error tracking

        Returns:
            MCPToolset: Connected toolset with filesystem tools

        Raises:
            SystemExit: On connection failure or missing dependencies
        """
        debug_log("Attempting to connect to MCP servers...")
        target_folder_str = str(target_folder)

        try:
            debug_log("Connecting to MCP Filesystem server...")

            # Create toolset
            fs_tools = await self._create_toolset(target_folder_str)

            debug_log("Getting tools list from Filesystem MCP server...")
            debug_log(f"Using {self.tools_timeout} second timeout for get_tools")

            # Attempt connection with retries
            tools_list = await self._connect_with_retry(fs_tools)

            debug_log(f"Connected to Filesystem MCP server, got {len(tools_list)} tools")

            # Log available tools
            for tool in tools_list:
                if hasattr(tool, 'name'):
                    debug_log(f"  - Filesystem Tool: {tool.name}")
                else:
                    debug_log("  - Filesystem Tool: (Name attribute missing)")

            debug_log(f"Total tools from all MCP servers: {len(tools_list)}")

            return fs_tools

        except NameError as ne:
            log(f"FATAL: Error initializing MCP Filesystem server (likely ADK setup issue): {ne}", is_error=True)
            log("No filesystem tools available - cannot make code changes.", is_error=True)
            error_exit(remediation_id, FailureCategory.AGENT_FAILURE.value)
        except Exception as e:
            log(f"FATAL: Failed to connect to Filesystem MCP server: {str(e)}", is_error=True)
            # Get better error information when possible
            if hasattr(e, '__traceback__'):
                import traceback
                log(f"Error details: {traceback.format_exc()}", is_error=True)
            log("No filesystem tools available - cannot make code changes.", is_error=True)
            error_exit(remediation_id, FailureCategory.AGENT_FAILURE.value)

    async def _create_toolset(self, target_folder_str: str) -> MCPToolset:
        """
        Create MCP toolset with platform-specific configuration.

        Args:
            target_folder_str: String path to target folder

        Returns:
            MCPToolset: Configured toolset instance
        """
        if self.is_windows:
            debug_log("Using Windows-specific MCP connection settings")

        return MCPToolset(
            connection_params=StdioConnectionParams(
                server_params=StdioServerParameters(
                    command='npx',
                    args=self._build_npx_args(target_folder_str),
                ),
                timeout=self.connection_timeout,
            )
        )

    def _build_npx_args(self, target_folder_str: str) -> List[str]:
        """
        Build npx arguments for MCP server startup.

        Args:
            target_folder_str: String path to target folder

        Returns:
            List of arguments for npx command
        """
        return [
            '-y',  # Auto-accept installation
            '--cache', self.npm_cache_path,  # Use explicit cache directory
            '--prefer-offline',  # Try to use cached packages first
            self.mcp_package,
            target_folder_str,
        ]

    async def _connect_with_retry(self, toolset: MCPToolset) -> List:
        """
        Attempt to connect to MCP server with retry logic.

        Args:
            toolset: MCPToolset instance to connect

        Returns:
            List of tools from the MCP server

        Raises:
            Exception: If all retry attempts fail
        """
        last_error = None

        for attempt in range(self.max_retries):
            try:
                if attempt > 0:
                    debug_log(f"Retrying MCP connection (attempt {attempt + 1}/{self.max_retries})")
                    await self._handle_retry(attempt)

                # Attempt connection with timeout
                tools_list = await self._attempt_connection(toolset)
                return tools_list

            except (asyncio.TimeoutError, asyncio.CancelledError, ConnectionError) as retry_error:
                last_error = retry_error
                debug_log(
                    f"MCP connection attempt {attempt + 1} failed: "
                    f"{type(retry_error).__name__}: {str(retry_error)}"
                )

                if attempt == self.max_retries - 1:
                    # Last attempt failed, re-raise the error
                    raise retry_error

        # This should not be reached, but just in case
        raise last_error if last_error else Exception("Unknown MCP connection failure")

    async def _attempt_connection(self, toolset: MCPToolset) -> List:
        """
        Attempt to connect to MCP server with timeout.

        Args:
            toolset: MCPToolset instance to connect

        Returns:
            List of tools from the MCP server
        """
        return await asyncio.wait_for(toolset.get_tools(), timeout=self.tools_timeout)

    async def _handle_retry(self, attempt: int):
        """
        Handle retry preparation (cache clearing, delays).

        Args:
            attempt: Current attempt number (0-indexed)
        """
        # Clear npm cache on second retry (attempt == 1, since 0-indexed)
        if attempt == 1:
            await self._clear_npm_cache()

        # Wait before retry to let connections clean up
        await asyncio.sleep(self.retry_delay)

    async def _clear_npm_cache(self):
        """Clear npm cache to resolve potential package issues."""
        debug_log("Clearing npm cache due to repeated failures...")
        try:
            import subprocess
            subprocess.run(
                ['npm', 'cache', 'clean', '--force'],
                capture_output=True,
                timeout=30
            )
            debug_log("NPM cache cleared successfully")
        except Exception as cache_error:
            debug_log(f"Failed to clear npm cache: {cache_error}")
