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
from src.utils import log, debug_log
from .directory_tree_utils import get_directory_tree


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


    def _annotate_build_file(self, file: str) -> str:
        """
        Add annotation explaining what a build file means.

        Args:
            file: Build file path

        Returns:
            Annotation string (e.g., " (Maven build configuration)")
        """
        if file.endswith('pom.xml'):
            return " (Maven build configuration)"
        elif file.endswith('build.gradle') or file.endswith('build.gradle.kts'):
            return " (Gradle build configuration)"
        elif file.endswith('package.json'):
            return " (npm/Node.js project)"
        elif file == 'Makefile':
            return " (Make build configuration)"
        elif file.endswith('build.xml'):
            return " (Ant build configuration)"
        elif file.endswith('.csproj') or file.endswith('.sln'):
            return " (C#/.NET project)"
        elif file == 'pyproject.toml' or file == 'setup.py':
            return " (Python project)"
        return ""

    def _explain_command_rationale(self, command: str) -> str:
        """
        Explain why a command was tried based on its content.

        Args:
            command: The command string

        Returns:
            Explanation string or empty if not applicable
        """
        if 'mvn' in command:
            return "*Why tried:* Standard Maven test command\n\n"
        elif 'gradle' in command:
            return "*Why tried:* Standard Gradle test command\n\n"
        elif 'npm test' in command:
            return "*Why tried:* Standard npm test script\n\n"
        elif 'pytest' in command:
            return "*Why tried:* Standard Python pytest command\n\n"
        elif 'make' in command:
            return "*Why tried:* Standard Make test target\n\n"
        return ""

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

        # Add directory tree for high-level overview
        prompt_parts.append("## Project Directory Structure\n\n")
        tree = get_directory_tree(self.repo_root, max_depth=3)
        prompt_parts.append("```\n")
        prompt_parts.append(tree)
        prompt_parts.append("\n```\n\n")

        # Add build system files with context
        prompt_parts.append("## Build System Detection\n\n")
        if build_files:
            prompt_parts.append("Phase 1 (pattern-based detection) found these build system files:\n")
            for file in build_files:
                prompt_parts.append(f"- `{file}`")
                prompt_parts.append(self._annotate_build_file(file))
                prompt_parts.append("\n")
            prompt_parts.append("\n")
        else:
            prompt_parts.append("Phase 1 did not find any standard build system files.\n\n")

        # Add failed attempt history with better context
        if failed_attempts:
            prompt_parts.append("## Failed Command Attempts\n\n")
            prompt_parts.append(
                "Phase 1 automatically tried standard commands based on detected build files. "
                "All attempts failed. You need to analyze WHY they failed and suggest a corrected command.\n\n"
            )

            for i, attempt in enumerate(failed_attempts, 1):
                prompt_parts.append(f"### Attempt {i}\n")
                prompt_parts.append(f"**Command tried:** `{attempt['command']}`\n\n")
                prompt_parts.append(self._explain_command_rationale(attempt['command']))
                prompt_parts.append(f"**Error encountered:**\n```\n{attempt['error']}\n```\n\n")

        # Add instructions
        prompt_parts.append("## Your Task\n\n")
        prompt_parts.append(
            "Based on the directory structure, build system files, and error patterns above, "
            "suggest a corrected build/test command.\n\n"
            "Consider:\n"
            "- Is this a monorepo? (multiple build files in subdirectories may need -f or -p flags)\n"
            "- Are there wrapper scripts? (./gradlew vs gradle, ./mvnw vs mvn)\n"
            "- Does the error indicate missing dependencies, wrong directory, or configuration issues?\n"
            "- What specific adjustments would fix the errors shown above?\n"
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
