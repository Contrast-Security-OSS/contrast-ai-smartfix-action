# -
# #%L
# Contrast AI SmartFix
# %%
# Copyright (C) 2025 Contrast Security, Inc.
# %%
# Contact: support@contrastsecurity.com
# License: Commercial
# NOTICE: This Software and the patented inventions embodied within may only be
# used as part of Contrast Security’s commercial offerings. Even though it is
# made available through public repositories, use of this Software is subject to
# the applicable End User Licensing Agreement found at
# https://www.contrastsecurity.com/enduser-terms-0317a or as otherwise agreed
# between Contrast Security and the End User. The Software may not be reverse
# engineered, modified, repackaged, sold, redistributed or otherwise used in a
# way not consistent with the End User License Agreement.
# #L%
#

import os
import subprocess
import sys
import re
import platform
from typing import Optional
from src.config import get_config


def normalize_host(host: str) -> str:
    """Remove any protocol prefix and trailing slash from host to prevent double prefixing when constructing URLs."""
    normalized = host.replace('https://', '').replace('http://', '')
    return normalized.rstrip('/')


def tail_string(text: str, max_length: int, prefix: str = "...[Content truncated]...\n") -> str:
    """Tail a string to a maximum length, keeping the end portion.

    Args:
        text: The string to truncate
        max_length: Maximum length of the resulting string
        prefix: Optional prefix to add when truncating (default: "...[Content truncated]...\n")

    Returns:
        str: The original string if within max_length, or truncated string with prefix indicator
    """
    if len(text) <= max_length:
        return text

    # Calculate how much of the original text we can keep after accounting for the prefix
    remaining_length = max_length - len(prefix)
    if remaining_length <= 0:
        # If prefix is too long, just return the prefix truncated to max_length
        return prefix[:max_length]

    return prefix + text[-remaining_length:]

# Unicode to ASCII fallback mappings for Windows


UNICODE_FALLBACKS = {
    '\u274c': 'X',  # ❌ -> X
    '❌': 'X',  # ❌ -> X
    '\u2705': '',  # ✅ -> ''
    '\u2728': '*',  # ✨ -> *
    '⚠️': '!',  # ⚠️ -> !
    '🔑': '',    # 🔑 -> ''
    '🛠️': '',   # 🛠️ -> ''
    '💡': '',   # 💡 -> ''
    '🚀': '',  # 🚀 -> ''
}


def safe_print(message, file=None, flush=True):
    """Safely print message, handling encoding issues on Windows."""
    try:
        print(message, file=file, flush=flush)
    except UnicodeEncodeError:
        # On Windows, replace Unicode chars with ASCII equivalents
        for unicode_char, ascii_fallback in UNICODE_FALLBACKS.items():
            message = message.replace(unicode_char, ascii_fallback)

        # Replace any remaining problematic Unicode characters with '?'
        if platform.system() == 'Windows':
            message = ''.join([c if ord(c) < 128 else '?' for c in message])

        print(message, file=file, flush=flush)


def log(message: str, is_error: bool = False, is_warning: bool = False):
    """Logs a message to telemetry and prints to stdout/stderr."""
    from src import telemetry_handler  # Local import to break circular dependency
    telemetry_handler.add_log_message(message)
    if is_error:
        safe_print(message, file=sys.stderr, flush=True)
    elif is_warning:
        # Optionally, differentiate warning logs, e.g., with a prefix
        safe_print(f"WARNING: {message}", flush=True)
    else:
        safe_print(message, flush=True)


def debug_log(*args, **kwargs):
    """Prints only if DEBUG_MODE is True and logs to telemetry."""
    config = get_config()
    from src import telemetry_handler  # Local import to break circular dependency
    message = " ".join(map(str, args))
    # Log debug messages to telemetry, possibly with a DEBUG prefix or separate field if needed
    # For now, adding to the main log.
    telemetry_handler.add_log_message(f"DEBUG: {message}")
    if config.DEBUG_MODE:
        # Use safe_print for the combined message rather than direct print of args
        safe_print(message, flush=True)


def extract_remediation_id_from_branch(branch_name: str) -> Optional[str]:
    """Extracts the remediation ID from a branch name.

    Args:
        branch_name: Branch name in format 'smartfix/remediation-{remediation_id}'

    Returns:
        str: The remediation ID if found, or None if not found
    """
    # Match smartfix/remediation-{id} format
    match = re.search(r'smartfix/remediation-([^/]+)', branch_name)
    if match:
        return match.group(1)
    return None


def extract_remediation_id_from_labels(labels: list) -> Optional[str]:
    """Extracts the remediation ID from PR labels.

    Args:
        labels: List of label objects from PR, each with a 'name' field

    Returns:
        str: The remediation ID if found, or None if not found
    """
    for label in labels:
        label_name = label.get("name", "")
        if label_name.startswith("smartfix-id:"):
            # Extract ID from label format "smartfix-id:{remediation_id}"
            parts = label_name.split("smartfix-id:")
            if len(parts) > 1:
                return parts[1]
    return None


# Define custom exception for command errors


class CommandExecutionError(Exception):
    """Custom exception for errors during command execution."""
    def __init__(self, message, return_code, command, stdout=None, stderr=None):
        super().__init__(message)
        self.return_code = return_code
        self.command = command
        self.stdout = stdout
        self.stderr = stderr


