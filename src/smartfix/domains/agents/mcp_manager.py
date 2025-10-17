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
import platform
from pathlib import Path
from typing import List

from src.utils import debug_log, log, error_exit
from src.smartfix.shared.failure_categories import FailureCategory

try:
    from google.adk.tools.mcp_tool.mcp_toolset import MCPToolset, StdioServerParameters, StdioConnectionParams
    MCP_AVAILABLE = True
except ImportError:
    MCP_AVAILABLE = False


async def _create_mcp_toolset(target_folder_str: str) -> MCPToolset:
    """Create MCP toolset with platform-specific configuration."""
    if platform.system() == 'Windows':
        connection_timeout = 180
        debug_log("Using Windows-specific MCP connection settings")
    else:
        connection_timeout = 120

    return MCPToolset(
        connection_params=StdioConnectionParams(
            server_params=StdioServerParameters(
                command='npx',
                args=[
                    '-y',  # Arguments for the command
                    '--cache', '/tmp/.npm-cache',  # Use explicit cache directory
                    '--prefer-offline',  # Try to use cached packages first
                    '@modelcontextprotocol/server-filesystem@2025.1.14',
                    target_folder_str,
                ],
            ),
            timeout=connection_timeout,
        )
    )


async def _get_tools_timeout() -> float:
    """Get platform-specific timeout for MCP tools connection."""
    if platform.system() == 'Windows':
        return 120.0  # Much longer timeout for Windows
    else:
        return 30.0  # Increased timeout for Linux due to npm issues


async def _clear_npm_cache_if_needed(attempt: int, max_retries: int):
    """Clear npm cache on second retry if needed."""
    if attempt == 2:
        debug_log("Clearing npm cache due to repeated failures...")
        try:
            import subprocess
            subprocess.run(['npm', 'cache', 'clean', '--force'],
                           capture_output=True, timeout=30)
            debug_log("NPM cache cleared successfully")
        except Exception as cache_error:
            debug_log(f"Failed to clear npm cache: {cache_error}")


async def _attempt_mcp_connection(fs_tools: MCPToolset, get_tools_timeout: float) -> List:
    """Attempt to connect to MCP server and get tools."""
    return await asyncio.wait_for(fs_tools.get_tools(), timeout=get_tools_timeout)


async def get_mcp_tools(target_folder: Path, remediation_id: str) -> MCPToolset:
    """
    Connects to MCP servers (Filesystem) and returns the toolset.

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

    # Filesystem MCP Server
    try:
        debug_log("Connecting to MCP Filesystem server...")

        fs_tools = await _create_mcp_toolset(target_folder_str)
        get_tools_timeout = await _get_tools_timeout()

        debug_log("Getting tools list from Filesystem MCP server...")
        debug_log(f"Using {get_tools_timeout} second timeout for get_tools")

        # Add retry mechanism for MCP connection reliability across all platforms
        max_retries = 3
        last_error = None

        for attempt in range(max_retries):
            try:
                if attempt > 0:
                    debug_log(f"Retrying MCP connection (attempt {attempt + 1}/{max_retries})")
                    await _clear_npm_cache_if_needed(attempt, max_retries)
                    # Wait a bit before retry to let any broken connections clean up
                    await asyncio.sleep(2)

                # Wrap the get_tools call in wait_for to apply a timeout
                tools_list = await _attempt_mcp_connection(fs_tools, get_tools_timeout)
                debug_log(f"Connected to Filesystem MCP server, got {len(tools_list)} tools")
                break  # Success, exit retry loop

            except (asyncio.TimeoutError, asyncio.CancelledError, ConnectionError) as retry_error:
                last_error = retry_error
                debug_log(f"MCP connection attempt {attempt + 1} failed: {type(retry_error).__name__}: {str(retry_error)}")
                if attempt == max_retries - 1:
                    # Last attempt failed, re-raise the error
                    raise retry_error
        else:
            # This should not be reached, but just in case
            raise last_error if last_error else Exception("Unknown MCP connection failure")

        for tool in tools_list:
            if hasattr(tool, 'name'):
                debug_log(f"  - Filesystem Tool: {tool.name}")
            else:
                debug_log("  - Filesystem Tool: (Name attribute missing)")

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

    debug_log(f"Total tools from all MCP servers: {len(tools_list)}")
    return fs_tools
