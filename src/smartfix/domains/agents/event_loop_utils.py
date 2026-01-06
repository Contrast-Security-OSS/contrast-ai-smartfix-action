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
Event Loop Utilities Module

Provides event loop management, platform-specific configuration, and
high-level agent execution wrapper functions.
"""

import asyncio
import logging
import platform
from pathlib import Path

from src.config import get_config
from src.utils import debug_log, log, error_exit
from src.smartfix.shared.failure_categories import FailureCategory

from .sub_agent_executor import SubAgentExecutor, ADK_AVAILABLE

# Conditional imports
try:
    from google.adk.artifacts.in_memory_artifact_service import InMemoryArtifactService
    from google.adk.runners import Runner
    from google.adk.sessions import InMemorySessionService
    from asyncio import WindowsProactorEventLoopPolicy
except ImportError:
    pass


def _run_agent_in_event_loop(coroutine_func, *args, **kwargs):
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
        MAX_PENDING_TASKS = 100
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


async def _run_agent_internal_with_prompts(
    agent_type: str,
    repo_root: Path,
    query: str,
    system_prompt: str,
    remediation_id: str,
    session_id: str = None
) -> str:
    """
    Internal helper to run either fix or QA agent with API-provided prompts. Returns summary.

    Args:
        agent_type: Type of agent ("fix" or "qa")
        repo_root: Path to repository root
        query: User query/prompt for the agent
        system_prompt: System prompt for agent instructions
        remediation_id: Remediation ID for error tracking
        session_id: Session ID for Contrast LLM tracking

    Returns:
        str: Summary from the agent execution
    """
    config = get_config()
    debug_log(f"Using Agent Model ID: {config.AGENT_MODEL}")

    # Set the correct event loop policy for Windows
    # This is crucial for the MCP filesystem server connections to work on Windows
    if platform.system() == 'Windows':
        try:
            # First ensure there's no active event loop that might conflict
            try:
                loop = asyncio.get_event_loop()
                if not loop.is_closed():
                    debug_log("Closing existing event loop before setting policy")
                    loop.close()
            except RuntimeError:
                pass  # No event loop, which is fine

            # IMPORTANT: On Windows, we MUST use the ProactorEventLoop
            # SelectorEventLoop doesn't support subprocesses on Windows
            # Explicitly set the WindowsProactorEventLoopPolicy to ensure subprocess support
            asyncio.set_event_loop_policy(WindowsProactorEventLoopPolicy())
            debug_log("Explicitly set WindowsProactorEventLoopPolicy for subprocess support")

            # Create a fresh event loop with the WindowsProactorEventLoopPolicy
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            debug_log(f"Created and set new event loop with Windows default policy: {type(loop).__name__}")
        except Exception as e:
            debug_log(f"Warning: Error setting Windows event loop policy: {e}")
            debug_log("Will continue with default event loop policy")

    # Configure logging to suppress asyncio and anyio errors that typically occur during cleanup
    # Suppress anyio error logging
    anyio_logger = logging.getLogger("anyio")
    anyio_logger.setLevel(logging.CRITICAL)  # Using CRITICAL instead of ERROR for stricter filtering

    # Suppress MCP client/stdio error logging
    mcp_logger = logging.getLogger("mcp.client.stdio")
    mcp_logger.setLevel(logging.CRITICAL)

    # Silence the task exception was never retrieved warnings
    asyncio_logger = logging.getLogger("asyncio")
    asyncio_logger.setLevel(logging.CRITICAL)

    # Add a comprehensive filter to specifically ignore common cancel scope and cleanup errors
    class AsyncioCleanupFilter(logging.Filter):
        def filter(self, record):
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

    if not ADK_AVAILABLE:
        log(f"FATAL: {agent_type.capitalize()} Agent execution skipped: ADK libraries not available (import failed).")
        error_exit(remediation_id, FailureCategory.AGENT_FAILURE.value)

    session = None
    runner = None

    try:
        session_service = InMemorySessionService()
        artifacts_service = InMemoryArtifactService()
        app_name = f'contrast_{agent_type}_app'
        session = await session_service.create_session(
            state={},
            app_name=app_name,
            user_id=f'github_action_{agent_type}'
        )
    except Exception as e:
        # Handle any errors in session creation
        log(f"FATAL: Failed to create {agent_type.capitalize()} agent session: {e}", is_error=True)
        error_exit(remediation_id, FailureCategory.AGENT_FAILURE.value)

    # Use SubAgentExecutor to create and execute the agent
    executor = SubAgentExecutor()

    agent = await executor.create_agent(
        repo_root, remediation_id, session_id, agent_type=agent_type, system_prompt=system_prompt
    )
    if not agent:
        log(
            f"AI Agent creation failed ({agent_type} agent). "
            f"Possible reasons: MCP server connection issue, missing prompts, "
            f"model configuration error, or internal ADK problem."
        )
        error_exit(remediation_id, FailureCategory.AGENT_FAILURE.value)

    runner = Runner(
        app_name=app_name,
        agent=agent,
        artifact_service=artifacts_service,
        session_service=session_service,
    )

    # Execute the agent using the executor
    summary = await executor.execute_agent(runner, agent, session, query, remediation_id, agent_type)
    return summary
