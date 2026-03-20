# -
# #%L
# Contrast AI SmartFix
# %%
# Copyright (C) 2026 Contrast Security, Inc.
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
Event Loop Utilities Module

Provides event loop management, platform-specific configuration, and
high-level agent execution wrapper functions.
"""

import asyncio
import logging
import platform
from typing import Any

from src.utils import debug_log, log

# Conditional imports
try:
    from asyncio import WindowsProactorEventLoopPolicy
except ImportError:
    pass

MAX_PENDING_TASKS = 100


def _configure_cleanup_logging() -> None:
    """Configure logging to suppress benign asyncio and MCP cleanup errors."""
    # Suppress anyio error logging
    anyio_logger = logging.getLogger("anyio")
    anyio_logger.setLevel(logging.CRITICAL)

    # Suppress MCP client/stdio error logging
    mcp_logger = logging.getLogger("mcp.client.stdio")
    mcp_logger.setLevel(logging.CRITICAL)

    # Silence the task exception was never retrieved warnings
    asyncio_logger = logging.getLogger("asyncio")
    asyncio_logger.setLevel(logging.CRITICAL)

    # Add a comprehensive filter to specifically ignore common cancel scope and cleanup errors
    class AsyncioCleanupFilter(logging.Filter):
        def filter(self, record) -> bool:
            message = record.getMessage()
            # Filter out common cleanup errors
            if any(pattern in message for pattern in [
                "exit cancel scope in a different task",
                "Task exception was never retrieved",
                "unhandled errors in a TaskGroup",
                "GeneratorExit",
                "CancelledError",
                "asyncio.exceptions",
                "BaseExceptionGroup"
            ]):
                return False
            return True

    # Apply the filter to multiple loggers
    cleanup_filter = AsyncioCleanupFilter()
    anyio_logger.addFilter(cleanup_filter)
    asyncio_logger.addFilter(cleanup_filter)
    if mcp_logger:
        mcp_logger.addFilter(cleanup_filter)


def _run_agent_in_event_loop(coroutine_func, *args, **kwargs) -> Any:
    """
    Wrapper function to run an async coroutine in a controlled event loop.
    Handles proper setup and cleanup of the event loop and tasks.

    Args:
        coroutine_func: The async function to run
        *args, **kwargs: Arguments to pass to the coroutine function

    Returns:
        The result returned by the coroutine
    """
    result = None

    # Configure logging to suppress asyncio and anyio errors that typically occur during cleanup
    _configure_cleanup_logging()

    # Platform-specific setup
    is_windows = platform.system() == 'Windows'

    # On Windows, we must use the WindowsProactorEventLoopPolicy
    # The SelectorEventLoop on Windows doesn't support subprocesses, which are required for MCP
    if is_windows:
        try:
            # Close any existing loop first
            try:
                existing_loop = asyncio.get_event_loop()
                if not existing_loop.is_closed():
                    debug_log("Closing existing event loop")
                    existing_loop.close()
            except RuntimeError:
                pass  # No current loop, that's fine

            # Explicitly set the WindowsProactorEventLoopPolicy
            # This ensures subprocesses will work on Windows
            asyncio.set_event_loop_policy(WindowsProactorEventLoopPolicy())
            debug_log("Explicitly set WindowsProactorEventLoopPolicy for subprocess support")
        except Exception as e:
            debug_log(f"Warning: Error handling Windows event loop policy: {e}")

    # Create a new event loop for this function call
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    # For diagnostic purposes, log information about the loop
    loop_policy_name = type(asyncio.get_event_loop_policy()).__name__
    loop_type_name = type(loop).__name__
    debug_log(f"Created new event loop: {loop_type_name} with policy: {loop_policy_name}")

    # On Windows, verify we're using the correct event loop type for subprocess support
    if is_windows:
        if 'Proactor' not in loop_type_name:
            log(
                f"WARNING: Current event loop {loop_type_name} is not a "
                f"ProactorEventLoop, subprocesses may not work!",
                is_error=True
            )
            log(f"Current event loop policy: {loop_policy_name}", is_error=True)

    # More detailed logging for Windows environments
    if is_windows:
        # Check if we have a ProactorEventLoop which is required for subprocess support on Windows
        is_proactor = loop_type_name == 'ProactorEventLoop' or 'Proactor' in loop_type_name
        debug_log(f"Windows event loop is ProactorEventLoop: {is_proactor} (required for subprocess support)")

    try:
        # Create and run the task
        task = loop.create_task(coroutine_func(*args, **kwargs))
        result = loop.run_until_complete(task)
    except Exception as e:
        # Cancel the task if there was an error
        if 'task' in locals() and not task.done():
            task.cancel()
            # Give it a chance to complete cancellation
            try:
                loop.run_until_complete(task)
            except (asyncio.CancelledError, Exception):
                pass
        raise e  # Re-raise the exception
    finally:
        # Clean up any remaining tasks
        pending = asyncio.all_tasks(loop)

        # Security: Limit maximum tasks to prevent resource exhaustion
        if len(pending) > MAX_PENDING_TASKS:
            log(
                f"Security Warning: {len(pending)} pending tasks exceeds limit of {MAX_PENDING_TASKS}",
                is_error=True
            )
            # Proceed with cancellation but log the security concern

        if pending:
            # Cancel all pending tasks
            for task in pending:
                if not task.done():
                    task.cancel()

            # Give tasks a chance to terminate with shorter timeout
            try:
                # Use a short timeout to avoid hanging (reduced from 2.0s)
                wait_task = asyncio.wait(pending, timeout=0.5, return_when=asyncio.ALL_COMPLETED)
                loop.run_until_complete(wait_task)
            except asyncio.TimeoutError:
                # Security: Log force-killed tasks
                log(
                    f"Security Warning: Force-killed {len(pending)} tasks after timeout",
                    is_error=True
                )
            except (asyncio.CancelledError, Exception):
                pass

        # Shut down asyncgens and close the loop properly
        try:
            loop.run_until_complete(loop.shutdown_asyncgens())
        except Exception:
            pass

        # Close the loop
        try:
            loop.close()
        except Exception:
            pass

    return result