def run_command(command, env=None, check=True, shell=False):  # noqa: C901
    """
    Runs a shell command and returns its stdout.
    Prints command, stdout/stderr based on DEBUG_MODE.
    Exits on error if check=True.

    Args:
        command: List of command and arguments to run, or string if shell=True
        env: Optional environment variables dictionary
        check: Whether to exit on command failure
        shell: Whether to run the command through the shell (for operators like &&, ||, etc.)

    Returns:
        str: Command stdout output

    Raises:
        SystemExit: If check=True and command fails

    Note:
        Complexity is necessary for proper command execution and error handling.
    """
    try:
        # Show command and options for better debugging
        options_text = f"Options: check={check}, shell={shell}"
        if env and env.get('GITHUB_TOKEN'):
            # Don't print the actual token
            options_text += ", GITHUB_TOKEN=***"

        # Mask GITHUB_TOKEN value in command parts
        config = get_config()
        if shell:
            # For shell commands, mask token in the string
            masked_command = command
            if config.GITHUB_TOKEN and config.GITHUB_TOKEN in command:
                masked_command = command.replace(config.GITHUB_TOKEN, "***")
            debug_log(f"::group::Running command: {masked_command}")
        else:
            # For list commands, mask token in each part
            masked_command = []
            for part in command:
                # Note: the gh envvars "GITHUB_ENTERPRISE_TOKEN" and "GITHUB_TOKEN" have the same value as config.GITHUB_TOKEN
                if config.GITHUB_TOKEN and config.GITHUB_TOKEN in part:
                    masked_command.append(part.replace(config.GITHUB_TOKEN, "***"))
                else:
                    masked_command.append(part)
            debug_log(f"::group::Running command: {' '.join(masked_command)}")

        debug_log(f"  {options_text}")

        # Merge with current environment to preserve essential variables like PATH
        full_env = os.environ.copy()
        if env:
            full_env.update(env)

        # Set encoding and error handling for better robustness
        process = subprocess.run(
            command,
            capture_output=True,
            text=True,
            encoding='utf-8',
            errors='replace',
            check=False,  # We'll handle errors ourselves
            env=full_env,
            shell=shell
        )

        debug_log(f"  Return Code: {process.returncode}")
        if process.stdout:
            # Truncate very large stdout for readability
            stdout_text = process.stdout.strip()
            if len(stdout_text) > 1000:
                debug_log(f"  Command stdout (truncated):\n---\n{stdout_text[:500]}...\n...{stdout_text[-500:]}\n---")
            else:
                debug_log(f"  Command stdout:\n---\n{stdout_text}\n---")

        if process.stderr:
            # Always print stderr if it's not empty, as it often indicates warnings/errors
            stderr_text = process.stderr.strip()

            # Use new log function for stderr
            if process.returncode != 0:
                if len(stderr_text) > 1000:
                    log(
                        f"  Command stderr (truncated):\n---\n{stderr_text[:500]}..."
                        f"\n...{stderr_text[-500:]}\n---",
                        is_error=True
                    )
                else:
                    log(f"  Command stderr:\n---\n{stderr_text}\n---", is_error=True)
            elif stderr_text:  # Log as debug if there's stderr but command was successful
                if len(stderr_text) > 1000:
                    debug_log(
                        f"  Command stderr (truncated):\n---\n{stderr_text[:500]}..."
                        f"\n...{stderr_text[-500:]}\n---"
                    )
                else:
                    debug_log(f"  Command stderr:\n---\n{stderr_text}\n---")

        if check and process.returncode != 0:
            command_str = command if shell else ' '.join(command)
            error_message_for_log = f"Error: Command failed with return code {process.returncode}: {command_str}"
            log(error_message_for_log, is_error=True)
            error_details = process.stderr.strip() if process.stderr else "No error output available"
            log(f"Error details: {error_details}", is_error=True)
            raise CommandExecutionError(
                message=f"Command '{command_str}' failed with return code {process.returncode}.",
                return_code=process.returncode,
                command=command_str,
                stdout=process.stdout.strip() if process.stdout else None,
                stderr=error_details
            )

        return process.stdout.strip() if process.stdout else ""  # Return stdout or empty string
    finally:
        debug_log("::endgroup::")


def error_exit(remediation_id: str, failure_code: Optional[str] = None):
    """
    Cleans up a branch (if provided), sends telemetry, and exits with code 1.

    This function handles the graceful shutdown of the SmartFix workflow when an
    error occurs. It attempts to notify the Remediation service, clean up the
    Git branch, and send telemetry data before exiting. If any step fails with an
    exception, the function will catch it, log it, and continue with the next step.

    Args:
        remediation_id: The ID of the remediation that failed
        failure_code: Optional failure category code, defaults to GENERAL_FAILURE
    """
    config = get_config()
    # Local imports to avoid circular dependencies
    from src.git_handler import cleanup_branch, get_branch_name
    from src.contrast_api import notify_remediation_failed, send_telemetry_data
    from src.smartfix.shared.failure_categories import FailureCategory

    # Set default failure code if none provided
    if not failure_code:
        failure_code = FailureCategory.GENERAL_FAILURE.value

    # Attempt to notify remediation service - continue even if this fails
    remediation_notified = notify_remediation_failed(
        remediation_id=remediation_id,
        failure_category=failure_code,
        contrast_host=config.CONTRAST_HOST,
        contrast_org_id=config.CONTRAST_ORG_ID,
        contrast_app_id=config.CONTRAST_APP_ID,
        contrast_auth_key=config.CONTRAST_AUTHORIZATION_KEY,
        contrast_api_key=config.CONTRAST_API_KEY
    )

    if remediation_notified:
        log(f"Successfully notified Remediation service about {failure_code} for remediation {remediation_id}.")
    else:
        log(
            f"Failed to notify Remediation service about {failure_code} "
            f"for remediation {remediation_id}.",
            is_warning=True
        )

    # Attempt to clean up any branches - continue even if this fails
    if config.CODING_AGENT == 'SMARTFIX':
        branch_name = get_branch_name(remediation_id)
        cleanup_branch(branch_name)

    # Always attempt to send final telemetry
    send_telemetry_data()

    # Exit with error code
    sys.exit(1)
