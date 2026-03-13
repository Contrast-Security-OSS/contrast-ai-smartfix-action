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
BuildTool - Google ADK Tool for executing format and build commands.

Key behaviors:
- Determines command mode (configured vs determined) by exact match
- Validates determined commands against allowlist
- Executes format first (if provided), then build
- Records successful commands in module-level storage
- Returns dict results with success status and output
"""

import logging
from pathlib import Path
from typing import Optional

from src.smartfix.config.command_validator import validate_command, CommandValidationError
from src.smartfix.domains.workflow.build_runner import run_build_command
from src.smartfix.domains.workflow.formatter import run_formatting_command
from src.build_output_analyzer import extract_build_errors

logger = logging.getLogger(__name__)

# Module-level storage (single-threaded CLI, no singleton needed)
_successful_build_command: Optional[str] = None
_successful_format_command: Optional[str] = None

# Shell utilities that don't count as real builds
_SHELL_UTILITIES = {'echo', 'sh', 'bash', 'grep', 'sed', 'awk', 'cat', 'tee'}


def get_successful_build_command() -> Optional[str]:
    """Get the recorded successful build command."""
    return _successful_build_command


def get_successful_format_command() -> Optional[str]:
    """Get the recorded successful format command."""
    return _successful_format_command


def reset_storage() -> None:
    """Reset storage. Used for testing and between vulnerability runs."""
    global _successful_build_command, _successful_format_command
    _successful_build_command = None
    _successful_format_command = None


def _is_recordable_command(cmd) -> bool:
    """Check if command should be recorded (not --version/--help/shell utility)."""
    if not cmd:
        return False
    if '--version' in cmd or '--help' in cmd:
        return False
    base = cmd.split()[0].split('/')[-1]  # Handle /usr/bin/echo
    return base not in _SHELL_UTILITIES


def _truncate_tail(output, max_lines: int = 100) -> str:
    """Truncate output to last N lines for success responses."""
    if not output:
        return ""
    lines = output.splitlines()
    if len(lines) > max_lines:
        lines = lines[-max_lines:]
    return '\n'.join(lines)


def create_build_tool(  # noqa: C901
    repo_root: Path,
    remediation_id: str,
    user_build_command: Optional[str] = None,
    user_format_command: Optional[str] = None,
):
    """
    Factory to create build_tool function for Google ADK agents.

    Args:
        repo_root: Repository root path
        remediation_id: Unique ID for this remediation run
        user_build_command: User-configured build command (exact match = configured mode)
        user_format_command: User-configured format command (exact match = configured mode)

    Returns:
        Callable that can be passed directly to agent's tools list.
    """

    def build_tool(build_command: str, format_command: Optional[str] = None) -> dict:
        """Execute format and build commands to verify code changes compile correctly.

        Run this first to establish baseline, then after making code changes.
        If recorded=False on success, try a real build command (not --version).

        Args:
            build_command: The build command to execute (e.g., "mvn test", "npm run build")
            format_command: Optional formatting command to run first (e.g., "mvn spotless:apply")

        Returns:
            Dictionary with build results:
            - success: Whether the build command succeeded
            - output: Command output (truncated tail or error snippet)
            - recorded: Whether this counts as a verified build for PR creation
        """
        global _successful_build_command, _successful_format_command

        normalized_build = build_command.strip() if build_command else ""
        normalized_user_build = user_build_command.strip() if user_build_command else ""
        normalized_format = format_command.strip() if format_command else ""
        normalized_user_format = user_format_command.strip() if user_format_command else ""

        # Configured mode = exact match to user-provided command
        build_is_configured = (normalized_build == normalized_user_build) if normalized_user_build else False
        format_is_configured = (normalized_format == normalized_user_format) if normalized_user_format else False

        # Validate determined build command against allowlist
        if not build_is_configured:
            try:
                validate_command("BUILD_COMMAND", build_command)
            except CommandValidationError as e:
                logger.warning(f"Build command validation failed: {e}")
                return {"success": False, "output": f"Command not allowed: {e}", "recorded": False}

        # Validate determined format command against allowlist
        if format_command and not format_is_configured:
            try:
                validate_command("FORMAT_COMMAND", format_command)
            except CommandValidationError as e:
                logger.warning(f"Format command validation failed: {e}")
                return {"success": False, "output": f"Format command not allowed: {e}", "recorded": False}

        # Run format (best effort — log and continue on failure)
        if format_command:
            logger.info(f"Running format: {format_command}")
            try:
                run_formatting_command(format_command, repo_root, remediation_id)
                if _is_recordable_command(format_command):
                    _successful_format_command = format_command
                    logger.info(f"Format recorded: {format_command}")
            except Exception as e:
                logger.warning(f"Format failed (continuing): {e}")

        # Run build
        logger.info(f"Running build: {build_command}")
        try:
            success, output = run_build_command(build_command, repo_root, remediation_id)
        except Exception as e:
            logger.error(f"Build exception: {e}")
            return {"success": False, "output": f"Build exception: {e}", "recorded": False}

        if success:
            is_recordable = _is_recordable_command(build_command)
            if is_recordable:
                _successful_build_command = build_command
                logger.info(f"Build recorded: {build_command}")
            else:
                logger.info("Build succeeded but not recorded (--version/--help/shell utility)")

            return {
                "success": True,
                "output": _truncate_tail(output),
                "recorded": is_recordable,
            }
        else:
            logger.warning(f"Build failed: {build_command}")
            return {
                "success": False,
                "output": extract_build_errors(output),
                "recorded": False,
            }

    return build_tool
