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
Command Detection Agent

LLM-based agent that detects build and test commands by analyzing
project structure and iteratively refining suggestions based on
execution failures.
"""

from pathlib import Path

from src.smartfix.config.command_validator import (
    validate_command,
    CommandValidationError,
)
from src.smartfix.domains.workflow.build_runner import run_build_command
from src.build_output_analyzer import extract_build_errors
from src.utils import log


class CommandDetectionError(Exception):
    """Base exception for command detection errors."""
    pass


class MaxAttemptsExceededError(CommandDetectionError):
    """Raised when max detection attempts are exhausted without success."""
    pass


class AgentExecutionError(CommandDetectionError):
    """Raised when the LLM agent fails to execute properly."""
    pass


class ValidationError(CommandDetectionError):
    """Raised when a detected command fails validation."""
    pass


class CommandDetectionAgent:
    """
    Agent that uses LLM to detect build/test commands through iterative refinement.

    Follows a feedback loop pattern:
    1. Analyze project structure and failed attempts
    2. Generate prompt with error context
    3. Get LLM suggestion
    4. Test command
    5. If fails, add to failed_attempts and repeat
    """

    def __init__(
        self,
        repo_root: Path,
        project_dir: Path | None = None,
        max_attempts: int = 6
    ) -> None:
        """
        Initialize command detection agent.

        Args:
            repo_root: Repository root directory
            project_dir: Optional subdirectory for monorepo projects
            max_attempts: Maximum detection attempts before giving up
        """
        self.repo_root = repo_root
        self.project_dir = project_dir
        self.max_attempts = max_attempts

    def detect(
        self,
        build_files: list[str],
        failed_attempts: list[dict[str, str]],
        remediation_id: str
    ) -> str | None:
        """
        Detect build command through iterative LLM refinement.

        Implements iteration loop with error feedback. Calls LLM agent,
        validates suggestions, tests commands, and refines based on failures.

        Args:
            build_files: List of build system marker files found
            failed_attempts: History of failed command attempts with errors
            remediation_id: For error tracking and telemetry

        Returns:
            Valid build command string, or None if detection fails
        """
        # Track attempt history for this detection session
        attempt_history = list(failed_attempts)

        # Lazy import to avoid circular dependency with config module
        from src.smartfix.domains.agents.sub_agent_executor import SubAgentExecutor

        # Create SubAgentExecutor for LLM calls
        executor = SubAgentExecutor()

        # Iteration loop with max_attempts enforcement
        for _ in range(self.max_attempts):
            # Build prompt for current iteration
            prompt = self._build_iteration_prompt(build_files, attempt_history)

            # Call LLM agent to get suggested command (with filesystem access)
            suggested_command = executor.execute_detection(
                prompt=prompt,
                target_folder=self.repo_root,
                remediation_id=remediation_id
            )

            # Validate suggested command
            try:
                validate_command("BUILD_COMMAND", suggested_command)
            except CommandValidationError as e:
                # Add validation error to attempt history
                attempt_history.append({
                    "command": suggested_command,
                    "error": f"Command validation failed: {str(e)}"
                })
                continue  # Skip to next iteration

            # Test command execution
            success, output = run_build_command(suggested_command, self.repo_root, remediation_id)

            if success:
                # Command works! Return it
                return suggested_command

            # Extract errors for next iteration
            error_summary = extract_build_errors(output)

            # Add to attempt_history and continue loop
            attempt_history.append({
                "command": suggested_command,
                "error": error_summary
            })

        # Max attempts exhausted - log warning and return None
        self._log_max_attempts_exhausted(build_files, attempt_history)
        return None

    def _build_iteration_prompt(
        self,
        build_files: list[str],
        failed_attempts: list[dict[str, str]]
    ) -> str:
        """
        Build prompt for LLM based on project structure and failure history.

        Args:
            build_files: List of build system marker files found
            failed_attempts: List of dicts with 'command' and 'error' keys

        Returns:
            Formatted prompt string for LLM
        """
        prompt_parts = []

        # Add project structure context
        prompt_parts.append("## Project Structure\n")
        prompt_parts.append("Build system files detected:\n")
        for file in build_files:
            prompt_parts.append(f"- {file}\n")
        prompt_parts.append("\n")

        # Add failed attempt history if any
        if failed_attempts:
            prompt_parts.append("## Previous attempts\n")
            prompt_parts.append("The following commands have already been tried and failed:\n\n")

            for i, attempt in enumerate(failed_attempts, 1):
                prompt_parts.append(f"### Attempt {i}\n")
                prompt_parts.append(f"Command: `{attempt['command']}`\n")
                prompt_parts.append(f"Error: {attempt['error']}\n\n")

        # Add instructions
        prompt_parts.append("## Task\n")
        prompt_parts.append(
            "Suggest a build/test command that will successfully run tests "
            "based on the project structure and error patterns above.\n"
        )

        return "".join(prompt_parts)

    def _log_max_attempts_exhausted(
        self,
        build_files: list[str],
        failed_attempts: list[dict[str, str]]
    ) -> None:
        """
        Log warning when max detection attempts are exhausted.

        Args:
            build_files: List of build system marker files found
            failed_attempts: History of failed command attempts with errors
        """
        # Build warning message with context
        warning_parts = [
            f"Phase 2 LLM detection exhausted {self.max_attempts} attempts without finding valid build command."
        ]

        # Add build files context
        if build_files:
            warning_parts.append(f"Build files found: {', '.join(build_files)}")

        # Add attempt count
        if failed_attempts:
            warning_parts.append(f"Tried {len(failed_attempts)} command(s)")

            # Add last attempt details for debugging
            last_attempt = failed_attempts[-1]
            warning_parts.append(f"Last attempt: {last_attempt['command']}")
            warning_parts.append(f"Last error: {last_attempt['error'][:200]}...")  # Truncate long errors

        # Log as warning
        log(" | ".join(warning_parts), is_warning=True)
